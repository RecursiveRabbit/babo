"""The office's event vocabulary: one table, one set, two readers.

F13 and F16. This module exists for one structural reason, and it is worth
stating rather than leaving to the import graph: the words are *derived* from a
table (an action's verb and its settled state), the core writes them, and the
store has to validate against the same set — `audit.insert_audit` is the only
validating write in the office. `core` imports `audit`, so `audit` cannot import
`core`; a leaf module that both can import is the shape that keeps one set of
words instead of two that drift.

Nothing here touches a runtime, a store, or a clock. It is a table.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from babo.office.api import ACTIONS, TERMINAL

# The only literal: one family base per verb. The suffixes follow `TERMINAL`, and
# the *domain* is generated from `ACTIONS x TERMINAL`, so a fifth terminal state
# arrives with its cells already present and no one has to remember to add them.
# `EVENT_OVERRIDES` is the one cell that does not follow the suffix rule, named in
# the table with its reason instead of in a prose comment a reader has to find.
EVENT_BASES: Mapping[str, str] = MappingProxyType({
    "spawn": "SPAWN",
    # wake gets its own base, never SPAWN. The *effect* branch in `_execute` is
    # shared (`("spawn", "wake")`) because the effect is one; the *word* is not,
    # because the event column is the closed, validated one while the verb column
    # is an input string. A vocabulary that merges two of its own inputs is a
    # lossy validator: a reader scanning the event column would lose a door the
    # row's unvalidated field still knows, and would have to trust that field to
    # get it back. F9's literals stay parked — this is a word, not a branch.
    "wake": "WAKE",
    "freeze": "FREEZE",
    "rescue": "RESCUE",
    "destroy": "TEARDOWN",
    "restart-ui": "UI_RESTART",
})

# The exception, in the table where a reader will look for it: revocation runs
# before removal, so a destroy that failed has already done part of itself.
# `PARTIAL` is true of it; `TEARDOWN_FAILED` would be a word no cell produces.
EVENT_OVERRIDES: Mapping[tuple[str, str], str] = MappingProxyType({
    ("destroy", "failed"): "TEARDOWN_PARTIAL",
})

# Not a word in the vocabulary: it is the evidence that a cell was missing.
EVENT_FALLBACK = "EVENT_UNMAPPED"


def _word(verb: str, state: str) -> str:
    """The suffix rule: `succeeded` is the family base, the rest take `_<STATE>`.

    `refused` is the exception the rule cannot express: a refusal is a non-event
    — the core declined before acting — so it gets no family word. The bare word
    is the marker that says *this row is not an event*, and it is only honest
    beside a sentence that names the verb.
    """
    if state == "refused":
        return "REFUSED"
    base = EVENT_BASES[verb]
    return base if state == "succeeded" else f"{base}_{state.upper()}"


EVENT_TABLE: Mapping[tuple[str, str], str] = MappingProxyType({
    (verb, state): EVENT_OVERRIDES.get((verb, state), _word(verb, state))
    for verb in ACTIONS for state in TERMINAL
})

# The closed set the *table* produces — not "the set an action row can produce":
# a row can carry `EVENT_FALLBACK`, and that word is deliberately outside this
# set, because it is not a word in the vocabulary but the evidence that a cell
# was missing.
ACTION_EVENTS: tuple[str, ...] = tuple(dict.fromkeys(EVENT_TABLE.values()))
