"""Own time: a slot for each resident that is its own, shown beside the rounds."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from babo.baton import activity, own_time
from babo.baton.registry import Registry
from babo.baton.town import BatonError, Town


def _settled(town: Town, *residents: str) -> None:
    for r in residents:
        Registry(town).update(r, first_session_done=True)


class Pass:
    """Just what Night.run_own_time uses."""

    def __init__(self, town: Town, fail: str = "") -> None:
        self.town, self.own_time, self.fail = town, None, fail
        self.turns: list[tuple[str, str, str, str]] = []
        self.marked: dict[str, Any] = {}
        self.ledger = self

    def done(self, key: str) -> bool:
        return key in self.marked

    def mark(self, key: str, **info: Any) -> None:
        self.marked[key] = info

    def _checkpoint_interrupt(self, step: str) -> None: ...

    def log(self, line: str) -> None: ...

    async def agent_turn(self, resident: str, message: str, session_key: str, kind: str = "upkeep") -> str:
        self.turns.append((resident, message, session_key, kind))
        if resident == self.fail:
            raise RuntimeError("no model")
        return f"{resident} wrote a letter and rested."


async def test_each_settled_resident_gets_its_own_time_weekly(town: Town) -> None:
    from babo.baton.night import Night

    now = datetime.now().astimezone()
    assert own_time.due(town, now=now) == []  # (off in tests)
    own_time.set_every(town, "weekly")
    assert own_time.due(town, now=now) == []  # nobody has settled in yet
    _settled(town, "archivist", "inspector")
    assert own_time.due(town, now=now) == [("archivist", "its weekly own time"), ("inspector", "its weekly own time")]
    ctx = Pass(town, fail="inspector")
    await Night.run_own_time(ctx)  # type: ignore[arg-type]
    [(who, message, key, kind), _] = ctx.turns
    assert (who, key, kind) == ("archivist", "own-time:archivist", "own-time") and "Nothing is asked of you" in message
    assert own_time.runs(town, "archivist")[0]["said"] == "archivist wrote a letter and rested."
    assert own_time.runs(town, "inspector")[0]["status"] == "failed"  # the pass went on without it
    assert activity.get(town, "own_time:archivist").status == "done"  # type: ignore[union-attr]
    assert [r for r, _ in own_time.due(town, now=now)] == []  # had it this week (the failed one too, until next week)
    assert [r for r, _ in own_time.due(town, now=now + timedelta(days=7, minutes=1))] == ["archivist", "inspector"]


def test_how_often_is_set_for_the_town_or_one_resident(town: Town) -> None:
    _settled(town, "archivist", "inspector")
    own_time.set_every(town, "weekly")
    assert own_time.set_every(town, "off", "inspector") == "inspector's own time: off."
    assert [r for r, _ in own_time.due(town, now=datetime.now().astimezone())] == ["archivist"]
    assert own_time.set_every(town, "town", "inspector") == "inspector's own time follows the town's (weekly)."
    with pytest.raises(BatonError, match="daily, weekly, off"):
        own_time.set_every(town, "hourly")
    rows = {r["resident"]: r for r in own_time.overview(town)["residents"]}
    assert rows["archivist"]["every"] == "weekly" and rows["archivist"]["next"] == "at the next upkeep pass"


def test_the_owner_gives_a_resident_its_time_now(town: Town) -> None:
    from babo.baton import upkeep

    assert "starts within a minute" in own_time.request(town, "inspector")
    assert own_time.due(town, now=datetime.now().astimezone()) == [("inspector", "given by the owner")]  # even while off
    assert activity.get(town, "own_time:inspector").status == "waiting"  # type: ignore[union-attr]
    assert upkeep.Due().own_time == []
    own_time.clear_requests(town)
    assert own_time.due(town, now=datetime.now().astimezone()) == []


def test_the_terminal_and_the_web_show_and_set_it(town: Town, index_path: Path, make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from rich.console import Console
    from typer.testing import CliRunner
    from websockets.datastructures import Headers
    from websockets.http11 import Request as WsRequest

    from babo.baton import cli
    from babo.config.schema import Config
    from babo.webui.town_api import TownRoutes

    monkeypatch.setattr(cli, "_town", lambda _config: (town, make_config("mayor")))
    monkeypatch.setattr(cli, "console", Console(width=200, force_terminal=False))
    run = CliRunner().invoke
    assert "Own time for the town: weekly" in run(cli.app, ["own-time", "set", "weekly"]).output
    own_time.record(town, "archivist", started=datetime.now().astimezone().isoformat(), status="done", said="Revised myself.", why="t")
    out = run(cli.app, ["own-time"]).output
    assert "- archivist (weekly); next:" in out and "Revised myself." in out
    assert "starts within a minute" in run(cli.app, ["own-time", "now", "archivist"]).output
    assert run(cli.app, ["own-time", "set", "sometimes"]).exit_code == 1

    cfg = Config.model_validate({"baton": {"town": str(town.root), "indexPath": str(index_path)}})
    monkeypatch.setattr("babo.config.loader.load_config", lambda *_a, **_k: cfg)
    payloads: dict[int, dict[str, Any]] = {}
    routes = TownRoutes(authorized=lambda _request: True, payload=lambda request: payloads.get(id(request)))

    async def call(path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        request = WsRequest(path, Headers())
        if body is not None:
            payloads[id(request)] = body
        response = await routes.dispatch(request, path)
        assert response is not None
        text = response.body.decode() if response.body else ""
        try:
            return response.status_code, json.loads(text)
        except ValueError:
            return response.status_code, text

    status, got = asyncio.run(call("/api/town/own-time/set", {"every": "daily", "resident": "archivist"}))
    assert status == 200 and got["message"] == "archivist's own time: daily."
    status, got = asyncio.run(call("/api/town/own-time"))
    assert got["every"] == "weekly" and {r["resident"]: r["every"] for r in got["residents"]}["archivist"] == "daily"
    status, got = asyncio.run(call("/api/town/own-time/now", {"resident": "inspector"}))
    assert status == 200 and "inspector's own time starts" in got["message"]
