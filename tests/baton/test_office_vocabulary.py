"""The closed action vocabulary is a partition of two doors, not one list.

F7 (2026-11-11, nime's review): ``AGENT_ACTIONS`` was derived by excluding a name
from ``ACTIONS`` — an allow-list built as a deny-list of one. The day a seventh
verb landed, it would have entered the agent door without anyone deciding that.
The doors are literals now, and this file is the decision record:

- the vocabulary is exactly the six frozen verbs, in order;
- the two doors union to it and do not intersect;
- every verb is in exactly one door.

Nothing here touches a runtime. It is a table, and the table is the point.

The event words are the same argument one level down (F13): a projection from
``(verb, state)`` onto a closed set, total over ``ACTIONS x TERMINAL``, closed
in both directions. A word no pair can produce is a dead word; a pair that
produces an undeclared word is a hole. Neither is allowed to be quiet.
"""

from __future__ import annotations

import logging
from collections import Counter

import pytest

from babo.office.api import ACTIONS, AGENT_ACTIONS, OPERATOR_ACTIONS, TERMINAL
from babo.office.audit import ACTION_EVENTS
from babo.office.audit import EVENTS as STORE_EVENTS
from babo.office.core import EVENT_FALLBACK, EVENT_TABLE, _event

# L-01's five, in order, plus L-10's amendment last.
FROZEN = ("spawn", "wake", "freeze", "rescue", "destroy", "restart-ui")
AGENT_DOOR = ("spawn", "wake", "freeze", "rescue", "destroy")
OPERATOR_DOOR = ("restart-ui",)


def test_the_vocabulary_is_the_frozen_six_in_order() -> None:
    # The order is load-bearing: it is the order refusals print and the page
    # offers. A seventh verb fails here.
    assert ACTIONS == FROZEN


def test_the_two_doors_partition_the_vocabulary() -> None:
    # Union covers, intersection is empty: no verb is in both doors and none is
    # in neither. This is the assertion that bites if `ACTIONS` is ever written
    # as a literal again beside the doors, or if a verb is handed to two doors.
    assert set(AGENT_ACTIONS) | set(OPERATOR_ACTIONS) == set(ACTIONS)
    assert set(AGENT_ACTIONS) & set(OPERATOR_ACTIONS) == set()
    counts = Counter((*AGENT_ACTIONS, *OPERATOR_ACTIONS))
    assert [verb for verb, seen in counts.items() if seen != 1] == []
    assert len(ACTIONS) == len(set(ACTIONS))


def test_each_verb_is_in_exactly_the_door_it_was_ruled_into() -> None:
    # Membership is a decision, spelled out. A seventh verb added to either tuple
    # fails here until someone edits this table on purpose — which is the point
    # of not deriving one list from the other.
    assert AGENT_ACTIONS == AGENT_DOOR
    assert OPERATOR_ACTIONS == OPERATOR_DOOR


# --- F13: the event vocabulary ----------------------------------------------
#
# The verbs above are the doors; their outcomes are a table. What this section
# refuses to allow is a word that no pair can produce (a dead word living for a
# year) or a pair that produces a word nobody declared.


def test_every_verb_and_state_has_a_cell_that_produces_a_declared_word() -> None:
    # Totality over ACTIONS x TERMINAL. The pairs are enumerated from the closed
    # sets, never from the table: a test that iterates its own subject passes
    # exactly when the subject shrinks, which is when it should fail.
    for verb in ACTIONS:
        for state in TERMINAL:
            assert (verb, state) in EVENT_TABLE, f"no event word for ({verb!r}, {state!r})"
            assert _event(verb, state) in ACTION_EVENTS


def test_the_event_vocabulary_is_closed_in_both_directions() -> None:
    # pair -> word: nothing outside the declared set is produced.
    # word -> pair: nothing declared is unreachable. One direction alone is how a
    # dead word lives for a year, which is why both are asserted here.
    assert set(EVENT_TABLE.values()) == set(ACTION_EVENTS)
    assert {verb for verb, _state in EVENT_TABLE} == set(ACTIONS)
    assert {state for _verb, state in EVENT_TABLE} == set(TERMINAL)


def test_the_action_vocabulary_is_part_of_the_store_vocabulary() -> None:
    # `finish_action` writes these words into the same audit table whose
    # vocabulary the store declares. A word here that is missing there would be a
    # column the store's own list denies.
    assert set(ACTION_EVENTS) <= set(STORE_EVENTS)


def test_the_fallback_is_not_a_word_in_the_vocabulary() -> None:
    # The belt is not a cell. If EVENT_UNMAPPED ever joins the set, the vocabulary
    # has grown a member that means "a member was missing".
    assert EVENT_FALLBACK not in ACTION_EVENTS
    assert EVENT_FALLBACK not in STORE_EVENTS


def test_an_unmapped_pair_is_named_loudly_and_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="babo.office.core"):
        assert _event("spawn", "halfway") == EVENT_FALLBACK
    assert "no event word mapped for ('spawn', 'halfway')" in caplog.text
    assert EVENT_FALLBACK in caplog.text


def test_the_six_rows_nime_reads_for() -> None:
    # The bar, as one table: each row is a pair and the word it must produce. The
    # rows that are reachable through a real action are also asserted there
    # (`test_office_core`); this is the vocabulary's copy of the same six.
    rows = {
        ("spawn", "timeout"): "SPAWN_TIMEOUT",
        ("freeze", "timeout"): "FREEZE_TIMEOUT",
        ("spawn", "failed"): "SPAWN_FAILED",
        ("spawn", "succeeded"): "SPAWN",          # `_settle`'s no-op
        ("destroy", "failed"): "TEARDOWN_PARTIAL",
        ("spawn", "halfway"): EVENT_FALLBACK,      # an unmapped pair
    }
    for (verb, state), word in rows.items():
        assert _event(verb, state) == word, (verb, state)
