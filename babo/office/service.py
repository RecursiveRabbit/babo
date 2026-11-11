"""The Manager's side of the hop: handlers, validation, and the peer check.

D-12 makes the UI the only caller. That is enforced twice on purpose — the
Router admits only the UI pod's address to this port, and these handlers compare
the **socket peer** to that same exact address, header-blind. A wrong network
rule therefore still gets a 403 from the application rather than an open door.

The handlers are pure: they take a peer string and a parsed body, and return
``(status, payload)``. The listener, its binding and its policy belong to the
network lane; keeping the interpretation here means the rules can be tested
without a socket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from babo.office.api import ACTIONS, TERMINAL, OfficeManager


def _named(exc: BaseException, *names: str) -> bool:
    """Match a core exception by class name.

    The core's exception types live in ``babo/office/core.py``, which is another
    branch's file until the slice lands; importing them here would make this
    surface unimportable on its own head. The name match is deliberately narrow —
    anything that is not one of these keeps propagating, because a swallowed
    programming error is worse than a loud 500.
    """
    return type(exc).__name__ in names

# A body may carry these and nothing else; unknown keys are refused rather than
# ignored, because an ignored key is a client believing it changed something.
ACTION_FIELDS = frozenset({"handle", "action", "reason", "actor", "actor_source", "action_id"})


def peer_allowed(peer: str, allowed: tuple[str, ...]) -> bool:
    """Exact address match, no prefixes and no header trust — the trusted_sources rule."""
    return any(entry == peer for entry in allowed)


@dataclass
class ManagerService:
    core: OfficeManager
    ui_peers: tuple[str, ...]

    # -- reads -----------------------------------------------------------
    def health(self) -> tuple[int, dict[str, Any]]:
        available, detail = self.core.health()
        if available:
            return 200, {"available": True, "detail": detail, "core": getattr(self.core, "name", "core")}
        return 503, {"available": False, "detail": detail}

    def agents(self, peer: str) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        return 200, {"agents": [a.overview() for a in self.core.agents()]}

    # -- actions ---------------------------------------------------------
    def act(self, peer: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        unknown = set(body) - ACTION_FIELDS
        if unknown:
            return 400, {"detail": f"unknown field(s): {', '.join(sorted(unknown))}"}
        handle = str(body.get("handle") or "").strip()
        action = str(body.get("action") or "").strip()
        reason = str(body.get("reason") or "").strip()
        actor = str(body.get("actor") or "").strip()
        actor_source = str(body.get("actor_source") or "").strip()
        replay = body.get("action_id")
        if not handle:
            return 400, {"detail": "missing handle"}
        if action not in ACTIONS:
            return 400, {"detail": f"unknown action {action!r}; it is one of {', '.join(ACTIONS)}"}
        if not reason:
            return 400, {"detail": "missing reason"}
        if not actor or not actor_source:
            # R5: no actor, no effect. Refuse here rather than let the core do it,
            # because this surface is the one that must not accept an anonymous call.
            return 400, {"detail": "missing actor or actor_source; an action must name who is asking"}
        try:
            action_id = self.core.act(handle, action, reason, actor=actor, actor_source=actor_source,
                                      action_id=str(replay) if isinstance(replay, str) and replay else None)
        except Exception as exc:
            if not _named(exc, "CoreRefusalError", "RefusalError"):
                raise
            # A refusal is an answer, not a server fault: nothing was queued, so
            # this is 409 carrying the core's own sentence.
            return 409, {"detail": str(exc)}
        return 202, {"action_id": action_id}

    def restart_ui(self, peer: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """The cross-pod half of revocation: replace the UI pod.

        It is an action, not a side door: same actor/reason requirement, same
        idempotency key, same closed terminal states, and the ledger records that
        it invalidates sessions by construction rather than by an API call reaching
        into another pod's memory.
        """
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        unknown = set(body) - {"reason", "actor", "actor_source", "action_id"}
        if unknown:
            return 400, {"detail": f"unknown field(s): {', '.join(sorted(unknown))}"}
        reason = str(body.get("reason") or "").strip()
        actor = str(body.get("actor") or "").strip()
        actor_source = str(body.get("actor_source") or "").strip()
        replay = body.get("action_id")
        if not reason or not actor or not actor_source:
            return 400, {"detail": "missing reason, actor or actor_source"}
        try:
            action_id = self.core.act("ui", "restart-ui", reason, actor=actor, actor_source=actor_source,
                                      action_id=str(replay) if isinstance(replay, str) and replay else None)
        except Exception as exc:
            if not _named(exc, "CoreRefusalError", "RefusalError"):
                raise
            return 409, {"detail": str(exc)}
        return 202, {"action_id": action_id}

    def action(self, peer: str, action_id: str) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        try:
            record = self.core.action(action_id)
        except Exception as exc:
            if not _named(exc, "UnknownActionError", "KeyError"):
                raise
            # An unknown id is 404, never an invented `failed`.
            return 404, {"detail": str(exc)}
        if record.state not in ("pending", "running", *TERMINAL):
            # A core bug must not reach the UI as a fifth word.
            return 503, {"detail": f"the core reported an unknown action state {record.state!r}"}
        return 200, {"state": record.state, "detail": record.said}
