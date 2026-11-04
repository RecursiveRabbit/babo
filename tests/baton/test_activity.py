"""What Babo is working on now: one entry per thing, waiting, running, done or failed, shown where it was asked for."""

from __future__ import annotations

from typing import Any

import pytest

from babo.baton import activity, rounds, views
from babo.baton.town import Town


def test_an_entry_goes_from_waiting_to_running_to_done(town: Town) -> None:
    activity.note(town, "round:night", "round", "The night round", status="waiting", detail="starts within a minute")
    assert activity.get(town, "round:night").status == "waiting"  # type: ignore[union-attr]
    activity.update(town, "round:night", "running", "run by hand")
    activity.update(town, "round:night", "done", "2 step(s) done")
    done = activity.get(town, "round:night")
    assert done is not None and (done.status, done.detail) == ("done", "2 step(s) done") and done.finished and not done.active
    activity.update(town, "nothing:here", "done")  # an entry nobody started: nothing happens
    assert [e.key for e in activity.recent(town)] == ["round:night"]


def test_tracked_says_why_it_failed(town: Town) -> None:
    with pytest.raises(RuntimeError), activity.tracked(town, "freeze:archivist:s1", "freeze", "archivist is reviewing"):
        raise RuntimeError("the model wasn't reachable")
    failed = activity.get(town, "freeze:archivist:s1")
    assert failed is not None and failed.status == "failed" and "the model wasn't reachable" in failed.detail
    with activity.tracked(town, "freeze:archivist:s2", "freeze", "archivist is reviewing") as entry:
        entry.detail = "frozen"
    assert activity.get(town, "freeze:archivist:s2").detail == "frozen"  # type: ignore[union-attr]


def test_asking_for_a_round_or_upkeep_now_shows_it_waiting(town: Town) -> None:
    rounds.request_run(town, "night")
    views.request_upkeep(town)
    shown = {e.key: e.status for e in activity.recent(town)}
    assert shown == {"round:night": "waiting", "upkeep": "waiting"}


async def test_a_round_run_by_upkeep_shows_running_then_how_it_went(town: Town) -> None:
    from babo.baton.night import Night

    class Pass:  # just what Night.run_rounds uses
        def __init__(self) -> None:
            self.town, self.night, self.work_dir = town, "test", town.state / "upkeep" / "test"
            self.rounds = [("night", "run by hand")]
            self.marked: dict[str, Any] = {}
            self.ledger = self

        def done(self, key: str) -> bool:
            return key in self.marked

        def mark(self, key: str, **info: Any) -> None:
            self.marked[key] = info

        def _checkpoint_interrupt(self, step: str) -> None: ...

        def log(self, line: str) -> None: ...

        async def agent_turn(self, resident: str, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("the model wasn't reachable")

    (town.promotions / "2026-11-01-mayor-soil.md").write_text("---\nfrom: mayor\ntitle: Soil\nstatus: pending\n---\n\nLoam.\n")
    rounds.request_run(town, "night")
    await Night.run_rounds(Pass())  # type: ignore[arg-type]
    shown = activity.get(town, "round:night")
    assert shown is not None and shown.status == "failed" and "stopped at" in shown.detail


def test_the_terminal_lists_what_babo_is_doing(town: Town, make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    from rich.console import Console
    from typer.testing import CliRunner

    from babo.baton import cli

    monkeypatch.setattr(cli, "_town", lambda _config: (town, make_config("mayor")))
    monkeypatch.setattr(cli, "console", Console(width=200, force_terminal=False))
    assert "Nothing is running" in CliRunner().invoke(cli.app, ["activity"]).output
    activity.note(town, "eval:town", "eval", "Eval of town", detail="3 of 31 tasks")
    out = CliRunner().invoke(cli.app, ["activity"]).output
    assert "running  Eval of town" in out and "3 of 31 tasks" in out
