"""The restart door's read half: what the pod that came up inside it can learn.

Contract v1 (bomu, ruled 2026-11-12 06:2x), as implemented here: one route,
``GET /api/v1/office/ui/restart``; one object, two methods; the store query is
parameterised **inside** and no caller-supplied handle or verb reaches it; the
envelope is always ``{"actions": [...], "count": n}`` in the single-row wire
names (``detail``, not ``said``); ``403`` for a non-``ui_peer``; ``503`` when the
store is unreadable, so the office looks broken rather than clean; ``404`` when no
``restart-ui`` row exists — never a ``200`` with an empty list; ``boot_id`` is not
exposed, because it is the Manager's boot and a pod correlating on it would answer
"the restart I came up inside" with a field that means something else.

The service cases run in process against the **real** core and the real sqlite
store, the way the ``153620531`` probe proved the join: ``act()`` writes the row,
the service reads it back. The listener is out of scope, has no owner and no
ruling — nothing here claims a served proof.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from babo.office import hop, service
from babo.office.audit import Store
from babo.office.core import NativeManager
from babo.office.credentials import CredentialLedger, FileAdapter
from babo.office.runtime import ContainerFacts, LaunchSpec
from baton.office_core_fakes import RecordingRuntime

UI_ADDR = "10.0.0.11"
OP_ADDR = "10.0.0.2"
UI_POD = "babo-ui"

NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731 - a clock, not a constant


# -- the real core, in process ----------------------------------------------
def _ui_pod(state: str = "running") -> ContainerFacts:
    return ContainerFacts(name=UI_POD, state=state, ip=UI_ADDR)


def _ui_spec() -> LaunchSpec:
    return LaunchSpec(name=UI_POD, image="babo-ui:test")


def _core(tmp_path: Path, runtime: RecordingRuntime, **kw: Any) -> NativeManager:
    ledger = CredentialLedger(Store(tmp_path / "m.db"), clock=NOW)
    ledger.registry.register(FileAdapter(tmp_path / "creds"))
    kw.setdefault("executor", lambda fn: fn())  # synchronous: no thread in these tests
    return NativeManager(store=Store(tmp_path / "m.db"), runtime=runtime, ledger=ledger,
                         clock=NOW, deadline=5.0, **kw)


def _svc(core: object, ui_peers: tuple[str, ...] = (UI_ADDR,),
         operator_peers: tuple[str, ...] = (OP_ADDR,)) -> service.ManagerService:
    return service.ManagerService(core=core, ui_peers=ui_peers, operator_peers=operator_peers)  # type: ignore[arg-type]


def _one_restart(tmp_path: Path, reason: str = "sessions leaked") -> tuple[NativeManager, str]:
    manager = _core(tmp_path, RecordingRuntime(facts={UI_POD: _ui_pod()}), ui_spec=_ui_spec)
    action_id = manager.act(UI_POD, "restart-ui", reason, actor="evans", actor_source="terminal")
    return manager, action_id


# -- client: the wire -------------------------------------------------------
def test_the_client_asks_the_restart_route_with_no_handle_and_no_verb() -> None:
    seen: list[dict[str, Any]] = []

    def transport(method: str, url: str, body: dict | None, timeout_s: float) -> tuple[int, str]:
        seen.append({"method": method, "url": url, "body": body})
        return 200, json.dumps({"actions": [], "count": 0})

    client = hop.HopClient("http://manager.invalid:8844", transport=transport)
    client.restart_latest()

    assert seen == [{"method": "GET", "url": "http://manager.invalid:8844/api/v1/office/ui/restart",
                     "body": None}]
    # The narrowing, at the only place it could leak: no query string, so there is
    # nothing to widen into `?handle=…&verb=…` later.
    assert "?" not in str(seen[0]["url"])


def test_a_404_is_an_answer_and_arrives_as_a_value() -> None:
    def transport(method: str, url: str, body: dict | None, timeout_s: float) -> tuple[int, str]:
        return 404, json.dumps({"detail": "no restart-ui row is recorded here"})

    result = hop.HopClient("http://manager.invalid:8844", transport=transport).restart_latest()

    assert result.ok is False and result.status == 404
    assert result.unavailable is True
    assert "no restart-ui row" in result.said
    # A page renders `unknown` from this without deciding what an empty list meant.
    assert result.payload == {"detail": "no restart-ui row is recorded here"}


def test_the_client_passes_the_envelope_through_untouched() -> None:
    row = {"state": "succeeded", "detail": "replaced", "id": "act-1", "handle": UI_POD,
           "action": "restart-ui", "actor": "evans", "actor_source": "terminal", "reason": "r"}

    def transport(method: str, url: str, body: dict | None, timeout_s: float) -> tuple[int, str]:
        return 200, json.dumps({"actions": [row], "count": 1})

    result = hop.HopClient("http://manager.invalid:8844", transport=transport).restart_latest()

    assert result.ok and result.payload == {"actions": [row], "count": 1}


# -- service: the join ------------------------------------------------------
def test_the_join_a_row_the_core_wrote_is_read_back_by_the_service(tmp_path: Path) -> None:
    """hop body -> service -> core -> store -> service. The real core, no double."""
    manager, action_id = _one_restart(tmp_path)

    status, payload = _svc(manager).restart_latest(UI_ADDR)

    assert status == 200
    assert payload["count"] == 1
    row = payload["actions"][0]
    assert row["id"] == action_id
    assert row["handle"] == UI_POD
    assert row["action"] == "restart-ui"
    assert row["state"] == "succeeded"
    assert row["actor"] == "evans" and row["actor_source"] == "terminal"
    assert row["reason"] == "sessions leaked"
    assert row["created_at"], "a reader must be able to tell this restart from a later one"
    assert datetime.fromisoformat(row["created_at"])
    assert "sessions minted before it died with the old process" in row["detail"]


def test_the_single_row_read_and_the_envelope_use_the_same_wire_names(tmp_path: Path) -> None:
    manager, action_id = _one_restart(tmp_path)
    svc = _svc(manager)

    _, envelope = svc.restart_latest(UI_ADDR)
    _, single = svc.action(UI_ADDR, action_id)

    # Contract §2: two endpoints, one spelling of each field. If anyone moves it,
    # they move both reads — this is what makes that a failing test rather than a
    # sentence in a document.
    assert set(envelope["actions"][0]) == set(single)
    assert envelope["actions"][0]["detail"] == single["detail"]
    # Contract §3: the Manager's boot is not the pod's boot.
    assert "boot_id" not in envelope["actions"][0]
    assert "boot_id" not in single


def test_the_newest_row_comes_first(tmp_path: Path) -> None:
    manager = _core(tmp_path, RecordingRuntime(facts={UI_POD: _ui_pod()}), ui_spec=_ui_spec)
    first = manager.act(UI_POD, "restart-ui", "first", actor="evans", actor_source="terminal")
    second = manager.act(UI_POD, "restart-ui", "second", actor="evans", actor_source="terminal")

    status, payload = _svc(manager).restart_latest(UI_ADDR, limit=2)

    assert status == 200 and payload["count"] == 2
    assert [row["id"] for row in payload["actions"]] == [second, first]
    assert [row["reason"] for row in payload["actions"]] == ["second", "first"]
    # "Newest first" is falsifiable by the caller rather than a claim the door
    # makes about itself: the timestamps have to run no later, earlier on.
    assert not any(row["created_at"] is None for row in payload["actions"])
    stamps = [row["created_at"] for row in payload["actions"]]
    assert stamps == sorted(stamps, reverse=True)


# -- service: the four answers ---------------------------------------------
def test_a_non_ui_peer_is_refused_with_a_403_and_gets_no_list(tmp_path: Path) -> None:
    manager, _ = _one_restart(tmp_path)
    status, payload = _svc(manager).restart_latest("10.0.0.99")
    assert status == 403 and "actions" not in payload
    assert "10.0.0.99 is not the UI pod" in payload["detail"]


def test_the_operator_host_does_not_read_the_pods_history(tmp_path: Path) -> None:
    # The write admits two doors; the read admits one. The operator's host has no
    # business reading the pod's own restart history, so it is not admitted here.
    manager, _ = _one_restart(tmp_path)
    status, payload = _svc(manager).restart_latest(OP_ADDR)
    assert status == 403 and "actions" not in payload


def test_no_restart_row_is_404_and_says_so(tmp_path: Path) -> None:
    # A core that has never restarted the UI: readable store, no row.
    manager = _core(tmp_path, RecordingRuntime(facts={UI_POD: _ui_pod()}), ui_spec=_ui_spec)
    status, payload = _svc(manager).restart_latest(UI_ADDR)
    assert status == 404
    assert "no restart-ui row is recorded here" in payload["detail"]
    assert "actions" not in payload


def test_absence_of_a_store_is_503_and_says_absence() -> None:
    # "No store" is not "no restart": a core that cannot be read is broken, and the
    # office must look broken rather than clean.
    svc = _svc(SimpleNamespace(health=lambda: (True, ""), agents=lambda: [], act=lambda *a, **k: "",
                               action=lambda *a, **k: None))
    status, payload = svc.restart_latest(UI_ADDR)
    assert status == 503
    assert "exposes no action store" in payload["detail"]
    assert "actions" not in payload


def test_a_store_that_raises_is_503_in_its_own_words(tmp_path: Path) -> None:
    manager, _ = _one_restart(tmp_path)

    def broken(**kwargs: Any) -> list[Any]:
        raise RuntimeError("database is locked")

    object.__setattr__(manager.store, "actions", broken)

    status, payload = _svc(manager).restart_latest(UI_ADDR)
    assert status == 503
    assert "could not be read" in payload["detail"] and "database is locked" in payload["detail"]
    assert "actions" not in payload


def test_a_store_whose_actions_is_not_callable_is_a_read_failure_not_an_absence() -> None:
    # `@runtime_checkable` checks that the attribute is *there*, not that it is a
    # store: this object has `actions` and is nothing like a store. The pre-check
    # lets it through by design, and the call reports it — which is why the two
    # failures must not share one sentence.
    svc = _svc(SimpleNamespace(store=SimpleNamespace(actions=("not", "callable"))))
    status, payload = svc.restart_latest(UI_ADDR)
    assert status == 503
    assert "could not be read" in payload["detail"]
    assert "not callable" in payload["detail"]


def test_a_state_word_the_surface_cannot_render_is_503() -> None:
    # A core bug must not reach a page as a fifth word — same guard as the
    # single-row read, on the same reasoning.
    bogus = SimpleNamespace(id="act-1", handle=UI_POD, verb="restart-ui", state="mostly-fine",
                            said="", actor="evans", actor_source="terminal", reason="r")
    svc = _svc(SimpleNamespace(store=SimpleNamespace(actions=lambda **k: [bogus])))
    status, payload = svc.restart_latest(UI_ADDR)
    assert status == 503 and "mostly-fine" in payload["detail"]


# -- the narrowing itself ---------------------------------------------------
def test_the_store_query_is_parameterised_inside_and_never_by_the_caller() -> None:
    class RecordingStore:
        def __init__(self) -> None:
            self.seen: list[dict[str, Any]] = []

        def actions(self, *, handle: str | None = None, verbs: Any = None,
                    limit: int = 200) -> list[Any]:
            self.seen.append({"handle": handle, "verbs": tuple(verbs or ()), "limit": limit})
            return []

    store = RecordingStore()
    svc = _svc(SimpleNamespace(store=store))

    svc.restart_latest(UI_ADDR, limit=7)

    # The pod is the row's handle and the door is the row's verb, both fixed here.
    # Nothing the caller sent shaped either one.
    assert store.seen == [{"handle": UI_POD, "verbs": ("restart-ui",), "limit": 7}]


def test_limit_is_bounded_and_zero_is_not_an_empty_answer() -> None:
    class RecordingStore:
        def __init__(self) -> None:
            self.seen: list[int] = []

        def actions(self, **kwargs: Any) -> list[Any]:
            self.seen.append(int(kwargs.get("limit") or 0))
            return []

    store = RecordingStore()
    svc = _svc(SimpleNamespace(store=store))

    for bad in (0, -1, service.RESTART_READ_MAX + 1):
        status, payload = svc.restart_latest(UI_ADDR, limit=bad)
        assert status == 400, bad
        assert str(service.RESTART_READ_MAX) in payload["detail"]
    assert store.seen == [], "an out-of-range limit is refused before the store is touched"
