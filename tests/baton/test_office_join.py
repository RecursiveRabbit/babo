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


def test_dead_against_a_frozen_record_names_both_facts_without_softening() -> None:
    # The Manager's discriminator: dead = no pod AND no graceful stand-down recorded.
    live = model.join(_desired(desired="frozen"),
                      _observed(state="dead", provenance={"podman": "absent", "record": "inactive",
                                                          "note": "pod gone with no graceful stand-down on record"}))
    assert live.status == model.DEAD
    assert "no graceful stand-down" in live.said
    assert "not that" in live.said


def test_a_graceful_stand_down_is_frozen_and_says_why() -> None:
    live = model.join(_desired(desired="frozen"),
                      _observed(state="frozen", provenance={"podman": "absent", "record": "inactive",
                                                            "ended_reason": "idle",
                                                            "note": "stood down (idle); work preserved"}))
    assert live.status == model.FROZEN and live.ended_reason == "idle"


def test_a_frozen_row_repeats_the_cores_own_reason_verbatim() -> None:
    """A stand-down the core initiated must not read as a session that ended by
    itself: the reason is shown as the core wrote it, not mapped to a nicer word."""
    live = model.join(_desired(desired="frozen"),
                      _observed(state="frozen",
                                provenance={"note": "stood down by the core; work preserved",
                                            "ended_reason": "standdown"}))
    assert live.status == model.FROZEN
    assert live.ended_reason == "standdown"
    assert live.said == "stood down by the core; work preserved"


def test_an_unknown_ended_reason_is_shown_verbatim_not_translated() -> None:
    live = model.join(_desired(desired="frozen"),
                      _observed(state="frozen", provenance={"ended_reason": "context_limit"}))
    assert live.ended_reason == "context_limit"
