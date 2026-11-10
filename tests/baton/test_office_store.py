"""The office's desired records: agents and crews are checked writes."""

from __future__ import annotations

import pytest

from babo.baton import projects as project_board
from babo.baton.town import BatonError, Town
from babo.office.store import CREW_FILE, AgentStore, CrewStore


def test_an_agent_record_needs_a_resident_and_a_project(town: Town) -> None:
    store = AgentStore(town)
    with pytest.raises(BatonError, match="isn't a resident"):
        store.record(town, {"handle": "crew-1", "resident": "nobody"})
    with pytest.raises(BatonError, match="no project"):
        store.record(town, {"handle": "crew-1", "resident": "archivist", "project": "missing"})
    assert store.all() == {}


def test_recording_an_agent_keeps_desired_state_only(town: Town) -> None:
    project = project_board.new_project(town, "mayor", "Crew work")
    store = AgentStore(town)
    said = store.record(town, {"handle": "crew-1", "resident": "archivist", "project": project.slug,
                               "desired": "frozen"})
    assert "crew-1" in said
    entry = store.get("crew-1")
    assert entry is not None
    assert entry["desired"] == "frozen"
    assert entry["labels"] == {"babo.managed": "true", "babo.resident": "archivist",
                               "babo.project": project.slug, "babo.crew": project.slug}
    # Nothing about the runtime sneaks into the record; the Manager adds `babo.launch` at run.
    assert set(entry) == {"handle", "resident", "project", "crew", "desired", "labels", "created", "updated"}


def test_changing_desired_state_needs_a_record(town: Town) -> None:
    store = AgentStore(town)
    with pytest.raises(BatonError, match="isn't recorded"):
        store.set_desired("ghost", "running")
    store.record(town, {"handle": "ghost", "resident": "inspector"})
    store.set_desired("ghost", "running")
    entry = store.get("ghost")
    assert entry is not None and entry["desired"] == "running"


def test_a_crew_is_a_file_beside_its_project(town: Town) -> None:
    project = project_board.new_project(town, "mayor", "Crew work")
    crews = CrewStore(town)
    said = crews.write({"project": project.slug, "lead": "lead-agent", "crew": ["crew-2"]})
    assert "lead-agent" in said
    assert (project_board.folder(town) / project.slug / CREW_FILE).exists()
    assert crews.read(project.slug) == {"project": project.slug, "lead": "lead-agent",
                                       "crew": ["crew-2"], "exists": True}


def test_a_crew_refuses_names_that_are_not_agent_handles(town: Town) -> None:
    project = project_board.new_project(town, "mayor", "Crew work")
    crews = CrewStore(town)
    with pytest.raises(BatonError, match="handle"):
        crews.write({"project": project.slug, "crew": ["Not A Handle"]})
    with pytest.raises(BatonError, match="no project"):
        crews.write({"project": "nowhere", "crew": ["crew-2"]})


def test_an_empty_crew_leaves_no_file(town: Town) -> None:
    project = project_board.new_project(town, "mayor", "Crew work")
    crews = CrewStore(town)
    crews.write({"project": project.slug, "lead": "lead-agent", "crew": ["crew-2"]})
    assert "file is gone" in crews.write({"project": project.slug, "lead": "", "crew": []})
    assert not (project_board.folder(town) / project.slug / CREW_FILE).exists()
    assert crews.read(project.slug)["exists"] is False
