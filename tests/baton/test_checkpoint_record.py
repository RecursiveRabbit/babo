"""A line in a resident's checkpoint record that isn't a checkpoint is skipped, never fatal."""

from __future__ import annotations

import json

from babo.baton.baton_file import (
    Checkpoint,
    append_checkpoint,
    current_entry,
    iter_checkpoints,
    unreadable_lines,
)
from babo.baton.town import Town


def test_lines_that_arent_checkpoints_are_skipped_and_listed(town: Town) -> None:
    home = town.resident_dir("mayor")
    append_checkpoint(home, Checkpoint(thread="the board", doing="reading posts", resident="mayor"))
    record = next((home / "checkpoints").glob("*.jsonl"))
    with record.open("a", encoding="utf-8") as handle:  # what an agent's file tool, or a cut-short write, can leave
        handle.write(json.dumps("a note written as a plain string") + "\n" + "[1, 2]\n" + "42\n" + "{not json\n")
    assert [c.doing for c in iter_checkpoints(home)] == ["reading posts"]
    entry = current_entry(home)
    assert entry is not None and entry.thread == "the board"
    assert [n for _, n in unreadable_lines(home)] == [2, 3, 4, 5]


def test_the_town_page_and_the_mayors_prompt_still_load(town: Town) -> None:
    from babo.baton import views
    from babo.baton.bundle import build_bundle
    from babo.baton.config import BatonConfig
    from babo.baton.registry import Registry

    Registry(town).update("mayor", first_session_done=True)  # (a first session has the whole charter instead)
    home = town.resident_dir("mayor")
    append_checkpoint(home, Checkpoint(thread="the board", doing="reading posts", resident="mayor"))
    with next((home / "checkpoints").glob("*.jsonl")).open("a", encoding="utf-8") as handle:
        handle.write('"stray"\n')
    assert "reading posts" in build_bundle(town, "mayor").text()
    assert views.town_overview(town, BatonConfig())["residents"]


def test_the_doctor_says_where_they_are(town: Town, make_config) -> None:
    from babo.baton.doctor import check_memory_files

    cfg = make_config("mayor")
    assert check_memory_files(cfg).status == "PASS"
    record = town.resident_dir("archivist") / "checkpoints" / "2026-11-01.jsonl"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text('"stray"\n')
    check = check_memory_files(cfg)
    assert check.status == "WARN" and "residents/archivist/checkpoints/2026-11-01.jsonl line 1" in check.detail
