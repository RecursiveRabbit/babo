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
    "office.agent.wake": "/api/office/agents/wake",
    "office.agent.freeze": "/api/office/agents/freeze",
}


def _town() -> Town:
    from babo.config.loader import load_config

    return Town.open(load_config().baton.town_path)


def _backend() -> Any:
    from babo.config.loader import load_config
    from babo.office.backend import from_config

    return from_config(load_config().baton)


_OPS: Any = None


def _listener() -> str:
    """Where this WebUI is bound, for the page to show as corroboration (never as auth)."""
    try:
        from babo.config.loader import load_config

        gateway = load_config().gateway
        return f"{gateway.host}:{gateway.port}"
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
            listener = _listener()
            return http_json_response(await asyncio.to_thread(control.office_view, _town(), _backend(), listener))
        if got.startswith("/api/office/ops/"):
            return http_json_response(await asyncio.to_thread(control.op_view, _ops(), got.rsplit("/", 1)[-1]))
        if got == OFFICE_MUTATION_PATHS["office.crew"]:
            return http_json_response(await asyncio.to_thread(control.change_crew, _town(), self._body(request)))
        if got == OFFICE_MUTATION_PATHS["office.agent.record"]:
            return http_json_response(await asyncio.to_thread(control.record_agent, _town(), self._body(request)))
        if got in (OFFICE_MUTATION_PATHS["office.agent.wake"], OFFICE_MUTATION_PATHS["office.agent.freeze"]):
            body = self._body(request)
            verb = "wake" if got.endswith("/wake") else "freeze"
            handle = _text(body, "handle", 63).lower()
            reason = str(body.get("reason") or "")[:400]
            # The record read is small; keeping it on this loop lets the action's
            # follow-up task be created here, with the Manager call in a thread.
            op = control.begin(_town(), _backend(), _ops(), handle, verb, reason)
            return http_json_response({"state": "pending", "op": op.overview()}, status=202)
        return http_error(404, "No such office route")

    def _body(self, request: WsRequest) -> dict[str, Any]:
        payload = self._payload(request)
        if not payload:
            raise BatonError("missing request body")
        return payload
