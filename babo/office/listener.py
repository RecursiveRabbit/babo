"""The Manager's listener: the six calls `hop` makes, and nothing else.

`hop.py` is the contract of record. This module is the server half of it, and it
is deliberately thin: it owns a socket, a peer identity and a dispatch table, and
it invents nothing. Every path here is a path the client already calls; every
answer is the service's `(status, payload)` passed through untouched.

Three rules, each of which is a row in `tests/baton/test_office_listener_contract.py`:

- **The peer is the socket address, never a header.** `X-Forwarded-For` is
  client-controlled; trusting it would make the trust list advisory. The address
  handed to the service is `self.client_address[0]` and nothing else.
- **The terminal vocabulary passes through.** `pending` and `running` stay what
  they are; a `202` stays a `202`; no state is defaulted here. If a word is
  missing it is missing, and the client says so.
- **The refusal names the source.** The service already names the peer it refused;
  the listener does not replace that sentence with a generic one.

Binding: loopback by default. Off-loopback is an explicit opt-in, and the boot
line says what that means.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

from babo.office.service import RENDER_UI_SOURCES, ManagerService, RenderIncompleteError

# Exactly the paths hop calls. The contract test derives its expectations from
# hop.py itself, so this table cannot quietly diverge from the client.
HEALTH = "/api/v1/office/health"
AGENTS = "/api/v1/office/agents"
ACTIONS = "/api/v1/office/actions"
RESTART_WRITE = "/api/v1/office/ui/restart"
RESTART_READ = "/api/v1/office/ui/restart"

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 18791


class _Handler(BaseHTTPRequestHandler):
    service: ManagerService
    server_version = "office-listener"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib hook name
        # One line per call, at the peer's own address: the log is evidence, and a
        # silent listener is how a seam gets debugged by guesswork.
        sys.stderr.write("office-listener %s %s\n" % (self.address_string(), format % args))

    # -- dispatch ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        self._dispatch("POST")

    def _peer(self) -> str:
        """The identity: the TCP peer. Never a header, never a body field."""
        return str(self.client_address[0])

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            loaded: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {}
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        svc = type(self).service
        peer = self._peer()

        try:
            if method == "GET" and path == HEALTH:
                status, payload = svc.health()
            elif method == "GET" and path == AGENTS:
                status, payload = svc.agents(peer)
            elif method == "POST" and path == ACTIONS:
                status, payload = svc.act(peer, self._body())
            elif method == "GET" and path.startswith(ACTIONS + "/"):
                status, payload = svc.action(peer, path.rsplit("/", 1)[-1])
            elif method == "POST" and path == RESTART_WRITE:
                status, payload = svc.restart_ui(peer, self._body())
            elif method == "GET" and path == RESTART_READ:
                status, payload = svc.restart_latest(peer)
            else:
                # A path hop does not call. Named, so a probe that guesses wrong
                # learns from the answer rather than from a stack trace.
                status, payload = 404, {"detail": f"no such office route: {method} {path}"}
        except Exception as exc:  # a listener must not die on one bad request
            status, payload = 500, {"detail": f"the listener could not answer ({type(exc).__name__}: {exc})"}

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(service: ManagerService, *, bind: str = DEFAULT_BIND, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Start the listener. Returns the server; the caller decides when to stop it."""
    handler = type("_BoundHandler", (_Handler,), {"service": service})
    return ThreadingHTTPServer((bind, port), handler)


def _declared_sources() -> str:
    """The door, as the render declares it.

    `BABO_TRUSTED_SOURCES` is the render's own key (service.RENDER_UI_SOURCES);
    `BABO_OFFICE_PEERS` is kept as a deployment alias for the same input. Neither
    is an admission policy of its own: both are passed INTO the render, and the
    render decides what is admissible.
    """
    return (os.environ.get(RENDER_UI_SOURCES)
            or os.environ.get("BABO_OFFICE_PEERS")
            or "")


def main() -> int:
    """Run the listener. Loopback unless BABO_OFFICE_BIND says otherwise."""
    from babo.office.api import manager_for

    bind = os.environ.get("BABO_OFFICE_BIND") or DEFAULT_BIND
    port = int(os.environ.get("BABO_OFFICE_PORT") or DEFAULT_PORT)

    # The render owns this door's addresses, so the production constructor goes
    # through it. Building ManagerService(ui_peers=...) here would make this the
    # second source of admission policy — the duplicate the retirement existed to
    # prevent — and would leave from_render with no production caller to keep it
    # honest.
    render = {RENDER_UI_SOURCES: _declared_sources()}
    try:
        office = ManagerService.from_render(core=manager_for(None), render=render)
    except RenderIncompleteError as exc:
        sys.stderr.write(f"office-listener FATAL: {exc}\n")
        return 2
    peers = office.ui_peers
    server = serve(office, bind=bind, port=port)
    if bind == DEFAULT_BIND:
        sys.stderr.write(f"office-listener on {bind}:{port} — loopback only; admitted peers: {', '.join(peers)}\n")
    else:
        sys.stderr.write(
            f"office-listener on {bind}:{port} — beyond loopback; every request is judged by its socket "
            f"peer, never a header, and the admitted peers are: {', '.join(peers)}\n"
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
