#!/bin/sh
# LOCAL-ONLY: what commands will the two image roles actually run?
#
# This is a script and not a test on purpose. As a pytest row it skipped in CI
# forever — `1 skipped`, permanently numbered, and reading as though the commands
# had been verified — because CI has no image builder. A skip is honest when the
# thing cannot exist in that environment; a failure is honest when it should exist
# and does not. A row that can never run is neither: it is furniture with a number
# attached.
#
# Run it on a machine with podman:
#
#     scripts/verify_agent_image_cmd.sh [context]
#
# It builds both targets from the Dockerfile's single base and reads the command
# back out of each IMAGE — not out of the Dockerfile, which can be edited without a
# build and built without a tag. Exits 0 only when the app tag runs `status` and
# the agent tag runs `gateway`.
#
# UNMET — the agent inside the image does not yet learn who it is. This script
# says nothing about identity: `/run/secrets/spawn.json` is mounted by the pod
# renderer and nothing reads it. Its row is the relay's job.
set -eu

context="${1:-.}"
app_tag="babo-app:cmd-check"
agent_tag="babo-agent:cmd-check"

echo "building $app_tag from $context (--target app)…"
podman build --target app -t "$app_tag" "$context" >/dev/null
echo "building $agent_tag from $context (--target agent)…"
podman build --target agent -t "$agent_tag" "$context" >/dev/null

app_cmd="$(podman image inspect "$app_tag" --format '{{json .Config.Cmd}}')"
agent_cmd="$(podman image inspect "$agent_tag" --format '{{json .Config.Cmd}}')"

printf '  %-20s Cmd=%s\n' "$app_tag" "$app_cmd"
printf '  %-20s Cmd=%s\n' "$agent_tag" "$agent_cmd"

status=0
[ "$app_cmd" = '["status"]' ] || { echo "FAIL: the app image must run status; the engine will run $app_cmd" >&2; status=1; }
[ "$agent_cmd" = '["gateway"]' ] || { echo "FAIL: the agent image must run gateway; the engine will run $agent_cmd" >&2; status=1; }

if [ "$status" -eq 0 ]; then
    echo "OK: app runs status, agent runs gateway (read from the images)"
else
    echo "UNMET: the commands are not what the roles need" >&2
fi

if [ "${KEEP_IMAGES:-0}" != "1" ]; then
    podman rmi -f "$app_tag" "$agent_tag" >/dev/null 2>&1 || true
fi

exit "$status"
