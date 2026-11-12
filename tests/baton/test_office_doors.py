"""The two doors' addresses, rendered — not defaulted, and not fixtured.

nime's task, 2026-11-12. At ``467c5ad81`` ``operator_peers`` was a dataclass field
with no constructor anywhere in the tree: ``service.py:106`` declared it, ``:186``
read it, and the only things that ever built it were two test files. So
``restart-ui``'s host-WG admission was a code capability with no rendered entry —
the render's only trusted value for the manager role is the UI pod's
``10.0.0.11/32``. A host row against that render would prove the UI pod answers the
host (D12-2a) and *nothing* about the operator door (D12-2b), because the door had
no address to admit anyone from. That is the expensive near-proof: a green reported
as closing the operator door's host path while closing only the UI listener's.

Three rows, kept separate on purpose:

1. the constructor, populated from the render's own variable names and values;
2. ``restart-ui`` admitted from the host-WG address **through the constructor**;
3. the same verb refused from a second source, with the class it caught recorded.

The discriminator between 2a and 2b is the read path: the Manager's reads admit the
UI pod only. A host that answers ``agents()`` was admitted as a UI peer; a host that
answers only ``restart_ui()`` was admitted at the operator door. One service cannot
show both, and this file asserts which one it shows.

No pod, no listener, no daemon: nothing here is a served proof.
"""

from __future__ import annotations

import pytest

from babo.office import service
from babo.office.model import AgentObserved
from babo.office.service import ManagerService
from baton.office_fakes import FakeCore

# The render's two facts, as ``deploy/babo/entrypoint.sh`` resolves them for
# ``BABO_ROLE=manager``: the UI pod may call this Manager, and the host's WG
# address may carry the operator's verb. Two doors, two names, one address each.
UI = "10.0.0.11"
HOST = "10.0.0.2"
STRANGER = "10.0.0.9"

RENDER = {
    "BABO_TRUSTED_SOURCES": "10.0.0.11/32",   # the WebUI listener's only source: the UI pod
    "BABO_OPERATOR_SOURCES": "10.0.0.2/32",   # the operator door's only source: the host's WG
}


def _core() -> FakeCore:
    return FakeCore(agents_by_handle={
        service.UI_POD: AgentObserved(handle=service.UI_POD, state="alive")})


def test_the_render_populates_both_doors_and_no_default_stands_in_for_one() -> None:
    """The constructor reads the render's names; it does not choose an address.

    A door with no declared address is refused at construction rather than
    defaulted, because a default here would be this module inventing an operator —
    and the failure it produces later is a 403 that reads 'you are not the
    operator' when the truth is 'there is no door'.
    """
    svc = ManagerService.from_render(_core(), render=RENDER)
    assert svc.ui_peers == (UI,)
    assert svc.operator_peers == (HOST,)

    with pytest.raises(service.RenderIncompleteError) as refused:
        ManagerService.from_render(_core(), render={"BABO_TRUSTED_SOURCES": "10.0.0.11/32"})
    assert "BABO_OPERATOR_SOURCES" in str(refused.value), refused.value


def test_restart_ui_is_admitted_from_the_host_through_the_constructor() -> None:
    """Row 1: the host-WG address arrives from the render, not from a fixture."""
    core = _core()
    svc = ManagerService.from_render(core, render=RENDER)

    assert HOST not in svc.ui_peers, (
        "the host is not the UI pod: if it were in ui_peers, the 202 below would be "
        "a UI-door admission and would prove nothing about the operator door")
    status, payload = svc.restart_ui(HOST, {"reason": "invalidate sessions", "actor": "evans",
                                            "actor_source": "host-wg", "action_id": "r1"})
    assert status == 202, payload
    assert payload["status"] == "accepted" and payload["best_effort"] is True
    assert core.audit == [(service.UI_POD, "restart-ui", "evans", "host-wg")], (
        "the row names the pod, the operator and the door's provenance")


def test_restart_ui_is_refused_from_a_second_source_with_the_class_recorded() -> None:
    """Row 2: a stranger is refused at the door; an admitted door is not a principal."""
    core = _core()
    svc = ManagerService.from_render(core, render=RENDER)

    door_status, door_payload = svc.restart_ui(STRANGER, {"reason": "r", "actor": "evans",
                                                          "actor_source": "host-wg"})
    assert door_status == 403 and "not an admitted door" in door_payload["detail"], door_payload

    class_status, class_payload = svc.restart_ui(HOST, {"reason": "r", "actor": "evans",
                                                       "actor_source": "terminal"})
    assert class_status == 403 and "provenance is not the host operator" in class_payload["detail"]
    assert "'terminal'" in class_payload["detail"], (
        "the refusal names the class it caught, not just that something was wrong")
    assert not core.audit, "neither refusal reached the core: both were refused before effect"


def test_d12_2a_is_not_d12_2b() -> None:
    """The UI listener answering the host is a different row from the door admitting it.

    Same service, same address, two admissions that must not be read as one: the
    host is admitted to the operator verb and to no read. A green ``agents(HOST)``
    would mean the address had been placed in ``ui_peers`` — the 2a green wearing
    2b's name.
    """
    svc = ManagerService.from_render(_core(), render=RENDER)

    assert svc.agents(HOST)[0] == 403, "the host is not a UI peer; this is the 2a/2b seam"
    assert svc.agents(UI)[0] == 200
    assert svc.restart_ui(HOST, {"reason": "r", "actor": "evans",
                                "actor_source": "host-wg"})[0] == 202, (
        "and the host is admitted at the operator door — the second row, not the first")


def test_the_ui_roles_environment_cannot_stand_in_for_the_operator_door() -> None:
    """The same render file, the other role: on the UI pod the host *is* the trusted source.

    Building a Manager from that environment would put the host in ``ui_peers``,
    which is precisely the conflation 2a/2b exists to catch. It cannot happen by
    accident here: the operator door has its own name and no fallback.
    """
    with pytest.raises(service.RenderIncompleteError):
        ManagerService.from_render(_core(), render={"BABO_TRUSTED_SOURCES": "10.0.0.2/32"})


@pytest.mark.parametrize("declared", [
    "10.0.0.0/24",         # a prefix: peer_allowed is an exact match, so this would admit nobody, silently
    "10.0.0.2/32,",        # an empty entry is not an address
    "manager.example",     # a hostname never equals a socket peer
    "0.0.0.0/32",          # unspecified
    "127.0.0.1/32",        # loopback is not a source a remote caller arrives from
    "224.0.0.1/32",        # multicast
    "010.0.0.2/32",        # leading zero: a second spelling of one address
    "",                    # declared empty is not declared
    "   ",
])
def test_a_declared_source_that_cannot_be_a_caller_is_refused_by_name(declared: str) -> None:
    """The render validates with ``trusted_ok``; this is the door refusing to be lied to."""
    with pytest.raises(service.RenderIncompleteError) as refused:
        ManagerService.from_render(_core(), render={"BABO_TRUSTED_SOURCES": "10.0.0.11/32",
                                                   "BABO_OPERATOR_SOURCES": declared})
    assert "BABO_OPERATOR_SOURCES" in str(refused.value), refused.value
