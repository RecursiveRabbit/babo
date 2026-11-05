"""Moving away by choice (step 24).

A resident can decide to leave. It asks with ``propose_change`` and ``move_away``: why it
is going (the rationale), a **handover** for whoever takes its office next (the
description), and the notes of its own worth keeping in the commons (``keep``). The
request goes on the notice board and into the owner's Review.

The owner can't refuse it, only acknowledge it (and talk it over first, in a session
with the resident, if they want to). Acknowledging it:

- nominates the notes it chose for the commons (the Archivist curates them, as any
  nomination);
- files the handover, ``commons/handovers/<office>/<date>-<resident>.md``;
- moves the resident away: its sessions are frozen, its folder and memory stay, and its
  office is a vacancy.

The next newcomer to that office gets the handover as a letter from its predecessor,
in its first session. A newcomer chooses its own name; nothing is named for it.

The Mayor moves away differently, by handing over to a newcomer in its office (a later
part of this step).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from babo.baton.inbox import deliver
from babo.baton.notes import Note, first_line, join_frontmatter, split_frontmatter
from babo.baton.registry import Registry
from babo.baton.town import OWNER, BatonError, Town, atomic_write, now_iso, slugify, today

KIND = "move_away_request"
MAX_KEEP = 10


def _resident_note(town: Town, resident: str, ref: str) -> Path:
    ref = ref.strip().strip("`\"'").strip("/")
    if ref.startswith(f"residents/{resident}/"):
        ref = ref.split("/", 2)[2]
    home = town.resident_dir(resident).resolve()
    path = (home / ref).resolve()
    if path.suffix != ".md":
        path = path.with_suffix(".md")
    if not path.is_relative_to(home / "knowledge") or not path.is_file():
        raise BatonError(f"'{ref}' isn't one of your notes in knowledge/. Give your own notes to keep, like knowledge/soil.md.")
    return path


def request(town: Town, resident: str, *, reason: str, handover: str, keep: list[str] | None = None) -> Path:
    """A resident asks to move away. Nothing happens until the owner acknowledges it."""
    me = Registry(town).require_active(resident)
    if me.office == "mayor":
        raise BatonError("The Mayor moves away by handing over to a newcomer in the Mayor's office; that isn't here yet. "
                         f"Tell {town.owner_name} you'd like to go, and why.")
    if not reason.strip():
        raise BatonError("Say why you're moving away (the rationale): it goes to the owner with the request.")
    if len(handover.strip()) < 40:
        raise BatonError("Write a handover (the description) for whoever takes your office next: what you were doing, what's "
                         "unfinished, who to ask, what you'd want them to know. A few lines at least.")
    if any(meta.get("author") == resident for meta, _ in (_meta(p) for p in open_requests(town))):
        raise BatonError("You've already asked to move away; the owner hasn't acknowledged it yet.")
    kept = [str(_resident_note(town, resident, ref).relative_to(town.root)) for ref in (keep or [])[:MAX_KEEP]]
    meta: dict[str, Any] = {"kind": KIND, "author": resident, "office": me.office, "created": now_iso(), "status": "open",
                            "reason": " ".join(reason.split())[:2000], "keep": kept}
    path = town.board / f"{today()}-move_away-{resident}.md"
    n = 2
    while path.exists():
        path = path.with_name(f"{today()}-move_away-{resident}-{n}.md")
        n += 1
    town.board.mkdir(parents=True, exist_ok=True)
    atomic_write(path, join_frontmatter(meta, handover.strip() + "\n"))
    from babo.baton import notices

    notices.add(town, "move_away_request", f"{resident} has asked to move away: {first_line(reason, 160)}", resident=resident)
    return path


def _meta(path: Path) -> tuple[dict[str, Any], str]:
    return split_frontmatter(path.read_text(encoding="utf-8"))


def open_requests(town: Town) -> list[Path]:
    return [p for p in sorted(town.board.glob("*.md")) if (m := _meta(p)[0]).get("kind") == KIND and m.get("status") == "open"] \
        if town.board.is_dir() else []


def describe(town: Town, path: Path) -> dict[str, Any]:
    meta, body = _meta(path)
    return {"id": path.name, "resident": str(meta.get("author") or ""), "office": str(meta.get("office") or ""),
            "reason": str(meta.get("reason") or ""), "handover": body.strip(),
            "keep": [str(k) for k in cast(list[object], meta.get("keep") or [])], "created": str(meta.get("created") or "")}


def acknowledge(town: Town, path: Path, *, note: str = "") -> str:
    """The owner acknowledges a move-away request: the notes go for curation, the handover is filed, and the
    resident moves away."""
    from babo.baton import views

    meta, body = _meta(path)
    if meta.get("kind") != KIND or meta.get("status") != "open":
        raise BatonError(f"{path.name} isn't an open move-away request.")
    resident, office = str(meta.get("author")), str(meta.get("office"))
    nominated: list[str] = []
    for ref in cast(list[object], meta.get("keep") or []):
        source = town.root / str(ref)
        if not source.is_file():
            continue
        kept = Note.load(source)
        target = town.promotions / f"{today()}-{resident}-{slugify(kept.title)}.md"
        town.promotions.mkdir(parents=True, exist_ok=True)
        atomic_write(target, join_frontmatter({
            "from": resident, "note": str(ref), "title": kept.title, "reason": "Kept for the town as it moved away.",
            "created": now_iso(), "status": "pending", "aliases": kept.aliases, "keywords": kept.keywords}, kept.body))
        nominated.append(kept.title)
    handover = town.commons / "handovers" / slugify(office, 28) / f"{today()}-{resident}.md"
    handover.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(handover, join_frontmatter({"from": resident, "office": office, "written": str(meta.get("created") or now_iso()),
                                             "delivered_to": ""}, body.strip() + "\n"))
    if note.strip():
        from babo.baton import notices

        notices.add(town, "moved_away", f"{town.owner_name} on {resident} moving away: {first_line(note, 200)}", resident=resident)
    meta.update({"status": "acknowledged", "decided": now_iso(), "decided_by": OWNER, "decision_note": note.strip(),
                 "handover": str(handover.relative_to(town.root))})
    atomic_write(path, join_frontmatter(meta, body))
    said = views.move_away(town, resident)
    if nominated:
        said += f" Its notes for the commons are waiting to be curated: {', '.join(nominated)}."
    return said + f" Its handover is in {handover.relative_to(town.root)}, for whoever moves into the {office} next."


def hand_over(town: Town, office: str, newcomer: str) -> list[str]:
    """A newcomer moves into ``office``: the handovers waiting there come to it as letters from its predecessors."""
    folder = town.commons / "handovers" / slugify(office, 28)
    sent: list[str] = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("delivered_to"):
            continue
        sender = str(meta.get("from") or "your predecessor")
        deliver(town, newcomer, kind="letter", sender=sender, subject=f"Handover: the {office}",
                text=f"A handover from {sender}, who held the {office} before you and moved away. It's yours to read, use "
                     f"or set aside.\n\n{body.strip()}\n\n(Kept in {path.relative_to(town.root)}.)")
        meta["delivered_to"] = newcomer
        atomic_write(path, join_frontmatter(meta, body))
        sent.append(path.name)
    return sent
