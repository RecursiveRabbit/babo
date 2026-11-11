"""Who is asking, and where that answer came from.

A lifecycle action that changes a pod, or revokes a credential, must name the
person (or the seat) behind it — and the surface must not invent that name. Two
doors, two ways of obtaining it:

- the **web interface**: the operator's authenticated session. This product has
  one operator seat (the owner) reached over the WireGuard-permitted listener;
  the session is what proves someone is there, and `owner` is that seat's name.
  If a later ruling gives seats individual names, this is the one function that
  changes.
- the **terminal**: the operating-system user running the command, which is a
  real, checkable fact.

The actor travels as a name *plus* its source, so an audit row says both
(`owner`, `webui-session`) rather than leaving "a person approved" as a string
that merely happened to be non-empty.
"""

from __future__ import annotations

import getpass
from dataclasses import dataclass

from babo.baton.town import BatonError


@dataclass(frozen=True)
class Actor:
    """An obtained identity: the name, and how the surface came by it."""

    name: str
    source: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise BatonError("no actor: an action must name who is asking")
        if not self.source.strip():
            raise BatonError("no actor source: an action must say where the name came from")


def operator_actor() -> Actor:
    """The web interface's actor: the operator seat behind an authenticated session."""
    return Actor(name="owner", source="webui-session")


def terminal_actor(explicit: str = "") -> Actor:
    """The terminal's actor: whoever is running the command, checked at the OS."""
    name = explicit.strip() or getpass.getuser().strip()
    if not name:
        raise BatonError("no actor: this terminal has no user name to attribute the action to")
    return Actor(name=name, source="terminal")
