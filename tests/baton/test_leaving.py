"""Moving away by choice: the resident asks, the owner acknowledges (never refuses), the handover reaches the next one."""

from __future__ import annotations

import pytest

from babo.baton import leaving, notices, views
from babo.baton.inbox import unread
from babo.baton.registry import Registry
from babo.baton.town import BatonError, Town

HANDOVER = "I was rebuilding the index of recipes; half of them are done. Ask the inspector about the broken links."


def _note(town: Town, resident: str, name: str, text: str) -> None:
    path = town.resident_dir(resident) / "knowledge" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {name.title()}\n---\n\n{text}\n", encoding="utf-8")


def test_a_resident_asks_to_move_away_and_the_owner_acknowledges(box, town: Town) -> None:
    _note(town, "archivist", "soil", "Loam holds water.")
    said = box("archivist").call("propose_change", title="Moving away", rationale="I'd like to rest.", description=HANDOVER,
                                 move_away=True, keep=["knowledge/soil.md"])
    assert "acknowledges it" in said
    [item] = views.review_items(town)["leaving"]
    assert item["resident"] == "archivist" and item["reason"] == "I'd like to rest." and item["keep"] == ["residents/archivist/knowledge/soil.md"]
    assert views.pending_counts(town)["leaving"] == 1
    assert any(n["kind"] == "move_away_request" for n in notices.recent(town))
    with pytest.raises(BatonError, match="can't be refused"):
        views.decide(town, "move_away", item["id"], yes=False, reason="stay")
    assert Registry(town).get("archivist").status == "active"  # type: ignore[union-attr]
    result = views.decide(town, "move_away", item["id"], yes=True, reason="Thank you for everything.")
    assert "archivist has moved away" in result and "Soil" in result and "commons/handovers/archivist/" in result
    assert Registry(town).get("archivist").status == "moved_away"  # type: ignore[union-attr]
    assert (town.resident_dir("archivist") / "knowledge" / "soil.md").exists()  # its folder and memory stay
    [kept] = list(town.promotions.glob("*archivist-soil.md"))
    assert "Loam holds water." in kept.read_text(encoding="utf-8")
    assert views.review_items(town)["leaving"] == []


def test_the_next_one_in_the_office_gets_the_handover(box, town: Town) -> None:
    box("archivist").call("propose_change", title="Moving away", rationale="Time to go.", description=HANDOVER, move_away=True)
    views.decide(town, "move_away", views.review_items(town)["leaving"][0]["id"], yes=True, reason="")
    said = views.move_in(town, "archivist")
    newcomer = next(r for r in Registry(town).all() if r.office == "archivist" and r.status == "active")
    assert newcomer.id != "archivist" and newcomer.name == "unchosen"  # it chooses its own name
    [letter] = [i for i in unread(town, newcomer.id) if "Handover" in i.body or "handover" in i.body]
    assert letter.sender == "archivist" and "half of them are done" in letter.body and said
    views.move_in(town, "archivist")  # a second newcomer: the handover went to the first
    third = [r for r in Registry(town).all() if r.office == "archivist" and r.status == "active" and r.id != newcomer.id][0]
    assert not [i for i in unread(town, third.id) if "half of them are done" in i.body]


def test_what_a_request_to_move_away_needs(box, town: Town) -> None:
    archivist = box("archivist")
    with pytest.raises(BatonError, match="handover"):
        archivist.call("propose_change", title="Bye", rationale="Going.", description="Bye.", move_away=True)
    with pytest.raises(BatonError, match="isn't one of your notes"):
        archivist.call("propose_change", title="Bye", rationale="Going.", description=HANDOVER, move_away=True,
                       keep=["../inspector/knowledge/x.md"])
    with pytest.raises(BatonError, match="handing over"):
        box("mayor").call("propose_change", title="Bye", rationale="Going.", description=HANDOVER, move_away=True)
    archivist.call("propose_change", title="Bye", rationale="Going.", description=HANDOVER, move_away=True)
    with pytest.raises(BatonError, match="already asked"):
        archivist.call("propose_change", title="Bye", rationale="Going.", description=HANDOVER, move_away=True)
    assert len(leaving.open_requests(town)) == 1
    assert views.review_items(town)["founding"] == []  # (not a move-in request)
