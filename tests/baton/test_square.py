"""The town square: threads everyone starts and replies to, what's new shown with where you are now."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from babo.baton import rounds, square, views
from babo.baton.bundle import build_bundle
from babo.baton.town import BatonError, Town


def test_anyone_starts_a_thread_and_others_reply(box, town: Town) -> None:
    archivist, inspector = box("archivist"), box("inspector")
    said = archivist.call("town_square", kind="question", title="Where do recipes go?", text="Knowledge, or a project?")
    assert said.startswith("Posted on the square: [question] Where do recipes go? — archivist")
    [thread] = square.threads(town)
    assert inspector.call("town_square", action="reply", thread=thread.id, text="Knowledge, I'd say.") == f"Replied on {thread.id}."
    full = archivist.call("town_square", action="read", thread=thread.id)
    assert "Knowledge, or a project?" in full and "inspector: Knowledge, I'd say." in full
    with pytest.raises(BatonError, match="Only whoever started it"):
        inspector.call("town_square", action="close", thread=thread.id)
    assert archivist.call("town_square", action="close", thread=thread.id, text="Thanks!") == f"Closed {thread.id}."
    with pytest.raises(BatonError, match="is closed"):
        inspector.call("town_square", action="reply", thread=thread.id, text="One more thing")
    assert square.threads(town) == [] and square.get(town, thread.id).replies[-1]["text"] == "Thanks!"
    assert (town.commons / "square" / f"{thread.id}.md").exists()  # a file in the commons, for anyone to read
    assert "Thanks!" in box("mayor").call("read_note", path=f"commons/square/{thread.id}.md")


def test_the_mayors_posts_for_the_owner_still_go_to_the_board(box, town: Town) -> None:
    said = box("mayor").call("post_board", kind="move_in_request", text="Someone to tend the garden.", office="gardener")  # (the old name)
    assert "Move-in request posted" in said and list(town.board.glob("*gardener*.md")) and square.threads(town) == []
    with pytest.raises(BatonError, match="only the mayor"):
        box("archivist").call("town_square", kind="open_role", text="A baker")
    with pytest.raises(BatonError, match="question, observation, flag, announcement"):
        box("archivist").call("town_square", text="No kind")


def test_whats_new_is_shown_with_where_you_are_now_until_read(box, town: Town) -> None:
    box("archivist").call("town_square", kind="announcement", title="The index is rebuilt", text="Search is fast again.")
    shown = build_bundle(town, "inspector").now_text()
    assert "## New on the square" in shown and "[announcement] The index is rebuilt — archivist" in shown
    assert "New on the square" not in build_bundle(town, "archivist").now_text()  # (its own)
    assert "The index is rebuilt" in box("inspector").call("town_square", action="read")
    assert "New on the square" not in build_bundle(town, "inspector").now_text()  # read: nothing new
    box("mayor").call("town_square", action="reply", thread=square.threads(town)[0].id, text="Thank you.")
    assert "1 reply" in build_bundle(town, "inspector").now_text()  # a reply is something new
    assert "New on the square" not in build_bundle(town, "mayor").now_text()


def test_a_round_step_reads_whats_new_on_the_square(box, town: Town) -> None:
    (rounds.folder(town) / "square.md").write_text("---\ntitle: The square\nwhen: {daily: '07:00'}\nsteps:\n  - office: inspector\n"
                                                   "    duty: Answer what you can.\n    material: square\n---\n", encoding="utf-8")
    step = rounds.get(town, "square").steps[0]
    assert rounds.waiting(town, step) == ""
    box("archivist").call("town_square", kind="question", title="Who has the ladder?", text="I need it for the shelves.")
    assert rounds.waiting(town, step) == "1 new thread(s) on the square"
    turns: list[str] = []

    class Ctx:
        work_dir = town.state / "upkeep" / "t"

        def __init__(self) -> None:
            self.town = town

        async def agent_turn(self, resident: str, message: str, *_a: Any, **_k: Any) -> str:
            turns.append(message)
            return "answered"

        def log(self, line: str) -> None:
            pass

    asyncio.run(rounds.run(Ctx(), rounds.get(town, "square"), trigger="t", session_key="t"))  # type: ignore[arg-type]
    assert "Who has the ladder?" in turns[0] and "I need it for the shelves." in turns[0]
    assert rounds.waiting(town, step) == ""  # seen, once the step has run


def test_the_owner_on_the_square_from_the_terminal(town: Town, make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    from rich.console import Console
    from typer.testing import CliRunner

    from babo.baton import cli

    monkeypatch.setattr(cli, "_town", lambda _config: (town, make_config("mayor")))
    monkeypatch.setattr(cli, "console", Console(width=200, force_terminal=False))
    run = CliRunner().invoke
    assert "The square is quiet" in run(cli.app, ["square"]).output
    assert "Posted:" in run(cli.app, ["square", "post", "The power goes off at noon.", "--title", "Power cut"]).output
    [thread] = square.threads(town)
    assert "[announcement] Power cut — owner" in run(cli.app, ["square"]).output
    assert "Replied on" in run(cli.app, ["square", "reply", thread.id, "Back at two."]).output
    assert "owner: Back at two." in run(cli.app, ["square", "show", thread.id]).output
    assert "Closed" in run(cli.app, ["square", "close", thread.id]).output
    assert run(cli.app, ["square", "post", "x", "--kind", "gossip"]).exit_code == 1
    assert "New on the square" in build_bundle(town, "archivist").now_text() or square.threads(town) == []


async def test_the_square_tab_reads_and_posts(town: Town, index_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    status, got = await call("/api/town/square/change", {"action": "post", "kind": "question", "title": "Tea?", "text": "Anyone?"})
    assert status == 200 and got["square"]["threads"][0]["author"] == "owner"
    thread = got["square"]["threads"][0]["id"]
    await call("/api/town/square/change", {"action": "reply", "thread": thread, "text": "Yes please."})
    status, got = await call("/api/town/square")
    assert got["kinds"] == list(square.KINDS) and got["threads"][0]["replies"][0]["text"] == "Yes please."
    status, error = await call("/api/town/square/change", {"action": "post", "kind": "move_in_request", "text": "x"})
    assert status == 400 and "A thread is one of" in str(error)
    assert views.change_square(town, {"action": "close", "thread": thread}) == f"Closed {thread}."
