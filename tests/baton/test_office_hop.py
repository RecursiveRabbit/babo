"""The UI→Manager hop: five calls in one direction, and the rules that guard them.

Client side: a failure is a value, the Manager's words are the verdict, and no
retry happens silently. Service side: only the UI pod gets in, actor and reason
are required, a replay key is the caller's, and the terminal set stays closed.
"""

from __future__ import annotations

import json

from babo.office import hop
from babo.office.actors import Actor
from babo.office.model import AgentObserved
from babo.office.service import ManagerService
from baton.office_fakes import FakeCore

UI = "10.0.0.5"


def _core(**kwargs: object) -> FakeCore:
    return FakeCore(agents_by_handle={"crew-1": AgentObserved(handle="crew-1", state="frozen")}, **kwargs)  # type: ignore[arg-type]


# -- client -----------------------------------------------------------------
def test_a_transport_failure_is_a_value_never_an_exception() -> None:
    def broken(method: str, url: str, body: object, timeout_s: float) -> tuple[int, str]:
        raise OSError("connection refused")

    client = hop.HopClient("http://10.0.0.3:9200", transport=broken)
    result = client.health()
    assert result.unavailable and "connection refused" in result.said
    assert result.payload == {}


def test_the_client_passes_the_managers_words_through_untouched() -> None:
    seen: list[dict[str, object]] = []

    def transport(method: str, url: str, body: dict | None, timeout_s: float) -> tuple[int, str]:
        seen.append({"method": method, "url": url, "body": body})
        return 202, json.dumps({"action_id": "act-1"})

    client = hop.HopClient("http://10.0.0.3:9200", transport=transport)
    result = client.act("crew-1", "wake", "owner asked", actor=Actor("owner", "webui-session"), action_id="k1")
    assert result.ok and result.payload["action_id"] == "act-1"
    assert seen[0]["body"] == {"handle": "crew-1", "action": "wake", "reason": "owner asked",
                               "actor": "owner", "actor_source": "webui-session", "action_id": "k1"}


def test_the_client_refuses_an_unknown_verb_without_a_round_trip() -> None:
    calls: list[object] = []

    def transport(*args: object) -> tuple[int, str]:  # pragma: no cover - must not be called
        calls.append(args)
        return 202, "{}"

    result = hop.HopClient("http://x", transport=transport).act("h", "explode", "r", actor=Actor("o", "terminal"))
    assert result.unavailable and "unknown action" in result.said and not calls


# -- service ----------------------------------------------------------------
def test_only_the_ui_pod_gets_in() -> None:
    svc = ManagerService(core=_core(), ui_peers=(UI,))
    assert svc.agents(UI)[0] == 200
    status, payload = svc.agents("10.0.0.99")
    assert status == 403 and "not the UI pod" in payload["detail"]
    # an exact match is the rule: a neighbour address is not "close enough"
    assert svc.act("10.0.0.50", {"handle": "crew-1", "action": "wake", "reason": "r",
                                 "actor": "owner", "actor_source": "webui-session"})[0] == 403


def test_an_anonymous_action_is_refused_before_any_effect() -> None:
    core = _core()
    svc = ManagerService(core=core, ui_peers=(UI,))
    status, payload = svc.act(UI, {"handle": "crew-1", "action": "wake", "reason": "r"})
    assert status == 400 and "must name who is asking" in payload["detail"]
    assert not core.audit, "no effect without an actor"


def test_actor_and_reason_travel_to_the_core_with_their_source() -> None:
    core = _core()
    svc = ManagerService(core=core, ui_peers=(UI,))
    status, payload = svc.act(UI, {"handle": "crew-1", "action": "wake", "reason": "owner asked",
                                   "actor": "owner", "actor_source": "webui-session"})
    assert status == 202 and payload["action_id"]
    assert core.audit[-1] == ("crew-1", "wake", "owner", "webui-session")


def test_a_replayed_key_answers_202_and_the_refusal_is_read_as_a_row() -> None:
    """H-1: a duplicate is not a transport error.

    The core records a refused row and returns its id; the UI polls it like every
    other refusal. A 409 would leave the refusal visible only as a status code
    while the row sat unread.
    """
    svc = ManagerService(core=_core(), ui_peers=(UI,))
    body = {"handle": "crew-1", "action": "wake", "reason": "r", "actor": "owner",
            "actor_source": "webui-session", "action_id": "k1"}
    first = svc.act(UI, dict(body))
    again = svc.act(UI, dict(body))
    assert first[0] == again[0] == 202 and first[1]["action_id"] == again[1]["action_id"] == "k1"
    conflict = svc.act(UI, {**body, "action": "freeze"})
    assert conflict[0] == 202, "a conflicting replay is a refused row, not a 409"
    assert svc.action(UI, conflict[1]["action_id"])[1]["state"] == "refused"


def test_an_unknown_field_is_refused_rather_than_ignored() -> None:
    svc = ManagerService(core=_core(), ui_peers=(UI,))
    status, payload = svc.act(UI, {"handle": "crew-1", "action": "wake", "reason": "r", "actor": "o",
                                   "actor_source": "terminal", "socket": "/run/podman.sock"})
    assert status == 400 and "unknown field" in payload["detail"]


def test_an_unknown_action_id_is_404_not_an_invented_failure() -> None:
    svc = ManagerService(core=_core(), ui_peers=(UI,))
    assert svc.action(UI, "nope")[0] == 404


def test_a_degraded_core_is_503_with_its_own_words() -> None:
    svc = ManagerService(core=_core(unavailable="podman socket unreadable"), ui_peers=(UI,))
    status, payload = svc.health()
    assert status == 503 and payload["available"] is False
    assert "unreadable" in payload["detail"]


def test_restart_ui_is_an_action_not_a_side_door() -> None:
    """H-3: same actor/reason rule, same closed states, same idempotency key."""
    core = _core()
    core.agents_by_handle["ui"] = AgentObserved(handle="ui", state="alive")
    svc = ManagerService(core=core, ui_peers=(UI,))
    assert svc.restart_ui("10.0.0.99", {"reason": "r", "actor": "o", "actor_source": "terminal"})[0] == 403
    assert svc.restart_ui(UI, {"reason": "r", "actor": "o"})[0] == 400
    status, payload = svc.restart_ui(UI, {"reason": "invalidate sessions", "actor": "owner",
                                          "actor_source": "webui-session", "action_id": "r1"})
    assert status == 202
    assert core.audit[-1][1] == "restart-ui"
    assert svc.action(UI, payload["action_id"])[1]["state"] == "succeeded"
