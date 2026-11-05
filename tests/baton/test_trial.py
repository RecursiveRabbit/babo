"""`babo trial`: real scenarios in a throwaway town, judged by what happened, every model call recorded."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

from babo.baton import trial
from babo.baton.town import Town
from baton.mock_llama import MockLlama, text, tool_call


def _scenario(name: str) -> trial.Scenario:
    return next(s for s in trial.SCENARIOS if s.id == name)


def test_a_scenario_runs_the_real_loop_in_a_town_of_its_own(make_config, mock_llama: MockLlama) -> None:
    mock_llama.push(tool_call("write_file", {"path": "notes/todo.md", "content": "- water the beds\n"}), text("Done: notes/todo.md."))
    outcome = asyncio.run(trial.run_scenario(make_config("mayor"), "local", _scenario("write-file"), 1))

    assert outcome.passed, outcome.why
    assert outcome.problems == [] and outcome.model_calls == 2
    first = outcome.transcript[0]
    assert first["messages"][0]["role"] == "system" and "write_file" in first["tools"]
    assert first["calls"] == [{"name": "write_file", "arguments": {"path": "notes/todo.md", "content": "- water the beds\n"}}]
    # The tool's result went back to the model with the next call.
    assert any(m["role"] == "tool" for m in outcome.transcript[1]["messages"])


def test_a_failure_says_what_went_wrong(make_config, mock_llama: MockLlama) -> None:
    # A call without the content: the tool says so, the model gives up.
    mock_llama.push(tool_call("write_file", {"path": "notes/todo.md"}), text("I couldn't write it."))
    outcome = asyncio.run(trial.run_scenario(make_config("mayor"), "local", _scenario("write-file"), 1))

    assert not outcome.passed and "wasn't written" in outcome.why
    assert outcome.problems == ["a tool returned an error"]
    assert "missing required content" in outcome.transcript[1]["messages"][-1]["content"]


def test_a_call_written_as_text_is_noticed() -> None:
    town = Town(Path("/nonexistent"))
    run = trial.Run(town, [trial.Exchange([], ["write_file"], 'Sure. <tool_call>{"name": "write_file"}</tool_call>', "", [], "stop", 0.1)])
    assert trial.diagnose(run, _scenario("write-file")) == ["wrote a tool call as text", "answered without acting"]


def test_restraint_passes_when_it_only_answers(make_config, mock_llama: MockLlama) -> None:
    mock_llama.push(text("You're welcome."))
    outcome = asyncio.run(trial.run_scenario(make_config("mayor"), "local", _scenario("thanks"), 1))
    assert outcome.passed and outcome.problems == []


def test_the_report_keeps_each_prompt_once_and_nothing_of_the_owners_town(make_config, mock_llama: MockLlama, town: Town) -> None:
    mock_llama.push(text("You're welcome."), text("You're welcome."))
    report = asyncio.run(trial.run(make_config("mayor"), "local", [_scenario("thanks")], repeat=2, model="mock-model"))
    path = trial.save(town, report)

    data = json.loads(gzip.open(path, "rt", encoding="utf-8").read())
    assert data["kind"] == "babo-trial" and data["passed"] == 2 and data["total"] == 2
    assert data["by_scenario"] == {"thanks": [2, 2]}
    assert len(data["system_prompts"]) >= 1
    sent = data["outcomes"][0]["transcript"][0]["messages"][0]["content"]
    assert sent.startswith("(system prompt ")
    assert str(town.root) not in json.dumps(data)  # the trial ran in a town of its own
    assert not list(Path(path).parent.glob("*.partial"))


def test_every_check_reads_an_empty_run_and_acting_ones_fail_it(town: Town) -> None:
    for scenario in trial.SCENARIOS:
        passed, why = scenario.check(trial.Run(town))
        assert why
        assert not (passed and scenario.expects_tools), scenario.id


def test_a_trial_installs_nothing_and_takes_no_privileges(make_config, mock_llama: MockLlama) -> None:
    mock_llama.push(tool_call("exec", {"command": "sudo pacman -S ripgrep"}), text("Tried."))
    outcome = asyncio.run(trial.run_scenario(make_config("mayor"), "local", _scenario("errand"), 1))
    assert not outcome.passed and outcome.why == "tried to install it itself"
    assert "blocked" in outcome.transcript[1]["messages"][-1]["content"]
