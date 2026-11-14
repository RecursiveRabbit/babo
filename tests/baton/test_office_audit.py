"""The durable record: legal transitions, one transaction, append-only audit."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from babo.office.audit import AuditRow, Store, StoreError

NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "m.db")


def _action(store: Store, action_id: str = "a1") -> str:
    store.create_action(action_id=action_id, handle="agent-a", verb="spawn", actor="evans",
                        reason="first", boot_id="b1", at=NOW())
    return action_id


def test_one_action_settles_once_and_its_audit_row_is_written_in_the_same_call(
    tmp_path: Path,
) -> None:
    # A-05 / R-08: the action row repeats the approval; the audit row repeats it.
    store = _store(tmp_path)
    action_id = _action(store)
    settled = store.finish_action(action_id, state="succeeded", said="spawned", at=NOW(),
                                  event="SPAWN", identity="kimi")
    assert settled.state == "succeeded" and settled.said == "spawned"
    (row,) = store.audit()
    assert (row.event, row.handle, row.actor, row.verb, row.reason, row.state, row.action_id) == (
        "SPAWN", "agent-a", "evans", "spawn", "first", "succeeded", action_id
    )
    assert row.identity == "kimi"


def test_a_second_finish_is_a_replay_not_a_second_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    action_id = _action(store)
    store.finish_action(action_id, state="succeeded", said="one", at=NOW(), event="SPAWN")
    again = store.finish_action(action_id, state="failed", said="two", at=NOW(), event="SPAWN_FAILED")
    assert again.state == "succeeded" and again.said == "one"
    assert len(store.audit()) == 1


def test_audit_rows_cannot_be_updated_or_deleted_even_by_sql(tmp_path: Path) -> None:
    # U-01 / D-9: the promise is enforced by the store, not by a comment.
    store = _store(tmp_path)
    action_id = _action(store)
    store.finish_action(action_id, state="succeeded", said="ok", at=NOW(), event="SPAWN")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE audit SET detail = 'rewritten'")  # noqa: SLF001 - testing the guard
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("DELETE FROM audit")  # noqa: SLF001 - testing the guard
    assert len(store.audit()) == 1


def test_the_store_has_no_audit_mutation_method(tmp_path: Path) -> None:
    # The absence is the guarantee: there is no update/delete path to forget.
    store = _store(tmp_path)
    assert {name for name in dir(store) if "audit" in name} == {"insert_audit", "audit"}


def test_an_unpreserved_event_name_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(StoreError) as caught:
        store.insert_audit(AuditRow(event="SOMETHING_NEW", handle="a", at=NOW()))
    assert "unknown audit event" in str(caught.value)


def test_a_duplicate_action_id_is_a_store_error_not_an_overwrite(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _action(store, "a1")
    with pytest.raises(StoreError) as caught:
        _action(store, "a1")
    assert "already exists" in str(caught.value)


def test_single_flight_is_per_handle_and_verb_and_expires(tmp_path: Path) -> None:
    # D-3: the durable key is (handle, verb); an expired claim is not in flight.
    store = _store(tmp_path)
    assert store.claim_or_read("agent-a", "spawn", "a1", "2026-01-02T00:00:00+00:00",
                               "2026-01-01T00:00:00+00:00") == "a1"
    assert store.claim_or_read("agent-a", "spawn", "a2", "2026-01-02T00:00:00+00:00",
                               "2026-01-01T00:00:00+00:00") == "a1"
    assert store.claim_or_read("agent-a", "wake", "a3", "2026-01-02T00:00:00+00:00",
                               "2026-01-01T00:00:00+00:00") == "a3"
    # an expired claim is not an action in flight: it is removed and replaced
    assert store.claim_or_read("agent-a", "spawn", "a4", "2026-01-04T00:00:00+00:00",
                               "2026-01-03T00:00:00+00:00") == "a4"


def test_only_legal_terminal_states_are_written(tmp_path: Path) -> None:
    store = _store(tmp_path)
    action_id = _action(store)
    with pytest.raises(StoreError) as caught:
        store.finish_action(action_id, state="running", said="no", at=NOW(), event="SPAWN")
    assert "not a terminal state" in str(caught.value)


def test_a_store_that_spans_the_changeover_still_orders_by_instant(tmp_path: Path) -> None:
    # Bomu's first measurement: `ORDER BY created_at DESC` is a **text** sort, so a
    # store holding rows written under two offsets sorts by spelling, not by time —
    # permanently, for every read. The store now writes one offset (UTC), so any row
    # it accepts is comparable; this writes both shapes through the public API.
    store = _store(tmp_path)
    # 19:00Z is 14:00 in Detroit; five minutes later, rendered in Detroit, the later
    # instant carries the *smaller* text. Text order and instant order disagree.
    store.create_action(action_id="A", handle="agent-a", verb="spawn", actor="evans",
                        reason="r", boot_id="b1", at="2026-11-12T19:00:00+00:00")
    store.create_action(action_id="B", handle="agent-a", verb="spawn", actor="evans",
                        reason="r", boot_id="b1", at="2026-11-12T14:05:00-05:00")

    rows = store.actions(handle="agent-a")
    assert [row.id for row in rows] == ["B", "A"], [(r.id, r.created_at) for r in rows]
    assert {row.created_at for row in rows} == {
        "2026-11-12T19:00:00+00:00", "2026-11-12T19:05:00+00:00",
    }


def test_a_claim_written_under_another_offset_still_expires(tmp_path: Path) -> None:
    # Bomu's second measurement: `expires_at <= ?` is a text comparison too, so a
    # claim stored at 19:00Z could never be expired by a `now` rendered as
    # 14:05-05:00 — the (handle, verb) pair stays refused until the clock's local
    # text passes the stored string. One offset in the store puts both sides of the
    # comparison in the same kind of string.
    store = _store(tmp_path)
    store.claim("agent-a", "spawn", "old-id", expires_at="2026-11-12T19:00:00+00:00")

    claimed = store.claim_or_read("agent-a", "spawn", "new-action",
                                  expires_at="2026-11-12T19:30:00+00:00",
                                  now="2026-11-12T14:05:00-05:00")

    assert claimed == "new-action"
    assert store.in_flight("agent-a", "spawn") == "new-action"
