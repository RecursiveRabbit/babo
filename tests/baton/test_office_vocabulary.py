"""The closed action vocabulary is a partition of two doors, not one list.

F7 (2026-11-11, nime's review): ``AGENT_ACTIONS`` was derived by excluding a name
from ``ACTIONS`` — an allow-list built as a deny-list of one. The day a seventh
verb landed, it would have entered the agent door without anyone deciding that.
The doors are literals now, and this file is the decision record:

- the vocabulary is exactly the six frozen verbs, in order;
- the two doors union to it and do not intersect;
- every verb is in exactly one door.

Nothing here touches a runtime. It is a table, and the table is the point.
"""

from __future__ import annotations

from collections import Counter

from babo.office.api import ACTIONS, AGENT_ACTIONS, OPERATOR_ACTIONS

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
