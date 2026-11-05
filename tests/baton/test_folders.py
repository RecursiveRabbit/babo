"""Folders outside the town, and a resident's projects, as where a session works."""

from __future__ import annotations

from pathlib import Path

import pytest

from babo.baton import opencode, profiles, views
from babo.baton.town import BatonError, Town


def test_a_profile_lists_folders_outside_the_town_only(town: Town, make_config, tmp_path: Path) -> None:
    cfg = make_config("mayor")
    garden = tmp_path / "machine" / "code" / "garden"
    garden.mkdir(parents=True)
    said = views.update_profile(town, cfg.baton, "archivist", {"folders": [str(garden)]}, [])
    assert "Folders outside the town: none → " in said
    for bad, why in [("code/garden", "in full"), ("/", "too wide"), (str(Path.home()), "too wide"),
                     (str(tmp_path / "nowhere" / "x"), "isn't a folder"), (str(town.root / "commons"), "is the town")]:
        with pytest.raises(BatonError, match=why):
            views.update_profile(town, cfg.baton, "archivist", {"folders": [bad]}, [])
    with pytest.raises(BatonError, match="The Mayor works in Babo itself"):
        views.update_profile(town, cfg.baton, "mayor", {"folders": [str(garden)]}, [])
    with pytest.raises(BatonError, match="one folder"):
        profiles.session_profile(profiles.Profile(), {"folders": [str(garden)]}, agent="archivist", mcp_known=[])


def test_a_session_works_in_its_own_folder_a_project_or_a_listed_folder(town: Town, make_config, tmp_path: Path) -> None:
    cfg = make_config("mayor", **{"baton.opencode.bin": "/bin/true"})
    garden = tmp_path / "machine" / "code" / "garden"
    garden.mkdir(parents=True)
    (town.resident_dir("archivist") / "projects" / "notes").mkdir(parents=True)
    plain = opencode.new_session(town, cfg, "archivist", title="plain")
    assert plain.folder == "" and opencode.workdir(town, plain) == town.resident_dir("archivist")
    project = opencode.new_session(town, cfg, "archivist", title="notes", folder="notes")
    assert project.folder == "projects/notes" and opencode.workdir(town, project) == town.resident_dir("archivist") / "projects" / "notes"
    with pytest.raises(BatonError, match="no project called 'gone'. Its projects: notes"):
        opencode.new_session(town, cfg, "archivist", folder="projects/gone")
    with pytest.raises(BatonError, match="isn't one of the folders"):
        opencode.new_session(town, cfg, "archivist", folder=str(garden))
    views.update_profile(town, cfg.baton, "archivist", {"folders": [str(garden)]}, [])
    outside = opencode.new_session(town, cfg, "archivist", folder=str(garden))
    assert opencode.workdir(town, outside) == garden.resolve()
    assert [c["value"] for c in opencode.folder_choices(town, cfg, "archivist")] == ["", "projects/notes", str(garden.resolve())]
