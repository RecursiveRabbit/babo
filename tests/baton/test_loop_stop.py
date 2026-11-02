"""Going round in circles: after the third reminder in a turn, Babo ends its tool calls and it answers in words."""

from __future__ import annotations

from babo.baton.town import Town


async def test_a_turn_that_keeps_hitting_the_same_wall_is_stopped_and_answers(make_loop, mock_llama, town: Town) -> None:
    from baton.mock_llama import text, tool_call

    # The model keeps making the same call while it has tools, and answers in words when it hasn't.
    mock_llama.default = lambda body: (tool_call("exec", {"command": "ls /etc/"}) if body.get("tools")
                                       else text("I can't list that folder from here; I need read access to it."))
    loop = make_loop("mayor")
    result = await loop.process_direct("What's in /etc?", session_key="cli:loop")
    said = str(getattr(result, "content", result))
    assert "I can't list that folder" in said
    last = mock_llama.requests[-1]
    assert not last.get("tools") and "going round in circles" in str(last["messages"][-1]["content"])
    assert len(mock_llama.requests) < 15  # it didn't use up its whole budget on the same refusal
    from babo.baton.events import resident_events

    assert any(e["kind"] == "drift" and e.get("rule") == "stopped" for e in resident_events(town, "mayor"))


def test_read_note_lists_a_folder_the_resident_may_read(town: Town, box) -> None:
    mayor = box("mayor")
    listed = mayor.call("read_note", path="rounds/")
    assert listed.startswith("In rounds/") and "- rounds/night.md" in listed
    assert "- offices/archivist.md" in mayor.call("read_note", path="offices")
    residents = mayor.call("read_note", path="residents/")
    assert "residents/mayor/" in residents and "residents/archivist" not in residents  # only what it may read
