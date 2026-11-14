"""Who a handle is: the provider the core was missing.

`spawn` refuses without an identity — *"no identity/channel recorded for {handle}"*
— and `NativeManager` took that from an injected `_identity_of` callable with no
caller. This is the source of truth for it: the office line's own store
(`state/agents.json`), never Rails.

**Absence is a property of the key, not of the string.** `channel` may be empty:
that is the singleton case the renderer expresses as an absent channel, and it is
a fact about the agent rather than a gap. What is refused is an entry that was
never asked to hold an identity at all, and the refusal names the handle and the
missing key rather than calling the agent invalid.
"""

from __future__ import annotations

from babo.baton.town import BatonError
from babo.office.core import Identity
from babo.office.store import AgentStore

IDENTITY_KEYS = ("identity", "channel")


class IdentityMissing(BatonError):
    """A handle with no recorded identity, named so the caller can fix it."""


def identity_of(store: AgentStore, handle: str) -> Identity:
    """The identity and channel recorded for one handle, or a refusal by name."""
    entry = store.get(handle)
    if entry is None:
        raise IdentityMissing(
            f"no agent '{handle}' is recorded here, so it has no identity; registration comes first"
        )
    missing = [key for key in IDENTITY_KEYS if key not in entry]
    if missing:
        raise IdentityMissing(
            f"agent '{handle}' has no recorded {', '.join(missing)}; "
            "registration must write both keys (set_identity) before it can spawn"
        )
    identity = str(entry["identity"]).strip()
    if not identity:
        raise IdentityMissing(f"agent '{handle}' has an empty identity; that is not a name")
    return Identity(identity=identity, channel=str(entry["channel"]).strip())
