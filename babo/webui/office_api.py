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
from collections.abc import Callable
from typing import Any

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

        channel = load_config().channels.websocket
        config = channel if isinstance(channel, dict) else {}
        host = str(config.get("host") or "127.0.0.1")
        port = int(config.get("port") or 8765)
        return f"{host}:{port}"
    except Exception:  # pragma: no cover - a read-only convenience line
        return ""


def _ops() -> Any:
    """The gateway's one in-memory record of actions in flight."""
    global _OPS
    if _OPS is None:
        from babo.office.control import Ops

        _OPS = Ops()
    return _OPS


def _text(payload: dict[str, Any], key: str, limit: int = 200) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BatonError(f"missing {key}")
    if len(value) > limit:
        raise BatonError(f"{key} is longer than {limit} characters")
    return value.strip()


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
            # The record read is small; keeping it on this loop lets the action's
            # follow-up task be created here, with the Manager call in a thread.
            from babo.office.actors import operator_actor

            # The actor is the authenticated operator session, obtained here — the
            # request body never supplies it (a client that names itself is not
            # evidence), and there is no constant default to fall back on.
            op = control.begin(_town(), _manager(), _ops(), handle, verb, reason,
                               actor=operator_actor(), action_id=action_id)
            return http_json_response({"state": "pending", "op": op.overview()}, status=202)
        return http_error(404, "No such office route")

    def _body(self, request: WsRequest) -> dict[str, Any]:
        payload = self._payload(request)
        if not payload:
            raise BatonError("missing request body")
        return payload
