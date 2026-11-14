"""The listener against the client: the contract test that can fail when hop moves.

A hand-maintained list of routes on both sides passes while the two drift. This
file derives its expectations **from `hop.py`**: it drives every `HopClient`
method through a recording transport to learn the method and path each one calls,
then asserts the listener answers those paths — and answers nothing else.

If `hop` grows a call, this test fails until the listener serves it. That is the
only shape of contract test that can notice the client moving, which is what the
three signature mismatches in this seam already cost us once.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import fields as dataclass_fields
from typing import Any
from urllib.parse import urlsplit

from babo.office import hop, listener, service
from babo.office.actors import Actor
from babo.office.model import AgentObserved
from babo.office.service import ManagerService
from baton.office_fakes import FakeCore

UI = "127.0.0.1"


def _core() -> FakeCore:
    core = FakeCore(agents_by_handle={"crew-1": AgentObserved(handle="crew-1", state="frozen")})
    core.agents_by_handle[service.UI_POD] = AgentObserved(handle=service.UI_POD, state="alive")
    return core


def _served() -> tuple[ManagerService, Any, str]:
    svc = ManagerService(core=_core(), ui_peers=(UI,))
    server = listener.serve(svc, bind="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return svc, server, f"http://127.0.0.1:{server.server_address[1]}"


def _client_calls() -> list[tuple[str, str]]:
    """Every (method, path) HopClient knows how to make, learned from the client."""
    calls: list[tuple[str, str]] = []

    def transport(method: str, url: str, body: object, timeout_s: float) -> tuple[int, str]:
        calls.append((method, urlsplit(url).path))
        return 202, json.dumps({"action_id": "act-1", "state": "succeeded", "detail": "ok"})

    client = hop.HopClient("http://manager.invalid:8844", transport=transport)
    client.health()
    client.agents()
    client.act("crew-1", "wake", "reason", actor=Actor("owner", "webui-session"))
    client.action("act-1")
    client.restart_ui("reason", actor=Actor("host_operator", "host-wg"))
    client.restart_latest()
    return calls


def test_every_path_the_client_calls_is_answered_by_the_listener() -> None:
    # Growth fails here first. A hand-enumerated list of calls cannot notice a
    # seventh method, so the public surface of the client is asserted against the
    # six this file knows how to serve: adding a method to HopClient turns this row
    # red until it is both enumerated above and answered below.
    # Fields are excluded by construction: HopClient is a dataclass, so its fields
    # answer to dir() as surely as its methods do, and a field is not a call.
    fields = {field.name for field in dataclass_fields(hop.HopClient)}
    visible = {name for name in dir(hop.HopClient) if not name.startswith("_")} - fields
    assert visible == {
        "health", "agents", "act", "action", "restart_ui", "restart_latest",
    }, f"HopClient grew or lost a method ({sorted(visible)}); the listener must be updated with it"

    recorded = _client_calls()
    assert len(recorded) == 6, f"hop calls {len(recorded)} paths; this row expects six"

    _svc, server, base = _served()
    try:
        client = hop.HopClient(base)

        assert client.health().ok, "GET health"

        agents = client.agents()
        handles = [a["handle"] for a in agents.payload["agents"]]
        assert agents.ok and "crew-1" in handles, handles

        started = client.act("crew-1", "wake", "owner asked", actor=Actor("owner", "webui-session"))
        assert started.ok and started.status == 202 and started.payload["action_id"]

        settled = client.action(started.payload["action_id"])
        assert settled.ok and settled.payload["state"] == "succeeded"

        restarted = client.restart_ui("sessions leaked", actor=Actor("host_operator", "host-wg"))
        assert restarted.ok and restarted.status == 202

        # The read half is answered by the listener, but this fixture's core exposes
        # no action store, so the service answers 503 with its own sentence. What
        # this row proves is the dispatch: the path is served and the service spoke.
        # The 200-with-a-row case is tests/baton/test_office_restart_read.py, which
        # runs the real core and the real store.
        latest = client.restart_latest()
        assert latest.status == 503 and "no action store" in latest.said, latest.said
    finally:
        server.shutdown()
        server.server_close()


def test_the_listener_serves_no_path_the_client_does_not_call() -> None:
    _svc, server, base = _served()
    try:
        for path in ("/api/v1/office/unknown", "/api/v1/office/actions/x/y", "/api/v1/office/ui"):
            try:
                urllib.request.urlopen(base + path)  # noqa: S310 - loopback, test
                raise AssertionError(f"{path} was answered; the listener must serve only hop's paths")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404, path
        # and the six the client does call are the whole set
        served = {hop_path for _method, hop_path in _client_calls()}
        assert served == {listener.HEALTH, listener.AGENTS, listener.ACTIONS,
                          listener.ACTIONS + "/act-1", listener.RESTART_WRITE, listener.RESTART_READ}
        assert (listener.RESTART_WRITE == listener.RESTART_READ), \
            "the restart route is one path with two methods; the client calls both"
    finally:
        server.shutdown()
        server.server_close()


def test_the_peer_is_the_socket_address_and_a_header_cannot_change_it() -> None:
    svc = ManagerService(core=_core(), ui_peers=("10.9.9.9",))  # not us
    server = listener.serve(svc, bind="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = urllib.request.Request(base + listener.AGENTS,
                                         headers={"X-Forwarded-For": "10.9.9.9", "X-Real-IP": "10.9.9.9"})
        try:
            urllib.request.urlopen(request)  # noqa: S310 - loopback, test
            raise AssertionError("a header promoted the caller; the peer must be the socket address")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            detail = json.loads(exc.read().decode())["detail"]
            assert "127.0.0.1" in detail, "the refusal names the source it actually saw"
    finally:
        server.shutdown()
        server.server_close()


def test_the_terminal_vocabulary_passes_through_and_a_202_stays_a_202() -> None:
    _svc, server, base = _served()
    try:
        client = hop.HopClient(base)
        started = client.act("crew-1", "wake", "owner asked", actor=Actor("owner", "webui-session"))
        assert started.status == 202 and "state" not in started.payload, \
            "the door queues; it does not invent a state on the way out"
        settled = client.action(started.payload["action_id"])
        assert settled.payload["state"] == "succeeded"
    finally:
        server.shutdown()
        server.server_close()


def test_the_audit_row_is_quoted_with_actor_and_source() -> None:
    _svc, server, base = _served()
    try:
        client = hop.HopClient(base)
        started = client.act("crew-1", "freeze", "sessions leaked", actor=Actor("owner", "webui-session"))
        assert started.ok
        row = client.action(started.payload["action_id"]).payload
        assert row["actor"] == "owner" and row["actor_source"] == "webui-session"
        assert row["reason"] == "sessions leaked"
        assert row["handle"] == "crew-1" and row["action"] == "freeze"
        assert row["state"] in ("pending", "running", "succeeded", "failed", "refused", "timeout")
    finally:
        server.shutdown()
        server.server_close()
