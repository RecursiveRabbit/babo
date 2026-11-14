"""The runtime's error classes: which non-zero rc is a verdict, and which is silence.

F12 (bomu). A non-zero rc says the *process* exited unhappily; it does not say the
tool answered. The class is chosen by recognition over stderr, in one place
(`runtime._classify`), and both entry points — `_call` (run, ps) and
`_call_maybe_absent` (inspect, remove) — use it. The unrecognised side takes the
silent class on purpose: "no usable verdict, effect unstated" is never wrong about
a pod, while `failed` claims something happened.

These tests exercise **both** entry points with the same input, because a
classifier that is right in one path and wrong in the other passes a suite written
against one.
"""

from __future__ import annotations

import subprocess

import pytest

from babo.office import runtime as runtime_mod
from babo.office.runtime import (
    LaunchSpec,
    PodmanRuntime,
    RuntimeUnavailableError,
    RuntimeVerdictError,
)

# Plausible, unfamiliar, and matching none of the markers: the case the classifier
# must not guess about.
UNSEEN = "Error: something the wrapper has never said before: /var/lib/containers/x"


def _failing(stderr: str, rc: int = 125) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout="", stderr=stderr)


@pytest.fixture
def podman(monkeypatch: pytest.MonkeyPatch) -> PodmanRuntime:
    instance = PodmanRuntime(url="unix:///run/podman/podman.sock")
    return instance


def _respond(monkeypatch: pytest.MonkeyPatch, done: subprocess.CompletedProcess[str]) -> None:
    monkeypatch.setattr(runtime_mod.subprocess, "run", lambda *a, **k: done)


def test_an_unrecognised_message_is_silence_through_run(podman: PodmanRuntime,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # `run` goes through `_call`.
    _respond(monkeypatch, _failing(UNSEEN))
    with pytest.raises(RuntimeUnavailableError) as caught:
        podman.run(LaunchSpec(name="agent-a", image="babo-agent:test"))
    assert not isinstance(caught.value, RuntimeVerdictError)


def test_an_unrecognised_message_is_silence_through_inspect(
    podman: PodmanRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `inspect` goes through `_call_maybe_absent` — the second entry point, and the
    # one nearly every decision in the core reads first.
    _respond(monkeypatch, _failing(UNSEEN))
    with pytest.raises(RuntimeUnavailableError) as caught:
        podman.inspect_container("agent-a")
    assert not isinstance(caught.value, RuntimeVerdictError)


def test_an_unreachable_socket_is_silence_even_with_a_plausible_rc(
    podman: PodmanRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _respond(monkeypatch, _failing("Error: Cannot connect to the Podman socket: No such file"))
    with pytest.raises(RuntimeUnavailableError) as caught:
        podman.inspect_container("agent-a")
    assert not isinstance(caught.value, RuntimeVerdictError)


def test_a_named_answer_is_a_verdict_through_run(podman: PodmanRuntime,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # The tool answered; the answer was negative. That is `failed`, not silence.
    _respond(monkeypatch, _failing("Error: image not found"))
    with pytest.raises(RuntimeVerdictError):
        podman.run(LaunchSpec(name="agent-a", image="babo-agent:test"))


def test_an_absent_object_is_none_through_inspect_and_a_verdict_through_run(
    podman: PodmanRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Absent is an answer too, and the two entry points differ only in whether they
    # act on it: `inspect_container` returns None, `run` cannot and raises.
    _respond(monkeypatch, _failing("Error: no such container"))
    assert podman.inspect_container("agent-a") is None
    with pytest.raises(RuntimeVerdictError):
        podman.run(LaunchSpec(name="agent-a", image="babo-agent:test"))
