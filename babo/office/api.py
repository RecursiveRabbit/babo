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
  timeout` are distinct: `refused` means the core declined before acting,
  `failed` means it acted and broke, `timeout` means no verdict arrived.
- **Verbs are idempotent.** Waking an awake agent is a success that says so;
  it is not an error and not a fake restart.
- **Credential rows carry identity only**: id, scope, issued/expires. The core
  never hands this surface a secret, and this surface never asks for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from babo.office.model import AgentObserved

# The core's action vocabulary. The page currently exposes the first two.
ACTIONS = ("spawn", "wake", "freeze", "rescue", "destroy")

# Terminal states, verbatim. Anything else is still in flight.
TERMINAL = ("succeeded", "failed", "refused", "timeout")


class CoreNotBuiltError(Exception):
    """The native manager core has not landed yet (the ledger's slice is building it)."""


@dataclass(frozen=True)
class ActionRecord:
    """One action as the core records it: what happened, in its own words."""

    id: str
    handle: str
    action: str
    state: str = "pending"
    said: str = ""

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

    def act(self, handle: str, action: str, reason: str) -> str:
        """Ask for one lifecycle action; returns the core's action id."""
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
    try:
        from babo.office.core import manager_for as build  # the manager slice's entry point
    except ImportError as exc:  # the slice hasn't landed yet
        raise CoreNotBuiltError(
            "the native manager core hasn't landed yet; the office is read-only until it does"
        ) from exc
    return build(_cfg)
