"""Joining what the owner configured with what the Manager says — disagreements named."""

from __future__ import annotations

from babo.office import model


def _desired(**changes: object) -> model.AgentDesired:
    base = {"handle": "crew-1", "resident": "archivist", "project": "work", "desired": "running"}
    base.update(changes)
    return model.AgentDesired(**base)  # type: ignore[arg-type]


def _observed(**changes: object) -> model.AgentObserved:
    base = {"handle": "crew-1", "state": "alive", "wg_address": "10.9.0.5"}
    base.update(changes)
    return model.AgentObserved(**base)  # type: ignore[arg-type]


def test_configured_awake_and_alive_is_running() -> None:
    live = model.join(_desired(), _observed())
    assert live.status == model.RUNNING and live.said == "" and live.wg_address == "10.9.0.5"


def test_configured_frozen_and_frozen_is_frozen() -> None:
    live = model.join(_desired(desired="frozen"), _observed(state="frozen"))
    assert live.status == model.FROZEN


def test_starting_is_its_own_state() -> None:
    live = model.join(_desired(), _observed(state="starting"))
    assert live.status == model.STARTING


def test_configured_but_unknown_to_the_manager_is_missing_not_forgiven() -> None:
    live = model.join(_desired(), None)
    assert live.status == model.MISSING and "no such agent" in live.said


def test_frozen_against_a_running_configuration_is_drift_not_smoothed() -> None:
    live = model.join(_desired(desired="running"), _observed(state="frozen"))
    assert live.status == model.DRIFTED
    assert "frozen" in live.said and "running" in live.said


def test_dead_is_the_managers_fact_whatever_the_configuration() -> None:
    live = model.join(_desired(desired="frozen"), _observed(state="dead"))
    assert live.status == model.DEAD


def test_an_agent_nobody_recorded_is_unmanaged_never_absorbed() -> None:
    live = model.join(None, _observed())
    assert live.status == model.UNMANAGED and live.handle == "crew-1"


def test_a_manager_disagreement_is_unknown_and_repeats_its_note() -> None:
    live = model.join(_desired(), _observed(state="unknown",
                                            provenance={"podman": "exited", "record": "alive",
                                                        "note": "podman says exited; the Manager's record says alive"}))
    assert live.status == model.UNKNOWN
    assert "podman says exited" in live.said


def test_dead_after_a_frozen_record_says_both_facts_and_claims_neither() -> None:
    live = model.join(_desired(desired="frozen"), _observed(state="dead"))
    assert live.status == model.DEAD
    assert "dead" in live.said and "frozen" in live.said
    assert "wake it to find out" in live.said
