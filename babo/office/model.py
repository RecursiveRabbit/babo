"""The office model: projects, crews, chiefs, residents, and the agents they run as.

The office is the social structure for work (manager, lead, crew, projects):
a project has one **lead** (a single agent) and a **crew** (every other agent
on it). There is no other role label; crew is the persistent grouping, not the
retired spawn-a-helper machinery (DESIGN 29e). A resident may be bound to one
agent in a NeoClaw pod. None of these grant access — what a resident may touch is its
profile, as always — and a crew is never ephemeral: it is a grouping over
persistent residents, not the removed spawn-a-helper machinery (DESIGN 29e).

Two kinds of record, kept apart on purpose:

- ``AgentDesired`` is what the owner said should be (``state/agents.json``).
  It is written only by the owner's configuration actions.
- ``AgentObserved`` is what the Manager says is (its ``/api/v1/office/state``).
  Babo never counts containers itself and holds no podman socket; every read
  is the Manager's answer, and every disagreement is named as one.

``AgentLive`` joins them, per the agreed contract with soro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

DESIRED_STATES = ("running", "frozen")

# The Manager's vocabulary, verbatim.
MANAGER_STATES = ("alive", "frozen", "starting", "dead", "unknown")

# Joined statuses, as the page shows them.
RUNNING = "running"
FROZEN = "frozen"
STARTING = "starting"
DEAD = "dead"
MISSING = "missing"  # configured, but the Manager doesn't know that agent
DRIFTED = "drifted"  # the Manager's state contradicts the desired record
UNMANAGED = "unmanaged"  # the Manager reports an agent nobody configured
UNKNOWN = "unknown"  # the Manager could not be read at all


@dataclass(frozen=True)
class Crew:
    """One project's lead agent, and the crew: every other agent on the project."""

    project: str
    lead: str = ""
    crew: tuple[str, ...] = ()

    def overview(self) -> dict[str, object]:
        return {"project": self.project, "lead": self.lead, "crew": list(self.crew)}

    def role_of(self, handle: str) -> str:
        if handle and handle == self.lead:
            return "lead"
        return "crew" if handle in self.crew else ""


@dataclass(frozen=True)
class AgentDesired:
    """One managed agent, as the owner configured it. Desired state only."""

    handle: str
    resident: str
    project: str = ""
    crew: str = ""
    desired: str = "running"  # running (awake) | frozen
    labels: dict[str, str] = field(default_factory=lambda: cast(dict[str, str], {}))
    created: str = ""
    updated: str = ""

    def overview(self) -> dict[str, object]:
        return {"handle": self.handle, "resident": self.resident, "project": self.project, "crew": self.crew,
                "desired": self.desired, "labels": dict(self.labels), "created": self.created, "updated": self.updated}


@dataclass(frozen=True)
class Checkout:
    """A live credential row, by identity only — never a value."""

    id: str
    scope: str = ""
    issued_at: str = ""
    expires_at: str = ""

    def overview(self) -> dict[str, object]:
        return {"id": self.id, "scope": self.scope, "issued_at": self.issued_at, "expires_at": self.expires_at}


@dataclass(frozen=True)
class AgentObserved:
    """One agent as the Manager reports it, read fresh."""

    handle: str
    state: str  # alive | frozen | starting | dead | unknown
    wg_address: str = ""
    last_activity_at: str = ""
    checkouts: tuple[Checkout, ...] = ()
    provenance: dict[str, str] = field(default_factory=lambda: cast(dict[str, str], {}))

    @property
    def ended_reason(self) -> str:
        """Why the last session ended, when the Manager recorded it (idle, context_limit, crash)."""
        return str(self.provenance.get("ended_reason") or "")

    def overview(self) -> dict[str, object]:
        return {"handle": self.handle, "state": self.state, "wg_address": self.wg_address,
                "last_activity_at": self.last_activity_at,
                "checkouts": [c.overview() for c in self.checkouts],
                "provenance": dict(self.provenance)}


@dataclass(frozen=True)
class AgentLive:
    """A desired record and the Manager's answer, joined without flattery."""

    handle: str
    resident: str
    project: str
    crew: str
    status: str
    role: str = ""  # lead | crew | ""
    desired: str | None = None
    observed: str | None = None
    wg_address: str = ""
    last_activity_at: str = ""
    checkouts: tuple[Checkout, ...] = ()
    ended_reason: str = ""
    said: str = ""

    def overview(self) -> dict[str, object]:
        return {"handle": self.handle, "resident": self.resident, "project": self.project, "crew": self.crew,
                "role": self.role, "status": self.status, "desired": self.desired, "observed": self.observed,
                "wg_address": self.wg_address, "last_activity_at": self.last_activity_at,
                "checkouts": [c.overview() for c in self.checkouts],
                "ended_reason": self.ended_reason, "said": self.said}


@dataclass(frozen=True)
class OpResult:
    """What a lifecycle action did, in the Manager's own words."""

    ok: bool
    said: str


_UP = ("alive", "starting")


def join(desired: AgentDesired | None, observed: AgentObserved | None) -> AgentLive:
    """Join one desired record and one Manager observation into the status the page shows."""

    if desired is None and observed is None:  # pragma: no cover - callers pass at least one
        raise ValueError("an agent needs a desired record or an observation")
    if desired is None:
        assert observed is not None
        return AgentLive(handle=observed.handle, resident="", project="", crew="", status=UNMANAGED,
                         observed=observed.state, wg_address=observed.wg_address,
                         last_activity_at=observed.last_activity_at, checkouts=observed.checkouts,
                         said="The Manager reports this agent, but no configuration records it here.")
    if observed is None:
        return AgentLive(handle=desired.handle, resident=desired.resident, project=desired.project,
                         crew=desired.crew, status=MISSING, desired=desired.desired,
                         said="Configured, but the Manager reports no such agent.")
    common = {"handle": desired.handle, "resident": desired.resident, "project": desired.project,
              "crew": desired.crew, "desired": desired.desired, "observed": observed.state,
              "wg_address": observed.wg_address, "last_activity_at": observed.last_activity_at,
              "checkouts": observed.checkouts, "ended_reason": observed.ended_reason}
    if observed.state == "alive" and desired.desired == "running":
        return AgentLive(status=RUNNING, **common)  # type: ignore[arg-type]
    if observed.state == "starting":
        return AgentLive(status=STARTING, **common)  # type: ignore[arg-type]
    if observed.state == "frozen" and desired.desired == "frozen":
        return AgentLive(status=FROZEN, **common)  # type: ignore[arg-type]
    if observed.state == "dead":
        # Dead means the pod is gone and the Manager has no graceful stand-down on
        # record (crash, or no ending recorded). That is the whole claim; repeat the
        # Manager's note rather than paraphrasing it, and name the record's
        # expectation when it differs. No page-side softening.
        note = str(observed.provenance.get("note") or "The Manager reports this agent dead.")
        if desired.desired == "frozen":
            note += " The record expected frozen (stood down with its work kept); this is not that."
        return AgentLive(status=DEAD, said=note, **common)  # type: ignore[arg-type]
    if observed.state == "frozen" and desired.desired == "running":
        return AgentLive(status=DRIFTED, said="The Manager reports it frozen; configuration says running.",
                         **common)  # type: ignore[arg-type]
    if observed.state == "alive" and desired.desired == "frozen":
        return AgentLive(status=DRIFTED, said="The Manager reports it alive; configuration says frozen.",
                         **common)  # type: ignore[arg-type]
    # The Manager reports an unknown state when its own sources disagree, and
    # names the disagreement in provenance.note. Repeat it — do not pick a winner.
    note = str(observed.provenance.get("note") or "")
    return AgentLive(status=UNKNOWN, said=note or f"The Manager says '{observed.state}'.", **common)  # type: ignore[arg-type]
