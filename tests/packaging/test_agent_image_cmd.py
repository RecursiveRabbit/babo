"""The agent image's command, read from the image — and the UNMET it carries.

`Surface.agent_image` was configuration in the retired oracle: the product never
shipped an agent image, it named one a deployer supplied. `Dockerfile` now has two
build targets over one base — `app` (`CMD ["status"]`, the default) and `agent`
(`CMD ["gateway"]`, the thing that starts the loop) — because the difference is the
command and nothing else.

This row asserts the **built images'** commands, not the Dockerfile's text: a file
can be edited without a build and built without a tag, and the question is what the
engine will run. Build them with

    podman build --target agent -t babo-agent:probe .
    podman build --target app   -t babo-app:probe   .

UNMET — THE AGENT INSIDE THE IMAGE DOES NOT YET LEARN WHO IT IS. The pod renderer
mounts `/run/secrets/spawn.json` read-only and nothing in `babo/` reads it; the
oracle's reader was Rails, from outside the pod. Until that reader exists, a pod
built from this tag starts a gateway that knows its config and its workspace and
not its identity. The row below is green about the command only, and its name says
so, because a named absence inside the artefact survives and a note in a pull
request does not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

AGENT_IMAGE = os.environ.get("BABO_AGENT_IMAGE", "babo-agent:probe")
APP_IMAGE = os.environ.get("BABO_APP_IMAGE", "babo-app:probe")


def _cmd(image: str) -> list[str] | None:
    if shutil.which("podman") is None:
        return None
    done = subprocess.run(
        ["podman", "image", "inspect", image, "--format", "{{json .Config.Cmd}}"],
        capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        return None
    return json.loads(done.stdout.strip() or "null")


def test_agent_image_cmd_is_gateway_and_app_image_cmd_is_status_UNMET_the_agent_does_not_learn_identity() -> None:
    """UNMET (identity): this row proves the command, and nothing about who the pod is.

    A named absence in the row's own name, because the reader for
    `/run/secrets/spawn.json` does not exist yet and a green command row must not be
    mistaken for "the agent is ready".
    """
    agent = _cmd(AGENT_IMAGE)
    app = _cmd(APP_IMAGE)
    if agent is None or app is None:
        pytest.skip(
            f"UNMET: {AGENT_IMAGE}/{APP_IMAGE} are not built here, so the images' commands "
            f"were NOT measured. Build them (--target agent / --target app) and re-run."
        )

    assert agent == ["gateway"], f"{AGENT_IMAGE} must run the gateway; the engine will run {agent!r}"
    assert app == ["status"], f"{APP_IMAGE} must keep its one-shot status; the engine will run {app!r}"
