"""The render's door, after the boundary ruling: one caller, no operator.

Evans ruled the boundary on 2026-11-12: *"No connection whatsoever. The manager is
not alive in this model. It has no state. It is an actuator for the UI, nothing
else. The UI can have any connections to the manager you wish, but it is the only
thing that talks to the manager about anything."*

So the operator door is retired, not deferred. This file holds the three rows that
make the retirement visible rather than assumed:

1. a render with no UI sources refuses at construction, naming the key it wanted
   (the rigour the door always had, kept for the door that remains);
2. a render that still declares ``BABO_OPERATOR_SOURCES`` is *ignored out loud* —
   warned about, not honoured, and shown not to have granted anything;
3. the service carries one peer list, so no code path can ask "is this the
   operator" — because nothing may be.

F17 is dead rather than fixed: nobody at ``10.0.0.2`` talks to the Manager at all,
so the address that used to be the operator's is now just an address that is not
the UI's. Nothing here is a served proof: the Manager is an object, not a process.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from babo.office import service
from babo.office.model import AgentObserved
from babo.office.service import ManagerService
from baton.office_fakes import FakeCore

# The render's one fact, as ``deploy/babo/entrypoint.sh`` resolves it for
# ``BABO_ROLE=manager``: the UI pod may call this Manager, and that is all.
UI = "10.0.0.11"
HOST = "10.0.0.2"        # was the operator door's source; now an address that is not the UI's
STRANGER = "10.0.0.9"

RENDER = {"BABO_TRUSTED_SOURCES": "10.0.0.11/32"}


def _core() -> FakeCore:
    return FakeCore(agents_by_handle={
        service.UI_POD: AgentObserved(handle=service.UI_POD, state="alive")})


def test_a_render_without_ui_sources_refuses_at_construction() -> None:
    """Absence of the one door is a refusal with a sentence, not a closed tuple.

    A Manager that starts with no admitted caller answers every request with
    `403`, which is also what a stranger gets — two facts that read alike in the
    only place a caller can see them. So the render must say who may call, and
    this refuses rather than defaulting to nobody.
    """
    with pytest.raises(service.RenderIncompleteError) as missing:
        ManagerService.from_render(_core(), render={})
    assert service.RENDER_UI_SOURCES in str(missing.value), missing.value

    # The retired key cannot stand in for the door that remains.
    with pytest.raises(service.RenderIncompleteError) as retired_only:
        ManagerService.from_render(_core(), render={"BABO_OPERATOR_SOURCES": HOST})
    assert service.RENDER_UI_SOURCES in str(retired_only.value), retired_only.value


def test_a_retired_operator_key_is_ignored_out_loud() -> None:
    """Present, warned about, and granting nothing — all three in one row.

    An ignored key is a future door: if the render still names an operator source
    and this module quietly drops it, the next reader cannot tell a retired key
    from one that was never meant to do anything. So the key warns, the peer list
    does not grow, and the address it names is refused at the only door there is.
    """
    with pytest.warns(service.RenderKeyRetiredWarning, match="BABO_OPERATOR_SOURCES") as warned:
        svc = ManagerService.from_render(_core(), render={**RENDER, "BABO_OPERATOR_SOURCES": HOST})
    assert "retired" in str(warned[0].message)

    assert svc.ui_peers == (UI,), "the retired key added nobody"
    status, payload = svc.restart_ui(HOST, {"reason": "r", "actor": "evans",
                                            "actor_source": "host-wg"})
    assert status == 403 and "is not the UI pod" in payload["detail"], payload


def test_the_service_has_one_peer_list_and_no_way_to_name_an_operator() -> None:
    """Structural, because the ruling is about what may exist, not what is used.

    A field named `operator_peers` would be a place for the next session to put an
    address back, and a branch reading it would be a code path that can ask "is
    this the operator". Neither may exist.
    """
    names = [f.name for f in dataclasses.fields(ManagerService)]
    assert names == ["core", "ui_peers"], names

    svc = ManagerService.from_render(_core(), render=RENDER)
    assert not hasattr(svc, "operator_peers")
    assert list(inspect.signature(ManagerService.__init__).parameters) == ["self", "core", "ui_peers"]


def test_the_ui_is_admitted_and_a_neighbour_address_is_not() -> None:
    """The allow-list of one, on the address the render declares."""
    core = _core()
    svc = ManagerService.from_render(core, render=RENDER)
    assert svc.ui_peers == (UI,)

    assert svc.agents(UI)[0] == 200
    assert svc.restart_ui(UI, {"reason": "invalidate sessions", "actor": "evans",
                               "actor_source": "host-wg"})[0] == 202
    assert core.audit == [(service.UI_POD, "restart-ui", "evans", "host-wg")]

    for outsider in (STRANGER, "10.0.0.20", HOST):
        status, payload = svc.agents(outsider)
        assert status == 403 and "is not the UI pod" in payload["detail"], (outsider, payload)
    assert len(core.audit) == 1, "the refusals left no row and the admission left exactly one"


@pytest.mark.parametrize("declared", [
    "10.0.0.0/24",         # a prefix: peer_allowed is an exact match, so this would admit nobody, silently
    "10.0.0.11/32,",       # an empty entry is not an address
    "manager.example",     # a hostname never equals a socket peer
    "0.0.0.0/32",          # unspecified
    "127.0.0.1/32",        # loopback is not a source a remote caller arrives from
    "224.0.0.1/32",        # multicast
    "010.0.0.11/32",       # leading zero: a second spelling of one address
])
def test_a_declared_source_that_cannot_be_a_caller_is_refused_by_name(declared: str) -> None:
    """The render validates with ``trusted_ok``; this is the door refusing to be lied to."""
    with pytest.raises(service.RenderIncompleteError) as refused:
        ManagerService.from_render(_core(), render={"BABO_TRUSTED_SOURCES": declared})
    assert service.RENDER_UI_SOURCES in str(refused.value), refused.value
