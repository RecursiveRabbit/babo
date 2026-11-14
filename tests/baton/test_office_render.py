"""The renderer's rows: every field names its oracle line, and two absences hold.

`neoclaw-rails` is spec, not runtime — these rows cite it the way the renderer's
docstring does, so a field that changes shape has to change its citation too.
"""

from __future__ import annotations

import pytest

from babo.office import render
from babo.office.core import Identity

SURFACE = {
    "agent_image": "localhost/babo-agent:test",   # podman.rb:38
    "agent_network": "babo-agent-mesh",           # podman.rb:32
    "host_spawn_dir": "/srv/spawn",               # podman.rb:33
    "host_claude_dir": "/srv/claude",             # podman.rb:34
    "container_memory": "4g",                     # podman.rb:35
    "container_cpus": "2",                        # podman.rb:36
}


def _spec(handle: str = "crew-1", identity: Identity | None = None):
    return render.spec_for(handle, identity or Identity("archivist", "silas"),
                           surface=render.surface_from(SURFACE))


def test_every_field_of_the_spec_names_the_line_it_came_from() -> None:
    spec = _spec()

    # spawner.rb:202-205 — identity if the config is singleton, else identity-channel
    assert spec.name == "archivist-silas"

    assert spec.image == "localhost/babo-agent:test", "podman.rb:38 Surface.agent_image"
    assert spec.network == "babo-agent-mesh", "podman.rb:32 Surface.agent_network"
    assert spec.cap_add == ("NET_ADMIN",), "podman.rb:37"

    # podman.rb:33-34 — both read-only, and the spawn file is named for the pod
    assert [(m.source, m.destination, m.read_only) for m in spec.mounts] == [
        ("/srv/spawn/archivist-silas.json", "/run/secrets/spawn.json", True),
        ("/srv/claude", "/run/secrets/claude", True),
    ]

    # podman.rb:31, :35, :36 — the three the spec could not express until it was measured
    assert spec.hostname == "archivist-silas", "podman.rb:31 --hostname"
    assert spec.memory == "4g", "podman.rb:35 --memory Settings.resources.container_memory"
    assert spec.cpus == "2", "podman.rb:36 --cpus Settings.resources.container_cpus"


def test_the_two_absences_are_pinned_because_they_are_load_bearing() -> None:
    """podman.rb:12-41 passes no `-e` and no command.

    An agent's identity arrives through the mounted spawn.json secret, never
    through environment or argv — the same rule as identity never coming from
    model-authored args, applied to the pod itself. A later "helpful" `-e` fails
    here, which is the point.
    """
    spec = _spec()
    assert spec.env == {}, "no -e: identity travels in spawn.json, not in the environment"
    assert spec.command == (), "no command: the image's own entrypoint is the whole story"
    assert spec.labels == {}, "labels are for selection; nothing here selects by one"
    assert spec.network_mode == "", "the oracle names a network, never a mode"
    assert spec.cap_drop == ()


def test_a_missing_surface_value_is_refused_by_name_not_defaulted() -> None:
    for key in render.SURFACE_KEYS:
        values = {k: v for k, v in SURFACE.items() if k != key}
        with pytest.raises(render.RenderIncomplete) as caught:
            render.surface_from(values)
        assert key in str(caught.value), f"{key} must be named, not defaulted"

    with pytest.raises(render.RenderIncomplete) as caught:
        render.surface_from({**SURFACE, "container_memory": "   "})
    assert "container_memory" in str(caught.value), "blank is absent, not a value"


def test_the_singleton_case_is_an_absent_channel() -> None:
    assert render.instance_name(Identity("archivist", "")) == "archivist"
    assert render.instance_name(Identity("archivist", "silas")) == "archivist-silas"
