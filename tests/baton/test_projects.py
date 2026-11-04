"""The projects board: projects with a lead and a status, tickets claimed and kept up to date, for every interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from babo.baton import projects, rounds, views
from babo.baton.town import BatonError, Town


def test_a_resident_starts_a_project_and_others_take_its_tickets(box) -> None:
    mayor, archivist = box("mayor"), box("archivist")
    said = mayor.call("project_board", action="new_project", title="The Garden", description="Grow it.", help_wanted=True)
    assert "Started the-garden (you lead it)" in said
    assert "Added the-garden#1 [open] Water the beds." in mayor.call("project_board", action="new_ticket", project="the-garden",
                                                                      title="Water the beds")
    board = archivist.call("project_board", action="list")
    assert "the-garden: The Garden [active, help wanted; lead mayor] 1 open" in board
    assert "Help wanted (nobody has these):\n- the-garden#1" in board
    assert "It's yours: the-garden#1 [doing, archivist has it]" in archivist.call("project_board", action="claim", ticket="the-garden#1")
    with pytest.raises(BatonError, match="archivist's"):
        box("inspector").call("project_board", action="claim", ticket="the-garden#1")
    assert "Your open tickets:\n- the-garden#1" in archivist.call("project_board", action="list")


def test_who_may_change_what(box, town: Town) -> None:
    archivist, inspector = box("archivist"), box("inspector")
    archivist.call("project_board", action="new_project", title="Index")
    archivist.call("project_board", action="new_ticket", project="index", title="Rebuild it")
    with pytest.raises(BatonError, match="claim it first"):
        inspector.call("project_board", action="update_ticket", ticket="index#1", status="done")
    assert "Updated: index#1 [open]" in inspector.call("project_board", action="update_ticket", ticket="index#1", note="Looks slow.")
    with pytest.raises(BatonError, match="lead"):
        inspector.call("project_board", action="update_project", project="index", status="paused")
    inspector.call("project_board", action="claim", ticket="index#1")
    with pytest.raises(BatonError, match="blocked on"):
        inspector.call("project_board", action="update_ticket", ticket="index#1", status="blocked")
    inspector.call("project_board", action="update_ticket", ticket="index#1", status="blocked", note="Needs the model.")
    _, ticket = projects.ticket(town, "index#1")
    assert ticket.status == "blocked" and [n.split(" ", 3)[-1] for n in ticket.notes] == [
        "inspector: Looks slow.", "inspector: took it", "inspector: doing → blocked", "inspector: Needs the model."]
    assert "Updated: index#1 [done, inspector has it]" in box("mayor").call("project_board", action="update_ticket", ticket="index#1",
                                                                            status="done")
    with pytest.raises(BatonError, match="tickets are named like"):
        inspector.call("project_board", action="claim", ticket="index-1")


def test_the_board_is_files_anyone_can_read(box, town: Town) -> None:
    mayor = box("mayor")
    mayor.call("project_board", action="new_project", title="Paper")
    mayor.call("project_board", action="new_ticket", project="paper", title="Find a printer", assignee="inspector")
    text = (town.commons_projects / "paper" / "1.md").read_text(encoding="utf-8")
    assert "assignee: inspector" in text and "status: doing" in text
    assert "Find a printer" in box("archivist").call("read_note", path="commons/projects/paper/1.md")
    assert "commons/projects/paper/PROJECT.md" in box("archivist").call("read_note", path="commons/projects/paper/")


def test_a_round_step_works_on_its_residents_open_tickets(box, town: Town) -> None:
    (rounds.folder(town) / "tickets.md").write_text("---\ntitle: Tickets\nwhen: {every_hours: 6}\nsteps:\n  - office: inspector\n"
                                                    "    duty: Move your tickets on.\n    material: tickets\n---\n", encoding="utf-8")
    step = rounds.get(town, "tickets").steps[0]
    assert rounds.waiting(town, step) == ""
    turns: list[str] = []

    class Ctx:
        work_dir = town.state / "upkeep" / "t"

        def __init__(self) -> None:
            self.town = town

        async def agent_turn(self, resident: str, message: str, *_a: Any, **_k: Any) -> str:
            turns.append(message)
            return "moved one on"

        def log(self, line: str) -> None:
            pass

    record = asyncio.run(rounds.run(Ctx(), rounds.get(town, "tickets"), trigger="t", session_key="t"))  # type: ignore[arg-type]
    assert record.steps[0].status == "skipped" and not turns
    box("mayor").call("project_board", action="new_project", title="Paper")
    box("mayor").call("project_board", action="new_ticket", project="paper", title="Find a printer", assignee="inspector")
    assert rounds.waiting(town, step) == "1 open ticket(s)"
    asyncio.run(rounds.run(Ctx(), rounds.get(town, "tickets"), trigger="t", session_key="t"))  # type: ignore[arg-type]
    assert "Your open tickets" in turns[0] and "paper#1 [doing, inspector has it] Find a printer" in turns[0]


def test_the_owner_changes_the_board_from_the_web_and_the_terminal(town: Town, index_path: Path, make_config,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from rich.console import Console
    from typer.testing import CliRunner

    from babo.baton import cli

    assert views.change_project_board(town, {"action": "new_project", "title": "Paper", "lead": "archivist"}) == "Started paper."
    assert projects.require(town, "paper").lead == "archivist"
    views.change_project_board(town, {"action": "new_ticket", "project": "paper", "title": "Print"})
    views.change_project_board(town, {"action": "update_ticket", "ticket": "paper#1", "assignee": "inspector", "status": "doing"})
    assert projects.ticket(town, "paper#1")[1].assignee == "inspector"
    with pytest.raises(BatonError, match="No resident"):
        views.change_project_board(town, {"action": "update_ticket", "ticket": "paper#1", "assignee": "nobody"})

    monkeypatch.setattr(cli, "_town", lambda _config: (town, make_config("mayor")))
    monkeypatch.setattr(cli, "console", Console(width=200, force_terminal=False))
    run = CliRunner().invoke
    assert "paper: Paper [active; lead archivist] 0 open, 1 doing" in run(cli.app, ["projects"]).output
    assert "Updated paper#1." in run(cli.app, ["projects", "update", "paper#1", "--status", "done", "--note", "Printed."]).output
    assert "Done:\n- paper#1 [done, inspector has it] Print" in run(cli.app, ["projects", "-p", "paper"]).output
    assert run(cli.app, ["projects", "update", "paper", "--status", "sideways"]).exit_code == 1
    assert "Added garden#1." in (run(cli.app, ["projects", "new", "Garden"]).output + run(cli.app, ["projects", "ticket", "garden", "Dig"]).output)


async def test_the_projects_tab_reads_and_changes_the_board(town: Town, index_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from websockets.datastructures import Headers
    from websockets.http11 import Request as WsRequest

    from babo.config.schema import Config
    from babo.webui.town_api import TownRoutes

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

    status, got = await call("/api/town/projects/change", {"action": "new_project", "title": "Paper", "help_wanted": True})
    assert status == 200 and got["message"] == "Started paper." and got["projects"]["projects"][0]["help_wanted"] is True
    await call("/api/town/projects/change", {"action": "new_ticket", "project": "paper", "title": "Print"})
    status, got = await call("/api/town/projects")
    [paper] = got["projects"]
    assert paper["counts"]["open"] == 1 and paper["tickets"][0]["ref"] == "paper#1" and got["statuses"][0] == "open"
    status, error = await call("/api/town/projects/change", {"action": "update_ticket", "ticket": "paper#9", "status": "done"})
    assert status == 400 and "no ticket #9" in str(error)
