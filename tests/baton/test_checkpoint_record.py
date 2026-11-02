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


def _stray(town: Town, resident: str = "mayor", text: str = "remember the board is open on Mondays") -> str:
    home = town.resident_dir(resident)
    append_checkpoint(home, Checkpoint(thread="the board", doing="reading posts", resident=resident))
    record = next((home / "checkpoints").glob("*.jsonl"))
    with record.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(text) + "\n")
    return f"checkpoints/{record.name}:2"


def test_a_stray_line_is_shown_to_its_resident_word_for_word_until_it_says_what_it_was(town: Town, box) -> None:
    from babo.baton.bundle import build_bundle
    from babo.baton.registry import Registry

    Registry(town).update("mayor", first_session_done=True)
    ref = _stray(town)
    now = build_bundle(town, "mayor").now_text()
    assert "Also in your record, not written as checkpoints" in now and f'`{ref}`: "remember the board is open on Mondays"' in now
    said = box("mayor").call("correct_checkpoint", entry=ref, thread="the board", doing="checking the board on Mondays")
    assert ref in said and "is now a checkpoint" in said
    assert "Also in your record" not in build_bundle(town, "mayor").now_text()  # resolved
    record = next((town.resident_dir("mayor") / "checkpoints").glob("*.jsonl"))
    assert '"remember the board is open on Mondays"' in record.read_text()  # never rewritten
    latest = current_entry(town.resident_dir("mayor"))
    assert latest is not None and latest.doing == "checking the board on Mondays" and latest.corrects == ref


def test_a_stray_line_can_be_kept_as_a_note(town: Town, box) -> None:
    from babo.baton.inbox import items

    ref = _stray(town)
    assert "Kept as a note" in box("mayor").call("correct_checkpoint", entry=ref, keep_as_note=True)
    assert any(i.kind == "remember" and "Mondays" in i.body for i in items(town, "mayor"))
    from babo.baton.baton_file import strays

    assert strays(town.resident_dir("mayor")) == []


def test_an_entry_is_corrected_by_a_new_one_naming_it(town: Town, box) -> None:
    import pytest

    from babo.baton.town import BatonError

    home = town.resident_dir("mayor")
    append_checkpoint(home, Checkpoint(thread="the index", doing="listing notes", next=["write it"], resident="mayor",
                                       at="2026-11-02T05:59:10"))
    said = box("mayor").call("correct_checkpoint", entry="2026-11-02 05:59", doing="listing the commons notes")
    assert "corrected" in said
    latest = current_entry(home)
    assert latest is not None and (latest.doing, latest.next, latest.thread) == ("listing the commons notes", ["write it"], "the index")
    assert "correcting 2026-11-02T05:59:10" in latest.render() and len(iter_checkpoints(home)) == 2  # both kept
    with pytest.raises(BatonError, match="Nothing in your record"):
        box("mayor").call("correct_checkpoint", entry="2020-01-01 00:00", doing="x")


async def test_the_mayors_file_tools_dont_write_his_record(make_loop, mock_llama, town: Town) -> None:
    from baton.mock_llama import text, tool_call

    home = town.resident_dir("mayor")
    mock_llama.push(tool_call("write_file", {"path": "checkpoints/2026-11-02.jsonl", "content": '"x"\n'}),
                    tool_call("write_file", {"path": "notes.md", "content": "fine"}), text("Done."))
    await make_loop("mayor").process_direct("Write those.", session_key="cli:record")
    assert not (home / "checkpoints" / "2026-11-02.jsonl").exists() and (home / "notes.md").read_text() == "fine"
    first = [m for m in mock_llama.requests[1]["messages"] if m["role"] == "tool"][-1]["content"]
    assert "correct_checkpoint" in first
