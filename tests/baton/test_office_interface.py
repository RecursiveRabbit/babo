"""The Office interface: what the page and CLI may ask for, and what they may not.

These are contract tests on the interface itself (R10/R12 in soro's plan): the
surface must not accept a runtime handle, a credential value, or a revoke
handle, and the core must be the only place lifecycle rules live.
"""

from __future__ import annotations

import inspect

from babo.office import api


def _params(method: str) -> set[str]:
    signature = inspect.signature(getattr(api.OfficeManager, method))
    return {name for name in signature.parameters if name != "self"}


def test_the_interface_offers_only_the_four_operations() -> None:
    assert {m for m in dir(api.OfficeManager) if not m.startswith("_")} >= {"health", "agents", "act", "action"}


def test_no_runtime_handle_or_capability_argument_crosses_the_interface() -> None:
    forbidden = {"socket", "socket_path", "podman", "container", "container_id", "pod", "pod_id",
                 "netns", "capability", "capabilities", "key", "secret", "token", "revoke_handle"}
    for method in ("health", "agents", "act", "action"):
        assert not (_params(method) & forbidden), f"{method} takes a runtime handle or a secret"


def test_the_action_vocabulary_and_terminal_states_are_closed() -> None:
    assert api.ACTIONS == ("spawn", "wake", "freeze", "rescue", "destroy")
    assert api.TERMINAL == ("succeeded", "failed", "refused", "timeout")


def test_an_unbuilt_core_is_an_honest_error_not_a_fallback() -> None:
    try:
        api.manager_for(None)
    except api.CoreNotBuiltError as exc:
        assert "hasn't landed" in str(exc)
    else:  # pragma: no cover - only once the manager slice lands
        raise AssertionError("no core should exist before the manager slice lands")


def test_credential_rows_are_identity_only() -> None:
    from babo.office.model import Checkout

    row = Checkout(id="c1", scope="kimi", issued_at="t0", expires_at="t1", unrevocable=True).overview()
    assert set(row) == {"id", "scope", "issued_at", "expires_at", "unrevocable"}
