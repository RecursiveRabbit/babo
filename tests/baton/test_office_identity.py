"""The identity provider and the writer behind it.

Four rows: the refusal names the key and the handle; the pair comes back when it
is there; the writer round-trips; and the runtime path has no reference to Rails
or to `AgentConfig`, so a later convenience import fails here rather than in a
production incident.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from babo.baton.town import Town
from babo.office import identity as identity_mod
from babo.office.core import Identity
from babo.office.store import AgentStore


@pytest.fixture()
def store(town: Town) -> AgentStore:
    return AgentStore(town)


def _record(store: AgentStore, handle: str = "crew-1") -> None:
    store.upsert({"handle": handle, "resident": "archivist", "project": "control-plane"})


def test_a_missing_identity_is_refused_by_name(store: AgentStore) -> None:
    with pytest.raises(identity_mod.IdentityMissing) as caught:
        identity_mod.identity_of(store, "ghost")
    assert "ghost" in str(caught.value), "the refusal names the handle"

    _record(store)
    with pytest.raises(identity_mod.IdentityMissing) as caught:
        identity_mod.identity_of(store, "crew-1")
    message = str(caught.value)
    assert "crew-1" in message and "identity" in message and "channel" in message, message


def test_the_pair_comes_back_when_both_keys_are_recorded(store: AgentStore) -> None:
    _record(store)
    store.set_identity("crew-1", "archivist", "silas")
    assert identity_mod.identity_of(store, "crew-1") == Identity("archivist", "silas")


def test_an_empty_channel_is_a_fact_not_a_gap(store: AgentStore) -> None:
    """The singleton case: both keys written, one of them empty."""
    _record(store)
    store.set_identity("crew-1", "archivist")
    assert identity_mod.identity_of(store, "crew-1") == Identity("archivist", "")


def test_the_writer_round_trips_through_an_unrelated_upsert(store: AgentStore) -> None:
    """Registration writes the pair; a later desired-state change must not drop it."""
    _record(store)
    store.set_identity("crew-1", "archivist", "silas")

    store.set_desired("crew-1", "frozen")           # an upsert that does not mention identity
    entry = store.get("crew-1")
    assert entry is not None
    assert entry["identity"] == "archivist" and entry["channel"] == "silas"
    assert entry["desired"] == "frozen"
    assert identity_mod.identity_of(store, "crew-1") == Identity("archivist", "silas")


def test_the_writer_refuses_what_it_cannot_name(store: AgentStore) -> None:
    with pytest.raises(Exception) as caught:
        store.set_identity("ghost", "archivist")
    assert "ghost" in str(caught.value)

    _record(store)
    with pytest.raises(Exception) as caught:
        store.set_identity("crew-1", "   ")
    assert "identity cannot be empty" in str(caught.value)


def test_the_runtime_path_never_consults_rails() -> None:
    """A grep row: `AgentConfig` is legacy, imported once at most, never at runtime.

    If someone reaches for the Rails table from the office line, this fails before
    it becomes a Manager that cannot start without a Rails process.
    """
    root = Path(__file__).resolve().parents[2] / "babo"
    offences: list[str] = []
    # The office line only: other channels have their own AgentConfig classes, and
    # a name that happens to collide is not a Rails reference.
    paths = [p for part in ("office", "webui") for p in sorted((root / part).rglob("*.py"))]
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in ("AgentConfig", "manager/app", "active_record", "ActiveRecord"):
            if needle in text:
                offences.append(f"{path.relative_to(root)}: {needle}")
    assert not offences, "the office line must not consult Rails at runtime: " + "; ".join(offences)
