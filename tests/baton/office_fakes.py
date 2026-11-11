"""A deterministic double for the Office interface — a test fixture, not a core.

It exists so the product's own surfaces (join, control, routes, CLI) can be
tested before the manager slice lands. It implements `babo.office.api.
OfficeManager` and nothing else: no lifecycle policy, no persistence, no
credentials. When the core lands, these tests keep working with `FakeCore` and
the core gets its own suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from babo.office.api import ActionRecord
from babo.office.model import AgentObserved


@dataclass
class FakeCore:
    name: str = "fake"
    agents_by_handle: dict[str, AgentObserved] = field(default_factory=dict)
    fail: set[str] = field(default_factory=set)  # action names that come back `failed`
    unavailable: str = ""
    actions: dict[str, ActionRecord] = field(default_factory=dict)
    _next: int = 0

    def health(self) -> tuple[bool, str]:
        return (False, self.unavailable) if self.unavailable else (True, "fake core")

    def agents(self) -> list[AgentObserved]:
        if self.unavailable:
            from babo.office.api import CoreNotBuiltError

            raise CoreNotBuiltError(self.unavailable)
        return list(self.agents_by_handle.values())

    def act(self, handle: str, action: str, reason: str) -> str:
        del reason
        if self.unavailable:
            from babo.office.api import CoreNotBuiltError

            raise CoreNotBuiltError(self.unavailable)
        if handle not in self.agents_by_handle:
            raise ValueError(f"refused: unknown handle {handle}")
        self._next += 1
        action_id = f"act-{self._next}"
        self.actions[action_id] = ActionRecord(id=action_id, handle=handle, action=action)
        return action_id

    def action(self, action_id: str) -> ActionRecord:
        record = self.actions.get(action_id)
        if record is None:
            from babo.office.api import CoreNotBuiltError

            raise CoreNotBuiltError(f"no such action: {action_id}")
        if record.state in ("succeeded", "failed", "refused", "timeout"):
            return record
        handle, action = record.handle, record.action
        if action in self.fail:
            settled = ActionRecord(id=action_id, handle=handle, action=action,
                                   state="failed", said=f"fake: {action} {handle} failed at the runtime")
        elif action == "wake":
            settled = ActionRecord(id=action_id, handle=handle, action=action,
                                   state="succeeded", said=f"woke {handle}")
            self._set_state(handle, "alive")
        elif action == "freeze":
            settled = ActionRecord(id=action_id, handle=handle, action=action,
                                   state="succeeded", said=f"froze {handle}: stood down, work pushed, pod released")
            self._set_state(handle, "frozen")
        else:
            settled = ActionRecord(id=action_id, handle=handle, action=action,
                                   state="refused", said=f"fake doesn't run '{action}'")
        self.actions[action_id] = settled
        return settled

    def _set_state(self, handle: str, state: str) -> None:
        current = self.agents_by_handle[handle]
        self.agents_by_handle[handle] = AgentObserved(
            handle=handle, state=state, wg_address=current.wg_address,
            last_activity_at=current.last_activity_at, checkouts=current.checkouts,
            provenance=current.provenance)
