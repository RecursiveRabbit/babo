"""Talking to the Manager: one small seam, and one honest stub.

By the agreed contract, Babo is the control plane but **not the executor**: the
NeoClaw Manager holds the only podman socket, the only Router API access, and
the only credential minting. Babo reads state from it and asks it for actions
over WireGuard (``NEOCLAW_MANAGER_URL``, in-pod default
``http://10.0.0.3:9200``).

There is deliberately **no podman backend and no local default**: an unset or
unreachable Manager is the page's ``unavailable`` state, never a quiet fallback
to running containers from inside Babo's own pod.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from babo.office.model import AgentObserved, Checkout, OpResult

DEFAULT_MANAGER_URL = "http://10.0.0.3:9200"


class ManagerUnreachableError(Exception):
    """The Manager can't be reached at all (as opposed to: an action failed)."""


class ManagerProtocol(Protocol):
    name: str

    def reachable(self) -> tuple[bool, str]: ...
    def state(self) -> list[AgentObserved]: ...
    def act(self, handle: str, action: str, reason: str) -> str: ...
    def action_status(self, action_id: str) -> dict[str, Any]: ...


def _observed_from_row(row: dict[str, Any]) -> AgentObserved:
    raw_checkouts = row.get("live_credentials") or row.get("checkouts") or []
    checkouts = tuple(
        Checkout(id=str(item.get("id") or ""), scope=str(item.get("scope") or ""),
                 issued_at=str(item.get("issued_at") or ""), expires_at=str(item.get("expires_at") or ""))
        for item in cast(list[dict[str, Any]], raw_checkouts) if isinstance(item, dict)
    )
    return AgentObserved(
        handle=str(row.get("handle") or ""),
        state=str(row.get("state") or "unknown").lower(),
        wg_address=str(row.get("wg_address") or ""),
        last_activity_at=str(row.get("last_activity_at") or row.get("last_activity") or ""),
        checkouts=checkouts,
        provenance={str(k): str(v) for k, v in cast(dict[object, object], row.get("provenance") or {}).items()},
    )


@dataclass
class ManagerBackend:
    """The Manager's three endpoints, exactly as agreed."""

    base_url: str = DEFAULT_MANAGER_URL
    timeout_s: float = 20.0
    name: str = "manager"

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        url = self.base_url.rstrip("/") + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                text = response.read().decode("utf-8", "replace")
                return response.status, json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return exc.code, text[:400]
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ManagerUnreachableError(f"can't reach the Manager at {self.base_url}: {exc}") from exc

    def reachable(self) -> tuple[bool, str]:
        try:
            status, _body = self._request("GET", "/api/v1/office/state")
        except ManagerUnreachableError as exc:
            return False, str(exc)
        if status != 200:
            return False, f"the Manager answered {status}"
        return True, f"the Manager answered at {self.base_url}"

    def state(self) -> list[AgentObserved]:
        status, body = self._request("GET", "/api/v1/office/state")
        if status != 200:
            raise ManagerUnreachableError(f"the Manager answered {status}: {body}")
        rows = body.get("agents") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise ManagerUnreachableError("the Manager's state answer has no agents list")
        return [_observed_from_row(cast(dict[str, Any], row)) for row in rows if isinstance(row, dict)]

    def act(self, handle: str, action: str, reason: str) -> str:
        status, body = self._request("POST", f"/api/v1/office/agents/{handle}/actions",
                                     {"action": action, "reason": reason})
        if status == 202 and isinstance(body, dict) and body.get("action_id"):
            return str(body["action_id"])
        if status in (400, 403, 404, 409, 429):
            raise ManagerUnreachableError(f"the Manager refused {action} for {handle} ({status}): {body}")
        raise ManagerUnreachableError(f"the Manager answered {status} to {action} for {handle}: {body}")

    def action_status(self, action_id: str) -> dict[str, Any]:
        status, body = self._request("GET", f"/api/v1/office/actions/{action_id}")
        if status != 200 or not isinstance(body, dict):
            raise ManagerUnreachableError(f"the Manager answered {status} for action {action_id}: {body}")
        return body


@dataclass
class StubManager:
    """A Manager with no container runtime: for tests, and for a page that must not pretend.

    State is honest and small: agents are alive or frozen, actions succeed or
    fail on request, and nothing is invented that the interface doesn't carry.
    """

    name: str = "stub"
    agents: dict[str, AgentObserved] = field(default_factory=dict)
    fail: set[str] = field(default_factory=set)  # actions that fail (by action name)
    unavailable: str = ""
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next: int = 0

    def reachable(self) -> tuple[bool, str]:
        return (False, self.unavailable) if self.unavailable else (True, "stub manager")

    def state(self) -> list[AgentObserved]:
        if self.unavailable:
            raise ManagerUnreachableError(self.unavailable)
        return list(self.agents.values())

    def act(self, handle: str, action: str, reason: str) -> str:
        del reason
        if self.unavailable:
            raise ManagerUnreachableError(self.unavailable)
        if handle not in self.agents:
            raise ManagerUnreachableError(f"the Manager refused {action} for {handle} (404): unknown handle")
        self._next += 1
        action_id = f"act-{self._next}"
        self.actions[action_id] = {"handle": handle, "action": action}
        return action_id

    def action_status(self, action_id: str) -> dict[str, Any]:
        row = self.actions.get(action_id)
        if row is None:
            raise ManagerUnreachableError(f"no such action: {action_id}")
        handle, action = str(row["handle"]), str(row["action"])
        if action in self.fail:
            row["state"] = "failed"
            row["detail"] = f"stub: {action} {handle} failed at the runtime"
        elif action == "wake":
            row["state"] = "succeeded"
            current = self.agents[handle]
            self.agents[handle] = AgentObserved(handle=handle, state="alive", wg_address=current.wg_address,
                                                last_activity_at=current.last_activity_at,
                                                checkouts=current.checkouts, provenance=current.provenance)
            row["detail"] = f"woke {handle}"
        elif action == "freeze":
            row["state"] = "succeeded"
            current = self.agents[handle]
            self.agents[handle] = AgentObserved(handle=handle, state="frozen", wg_address=current.wg_address,
                                                last_activity_at=current.last_activity_at,
                                                checkouts=(), provenance=current.provenance)
            row["detail"] = f"froze {handle}: stood down, work pushed, pod released"
        else:
            row["state"] = "refused"
            row["detail"] = f"stub doesn't run '{action}'"
        return row


def from_config(baton: object) -> ManagerProtocol:
    """The backend the configuration asks for: the Manager over WG, or an honest stub.

    ``baton.office.backend`` is ``manager`` (default) or ``stub``;
    ``baton.office.manager_url`` overrides ``NEOCLAW_MANAGER_URL``'s default.
    Empty everywhere means the default WG address — never a loopback fallback.
    """
    office = getattr(baton, "office", None)
    kind = str(getattr(office, "backend", "manager") or "manager").lower()
    if kind == "stub":
        return StubManager()
    url = str(getattr(office, "manager_url", "") or os.environ.get("NEOCLAW_MANAGER_URL", "") or DEFAULT_MANAGER_URL)
    return ManagerBackend(base_url=url, timeout_s=float(getattr(office, "timeout_s", 20.0) or 20.0))


def _result_from_action(row: dict[str, Any]) -> OpResult:
    state = str(row.get("state") or "unknown")
    detail = str(row.get("detail") or "")
    return OpResult(ok=state == "succeeded", said=detail or f"the action is {state}")
