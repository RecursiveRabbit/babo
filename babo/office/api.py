"""The Office interface: what the page and `babo office` may ask the core.

This module is the *interface* (dova's file). The implementation is
`babo/office/core.py` (the manager slice). The split is deliberate: the surface
cannot grow lifecycle logic, and the core cannot quietly widen what the UI may
do.

One product, one process. The Office page and `babo office` do not speak to a
second program over a wire: they call this interface, implemented inside Babo by
the deterministic manager core (lifecycle, authority, credentials, refusals).

What lives here is only the *contract*, plus the one honest answer for "the core
isn't built yet". The contract is deliberately small: the UI reads what the
runtime says and asks for two verbs; everything else — how pods are made, how
credentials are minted and revoked, how rescue preserves work — is the core's
business, and its rules are the ledger's, not this surface's.

Rules the implementation owes this interface (not restated anywhere else):

- **The runtime's word is the state word.** No guessing, no local re-mapping; a
  disagreement between the runtime and the record is reported as `unknown` with
  a `note`, never resolved by preference.
- **Lifecycle is terminal-state honest.** `succeeded | failed | refused |
  timeout` are distinct, and what separates them is whether the core accepted the
  action and whether the word asserts the effect:

  - `refused` — the core declined before acting.
  - `failed` — accepted, and returned an error; the effect is **not** asserted.
  - `timeout` — accepted, and no verdict arrived; the effect is **not** asserted.
    It covers both sites: an action interrupted before a verdict (the row's
    `started_at` is set) and a deadline that passed before anything was attempted
    (`started_at` is `NULL` — the machine-readable form of "nothing was
    attempted"). "Accepted" is the right noun for both: the core took the action
    on, and then either it was interrupted or its deadline expired. "Dispatched"
    would be false for the second site.
  - `succeeded` — accepted, and **the effect is asserted**: the pod is up, the
    work is frozen, the UI was replaced. The `202`'s honesty rests on this word
    meaning that; no other word may borrow it.

  When the effect is unknown, the row's own sentence says so; the choice of word
  records what was observed, never the effect. And when the core knows nothing was
  attempted, the row must say that rather than leave the reader to infer it.

  What lands here is decided by `runtime.py`'s classifier, not by the exit status.
  A non-zero `rc` naming the object (absent, "image not found") is an answer and
  becomes `failed`; one naming an unreachable service, or naming nothing we
  recognise, is silence and stays `timeout`. Silence is the default because
  claiming a verdict is the stronger claim. So a `timeout` row may mean the tool was
  not there, it timed out, or it exited with a message we could not read — and the
  row's own sentence, not the state word, says which. "Could not be read" stays
  where the read genuinely failed, and is deliberately absent from the executor's
  sentence, which also covers the message we could not read.
- **Verbs are idempotent.** Waking an awake agent is a success that says so;
  it is not an error and not a fake restart.
- **Credential rows carry identity only**: id, scope, issued/expires. The core
  never hands this surface a secret, and this surface never asks for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from babo.office.model import AgentObserved

# The closed action vocabulary is a partition of two doors, each written as a
# literal — never one list plus an exclusion. An allow-list built by filtering a
# name out is a deny-list of one, and a deny-list is exactly the row a seventh
# verb slips past the day someone adds it. `tests/baton/test_office_vocabulary.py`
# asserts the shape: the union of the doors is ACTIONS, the intersection is empty,
# every verb is in exactly one door, and each door's membership is a decision
# recorded here rather than a consequence of a filter.

# The five lifecycle verbs an agent handle may carry (L-01).
AGENT_ACTIONS = ("spawn", "wake", "freeze", "rescue", "destroy")

# The host operator's door: `restart-ui` is the cross-pod half of revocation — it
# asks the Manager to replace the UI pod, which invalidates every in-memory
# session by construction (D-12: revocation is owned by the pod holding the store).
# Its handle is the UI pod and its caller is the host operator (L-10's standing,
# ruled 2026-11-11), so it is never offered on an agent row and never accepted on
# the agent path. The authorizing class word is the *provenance*,
# `actor_source == "host-wg"`, not a literal actor token (soro's §8 ruling,
# corrected 2026-11-11); the actor is the operator's own name beside it.
OPERATOR_ACTIONS = ("restart-ui",)
OPERATOR_SOURCE = "host-wg"

# The one closed set the surface, the core and the tests agree on. Order matters:
# it is the order refusals print and the order the page offers.
ACTIONS = AGENT_ACTIONS + OPERATOR_ACTIONS

# Terminal states, verbatim. Anything else is still in flight.
TERMINAL = ("succeeded", "failed", "refused", "timeout")


class CoreNotBuiltError(Exception):
    """The native manager core has not landed yet (the ledger's slice is building it)."""


@dataclass(frozen=True)
class ActionRecord:
    """One action as the core records it: what happened, in its own words.

    The state is closed: ``pending``, ``running``, or one of the four terminal
    values. A core that invents a fifth word fails here, at construction, rather
    than reaching the page as a status nobody can render.
    """

    id: str
    handle: str
    action: str
    state: str = "pending"
    said: str = ""
    # The read half of the audit row (D-12's contradiction, ruled 2026-11-11):
    # the UI is the post-restart reader, so the row it polls must name who asked
    # and why. These are projection fields only — the write contract is unchanged,
    # and nothing here is a second store.
    actor: str = ""
    actor_source: str = ""
    reason: str = ""
    # When the row was created, projected for the same reason and under the same
    # rule: a reader that came up inside a restart has to tell *the restart that
    # made me* from *a restart aimed at me*, and without a timestamp it cannot.
    # The column already exists on the store row, so this is a projection and not
    # new state.
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.state not in ("pending", "running", *TERMINAL):
            raise ValueError(f"an action's state is pending, running or one of {TERMINAL}; got {self.state!r}")

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL


@runtime_checkable
class OfficeManager(Protocol):
    """What the Office UI/CLI may ask of the core. Nothing wider is available."""

    name: str

    def health(self) -> tuple[bool, str]:
        """Whether the core can act at all, and its own words if it can't."""
        ...

    def agents(self) -> list[AgentObserved]:
        """Every agent the core knows, as the runtime reports it."""
        ...

    def act(self, handle: str, action: str, reason: str, *,
            actor: str = "", actor_source: str = "", action_id: str | None = None) -> str:
        """Ask for one lifecycle action; returns the core's action id.

        ``actor`` is who is asking. The core refuses by name when it is absent —
        an action with no actor never takes effect, and the refusal says so
        rather than inventing a default. The product supplies it server-side
        (the owner, from the authenticated surface); it is never taken from a
        request body, because a client that names itself is not evidence.

        ``actor_source`` says how the surface obtained that name
        (``webui-session``, ``terminal``); a name with no provenance is not an
        identity, it is a string that satisfied a check.

        ``action_id`` is the caller's replay key. Replaying the same id returns
        the same action and does nothing; a different handle or verb under a
        taken id is refused. Without it there is nothing at the boundary for a
        replay rule to be explicit about.
        """
        ...

    def action(self, action_id: str) -> ActionRecord:
        """The core's record for one action, including its terminal state."""
        ...


def manager_for(_cfg: object = None) -> OfficeManager:
    """The core's entry point — one function, so the UI has one thing to call.

    Until the manager slice lands there is no core, and the product says so
    rather than pretending: the page renders `unavailable` with this sentence,
    and the CLI prints it. That is the honest state of a product whose manager
    is being built, not a fallback to some other runtime.

    R10: the interface takes no runtime handle. There is no socket path, no
    container id and no capability argument anywhere below — the UI cannot be
    handed a way to reach the runtime, even by mistake.
    """
    import importlib

    try:
        # Imported by name, not by a static `from … import`: the module may not
        # exist on this head, and a static import would be both a type-check
        # failure and a lie about the dependency.
        core = importlib.import_module("babo.office.core")
    except ModuleNotFoundError as exc:
        # Only the module's absence means "not built". A core that exists but
        # fails to import (missing dependency, renamed symbol) is *broken*, and a
        # broken core must never be reported to the operator as unbuilt — the
        # page would say "hasn't landed yet" while the truth is "it landed and
        # it does not work", which is the failure this check exists to prevent.
        if exc.name == "babo.office.core":
            raise CoreNotBuiltError(
                "the native manager core hasn't landed yet; the office is read-only until it does"
            ) from exc
        raise
    built = core.manager_for(_cfg)
    return cast(OfficeManager, built)
