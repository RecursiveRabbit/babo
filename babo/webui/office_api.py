"""The office pages of the web interface: the live view, and the two verbs.

Reads are GET routes; changes arrive as allowlisted WebUI mutations, like the
town's. Everything goes through ``babo.office.control``, which is what a
``babo office`` terminal command uses too, so web and terminal stay at parity.

A lifecycle action answers ``202`` the moment the Manager accepts it: the
Manager's own record answers from then on (``pending`` → ``running`` →
``succeeded``/``failed``/``refused``/``timeout``), and Babo never upgrades that
answer on its own.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any, cast

from loguru import logger
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from babo.baton.town import BatonError, Town
from babo.webui.http_utils import http_error, http_json_response

OFFICE_MUTATION_PATHS = {
    "office.crew": "/api/office/crew",
    "office.agent.record": "/api/office/agents/record",
    "office.agent.spawn": "/api/office/agents/spawn",
    "office.agent.wake": "/api/office/agents/wake",
    "office.agent.freeze": "/api/office/agents/freeze",
    "office.agent.rescue": "/api/office/agents/rescue",
    "office.agent.destroy": "/api/office/agents/destroy",
}


def _town() -> Town:
    from babo.config.loader import load_config

    return Town.open(load_config().baton.town_path)


def _manager() -> Any:
    """The native manager core. Until it lands, this raises and the page says so."""
    from babo.office.api import manager_for

    return manager_for(None)


_OPS: Any = None


def _unbuilt(said: str, listener: str) -> dict[str, Any]:
    """What the office looks like before its manager exists: honest, not empty.

    Desired records and crews are still the owner's, so they are listed; every
    agent is `unknown` because nothing can observe it yet, and the banner names
    the reason. No stub, no second core, no pretending.
    """
    from babo.baton import projects as project_board
    from babo.office.store import AgentStore, CrewStore

    town = _town()
    agents = AgentStore(town).all()
    return {
        "projects": [{"slug": p.slug, "title": p.title, "lead": CrewStore(town).read(p.slug).get("lead", ""),
                      "crew": CrewStore(town).read(p.slug).get("crew", []), "agents": []}
                     for p in project_board.all_projects(town)],
        "agents": [{"handle": handle, "resident": str(entry.get("resident") or ""), "project": str(entry.get("project") or ""),
                    "crew": str(entry.get("crew") or ""), "role": "", "status": "unknown",
                    "desired": str(entry.get("desired") or ""), "observed": None, "wg_address": "",
                    "last_activity_at": "", "checkouts": [], "ended_reason": "", "said": said}
                   for handle, entry in sorted(agents.items())],
        "missing": [], "drifted": [], "unmanaged": [],
        "manager": {"name": "native", "available": False, "said": said},
        "listener": listener, "desired": {h: dict(e) for h, e in agents.items()},
    }


def _listener() -> str:
    """Where this WebUI is bound, for the page to show as corroboration (never as auth).

    The WebUI is served by the websocket channel, not the gateway's /health
    server; in a pod those are different ports (UI 8843, health 18790), so
    reading gateway.host/port here would print a fact that is false exactly
    where the line is meant to help prove something.
    """
    try:
        from babo.config.loader import load_config

        channels = load_config().channels
        channel = cast(dict[str, Any], getattr(channels, "websocket", None) or {})
        host = str(channel.get("host") or "127.0.0.1")
        port = int(channel.get("port") or 8765)
        return f"{host}:{port}"
    except Exception:  # pragma: no cover - a read-only convenience line
        return ""


_ops_holder: list[Any] = []  # one slot: the gateway's record of actions in flight


def _ops() -> Any:
    """The gateway's one in-memory record of actions in flight.

    A one-slot holder rather than a module global: a global would be a constant
    reassigned at runtime, which is exactly the shape a type checker (and the
    next reader) is right to distrust.
    """
    if not _ops_holder:
        from babo.office.control import Ops

        _ops_holder.append(Ops())
    return _ops_holder[0]


def _text(payload: dict[str, Any], key: str, limit: int = 200) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BatonError(f"missing {key}")
    if len(value) > limit:
        raise BatonError(f"{key} is longer than {limit} characters")
    return value.strip()


# The UI does not execute lifecycle. It asks the Manager, and reports what the
# Manager said. The lifecycle call used to run the action in this process, which
# worked only while the UI was also the Manager — the hollow shell D-12 removes. A
# bypass that still works is the one nobody notices later, because it looks like
# success, so it is gone rather than demoted: there is no in-process fallback when
# the hop fails.
#
# hop.py is the contract of record. Five calls, one timeout, no retries, and the
# Manager's words are the verdict. This wrapper adds exactly one thing hop does not
# have: the name of the hole when there is no Manager to ask.
def _hop_action(handle: str, verb: str, reason: str, action_id: str | None) -> Response:
    from babo.office.actors import operator_actor
    from babo.office.hop import HopClient

    base = (os.environ.get("BABO_MANAGER_URL") or "").strip()
    if not base:
        # A named absence, not a quiet success and not a 500. Until the Manager's
        # listener lands there is nowhere to send this, and the page says so.
        return http_json_response(
            {
                "state": "unavailable",
                "said": ("no Manager is configured (BABO_MANAGER_URL is unset); lifecycle "
                         "actions are unavailable until the Manager's listener lands"),
            },
            status=503,
        )

    # The actor is the authenticated session, derived here. The request body never
    # supplies it: a client that names itself is not evidence.
    result = HopClient(base_url=base).act(handle, verb, reason,
                                          actor=operator_actor(), action_id=action_id)
    if result.ok:
        # pending / running / the closed terminal set, untouched. The Manager's
        # words are the verdict; this route adds no state of its own.
        return http_json_response(result.payload, status=result.status or 202)
    if result.status == 0:
        # Nothing answered. Not a refusal — an absence, and a different word.
        return http_json_response({"state": "unavailable", "said": result.said}, status=503)
    if not result.payload:
        # Something answered, but not with JSON: the page cannot read a verdict from it.
        return http_json_response({"state": "unknown", "said": result.said}, status=502)
    # A JSON answer that is not 200/202 is the Manager refusing, in its own words.
    return http_json_response(result.payload, status=result.status)


class OfficeRoutes:
    def __init__(self, *, authorized: Callable[[WsRequest], bool],
                 payload: Callable[[WsRequest], dict[str, Any] | None]) -> None:
        self._authorized = authorized
        self._payload = payload

    @staticmethod
    def is_mutation_path(path: str) -> bool:
        return path in OFFICE_MUTATION_PATHS.values()

    async def dispatch(self, request: WsRequest, got: str) -> Response | None:
        if got != "/api/office" and not got.startswith("/api/office/"):
            return None
        if not self._authorized(request):
            return http_error(401, "Unauthorized")
        try:
            return await self._route(request, got)
        except BatonError as exc:
            return http_error(400, str(exc))
        except OSError:
            logger.exception("office route {} failed", got)
            return http_error(500, "The office's files could not be read or written; see the gateway log.")
        except Exception as exc:
            logger.exception("office route {} failed", got)
            return http_error(500, f"Babo couldn't load this ({type(exc).__name__}: {exc}).")

    async def _route(self, request: WsRequest, got: str) -> Response | None:
        from babo.office import control

        if got == "/api/office":
            from babo.office.api import CoreNotBuiltError

            listener = _listener()
            try:
                core = _manager()
            except CoreNotBuiltError as exc:
                return http_json_response(_unbuilt(str(exc), listener))
            return http_json_response(await asyncio.to_thread(control.office_view, _town(), core, listener))
        if got.startswith("/api/office/ops/"):
            return http_json_response(await asyncio.to_thread(control.op_view, _ops(), got.rsplit("/", 1)[-1]))
        if got == OFFICE_MUTATION_PATHS["office.crew"]:
            return http_json_response(await asyncio.to_thread(control.change_crew, _town(), self._body(request)))
        if got == OFFICE_MUTATION_PATHS["office.agent.record"]:
            return http_json_response(await asyncio.to_thread(control.record_agent, _town(), self._body(request)))
        if got in OFFICE_MUTATION_PATHS.values() and got.startswith("/api/office/agents/"):
            body = self._body(request)
            verb = got.rsplit("/", 1)[-1]
            handle = _text(body, "handle", 63).lower()
            reason = str(body.get("reason") or "")[:400]
            replay = body.get("action_id")
            action_id = str(replay)[:64] if isinstance(replay, str) and replay.strip() else None
            return await asyncio.to_thread(_hop_action, handle, verb, reason, action_id)
        return http_error(404, "No such office route")

    def _body(self, request: WsRequest) -> dict[str, Any]:
        payload = self._payload(request)
        if not payload:
            raise BatonError("missing request body")
        return payload
