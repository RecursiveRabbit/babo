"""The pod renderer: what an agent's pod is, ported from the retired oracle.

`spec_for(handle, identity)` is the callable `NativeManager` takes and, until now,
nothing passed. The definition is not invented here — every field names the line
it came from in `neoclaw-rails`, which is spec and not runtime:

    name      spawner.rb:202-205   identity if the config is singleton, else "identity-channel"
    image     podman.rb:38         Surface.agent_image
    network   podman.rb:32         Surface.agent_network
    cap_add   podman.rb:37         NET_ADMIN
    mounts    podman.rb:33-34      host_spawn_dir/<name>.json:/run/secrets/spawn.json:ro
                                   host_claude_dir:/run/secrets/claude:ro
    hostname  podman.rb:31         --hostname <instance_name>
    memory    podman.rb:35         Settings.resources.container_memory
    cpus      podman.rb:36         Settings.resources.container_cpus

and two absences that are load-bearing rather than omissions: the oracle passes
**no `-e` and no command**. An agent's identity arrives through the mounted
`spawn.json` secret, never through environment or argv — the same rule as
identity never coming from model-authored arguments, applied to the pod itself.
`env == ()` and `command == ()` are therefore asserted by the row, so a later
"helpful" `-e` fails it.

No value here has a code default. A defaulted memory limit is a substituted value
that reads like a considered one, so a missing key is a refusal that names it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from babo.office import vocabulary
from babo.office.core import Identity
from babo.office.runtime import LaunchSpec, Mount

# The keys this renderer needs, each named as the oracle names it.
SURFACE_KEYS = (
    "agent_image",          # podman.rb:38
    "agent_network",        # podman.rb:32
    "host_spawn_dir",       # podman.rb:33 (Surface.host_spawn_dir)
    "host_claude_dir",      # podman.rb:34 (Surface.host_claude_dir)
    "container_memory",     # podman.rb:35
    "container_cpus",       # podman.rb:36
)

SPAWN_DESTINATION = "/run/secrets/spawn.json"
CLAUDE_DESTINATION = "/run/secrets/claude"


class RenderIncompleteError(ValueError):
    """A surface value the render cannot do without, named rather than defaulted."""


@dataclass(frozen=True)
class Surface:
    """The configuration a pod render needs. Every field is required."""

    agent_image: str
    agent_network: str
    host_spawn_dir: str
    host_claude_dir: str
    container_memory: str
    container_cpus: str


def surface_from(values: Mapping[str, str]) -> Surface:
    """A surface from configuration, refusing by name when a key is absent."""
    missing = [key for key in SURFACE_KEYS if not str(values.get(key) or "").strip()]
    if missing:
        raise RenderIncompleteError(
            "the pod render cannot run without: "
            + ", ".join(missing)
            + " — each is a value the retired manager's scripts set, and none has a default here"
        )
    return Surface(
        agent_image=str(values["agent_image"]).strip(),
        agent_network=str(values["agent_network"]).strip(),
        host_spawn_dir=str(values["host_spawn_dir"]).strip(),
        host_claude_dir=str(values["host_claude_dir"]).strip(),
        container_memory=str(values["container_memory"]).strip(),
        container_cpus=str(values["container_cpus"]).strip(),
    )


def instance_name(identity: Identity) -> str:
    """The pod's name: `spawner.rb:202-205`, with the singleton case expressed as
    an absent channel rather than as a second flag to keep in step.

    The rule itself lives in `vocabulary.instance_name` so the core can resolve a
    handle through the same producer before it inspects a pod. Two derivations of
    one name is how `nothing to destroy` happens while the pod is running.
    """
    return vocabulary.instance_name(identity.identity, identity.channel)


def spec_for(handle: str, identity: Identity, *, surface: Surface) -> LaunchSpec:
    """The agent pod. One handle, one identity, every field traceable."""
    name = instance_name(identity)
    return LaunchSpec(
        name=name,
        image=surface.agent_image,
        # No env and no command, on purpose: identity arrives in spawn.json.
        mounts=(
            Mount(source=f"{surface.host_spawn_dir}/{name}.json", destination=SPAWN_DESTINATION),
            Mount(source=surface.host_claude_dir, destination=CLAUDE_DESTINATION),
        ),
        network=surface.agent_network,
        cap_add=("NET_ADMIN",),
        hostname=name,
        memory=surface.container_memory,
        cpus=surface.container_cpus,
    )
