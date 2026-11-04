"""The projects board: the town's projects and their tickets (step 22).

A **project** has a lead (who started it, until it's handed on), a status (*active*,
*paused*, *done*) and *help wanted*, and holds **tickets**: a piece of work with a
status (*open*, *doing*, *blocked*, *done*), who has it, and notes. Both are files in
the commons, next to the project's repository when it has one::

    commons/projects/<project>/PROJECT.md
    commons/projects/<project>/<n>.md      # ticket <project>#<n>

Everyone can read them (``read_note commons/projects/``). They change only through
``project_board`` (residents and the Mayor), the Projects tab and ``babo projects`` (the
owner), so each change is checked and every note says who wrote it and when:

- anyone starts a project (they lead it) or adds a ticket to one;
- anyone *claims* an open ticket nobody has, and adds notes to any ticket;
- a ticket's status and who has it are changed by whoever has it, the project's lead,
  the Mayor or the owner; *blocked* says why;
- a project's status, *help wanted* and lead are changed by its lead, the Mayor or the owner.

A round step's material can be ``tickets``: the open tickets the step's resident has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from filelock import FileLock

from babo.baton.notes import first_line, join_frontmatter, split_frontmatter
from babo.baton.town import OWNER, BatonError, Town, atomic_write, now_iso, slugify

PROJECT_STATUSES = ("active", "paused", "done")
TICKET_STATUSES = ("open", "doing", "blocked", "done")
OPEN = ("open", "doing", "blocked")
MAX_TITLE = 120
MAX_TEXT = 4000
MAX_NOTE = 1000
_REF = re.compile(r"^\s*([a-z0-9][a-z0-9-]*)\s*#\s*(\d+)\s*$")


@dataclass
class Ticket:
    project: str
    number: int
    title: str
    status: str = "open"
    assignee: str = ""
    created_by: str = ""
    created: str = ""
    updated: str = ""
    description: str = ""
    notes: list[str] = field(default_factory=lambda: cast(list[str], []))

    @property
    def ref(self) -> str:
        return f"{self.project}#{self.number}"

    def line(self) -> str:
        who = f", {self.assignee} has it" if self.assignee else ""
        return f"{self.ref} [{self.status}{who}] {self.title}"

    def text(self) -> str:
        out = [self.line()]
        if self.description:
            out.append(self.description)
        if self.notes:
            out.append("Notes:\n" + "\n".join(self.notes[-8:]))
        return "\n".join(out)

    def overview(self) -> dict[str, Any]:
        return {"ref": self.ref, "project": self.project, "number": self.number, "title": self.title, "status": self.status,
                "assignee": self.assignee, "created_by": self.created_by, "created": self.created, "updated": self.updated,
                "description": self.description, "notes": self.notes}


@dataclass
class Project:
    slug: str
    title: str
    lead: str
    status: str = "active"
    help_wanted: bool = False
    created: str = ""
    updated: str = ""
    description: str = ""
    tickets: list[Ticket] = field(default_factory=lambda: cast(list[Ticket], []))

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for t in self.tickets if t.status == s) for s in TICKET_STATUSES}

    def line(self) -> str:
        c = self.counts()
        wanted = ", help wanted" if self.help_wanted else ""
        return (f"{self.slug}: {self.title} [{self.status}{wanted}; lead {self.lead}] "
                f"{c['open']} open, {c['doing']} doing, {c['blocked']} blocked, {c['done']} done")

    def overview(self) -> dict[str, Any]:
        return {"slug": self.slug, "title": self.title, "lead": self.lead, "status": self.status, "help_wanted": self.help_wanted,
                "created": self.created, "updated": self.updated, "description": self.description, "counts": self.counts(),
                "tickets": [t.overview() for t in self.tickets]}


def folder(town: Town) -> Path:
    return town.commons_projects


def _lock(town: Town) -> FileLock:
    return FileLock(str(town.locks / "projects.lock"), timeout=10)


def _clean(text: object, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _title(text: object) -> str:
    title = " ".join(str(text or "").split())[:MAX_TITLE]
    if not title:
        raise BatonError("Give it a title, in a few words.")
    return title


# -- reading ---------------------------------------------------------------------------

def _load_ticket(path: Path, project: str) -> Ticket | None:
    try:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        number = int(path.stem)
    except (OSError, ValueError):
        return None
    description, _, notes = body.partition("\n## Notes\n")
    return Ticket(project, number, str(meta.get("title") or f"ticket {number}"), str(meta.get("status") or "open"),
                  str(meta.get("assignee") or ""), str(meta.get("created_by") or ""), str(meta.get("created") or ""),
                  str(meta.get("updated") or ""), description.strip(),
                  [line for line in notes.strip().splitlines() if line.strip()])


def load(town: Town, slug: str) -> Project | None:
    path = folder(town) / slugify(slug, 40) / "PROJECT.md"
    try:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    project = Project(path.parent.name, str(meta.get("title") or path.parent.name), str(meta.get("lead") or ""),
                      str(meta.get("status") or "active"), bool(meta.get("help_wanted")), str(meta.get("created") or ""),
                      str(meta.get("updated") or ""), body.strip())
    tickets = [_load_ticket(p, project.slug) for p in path.parent.glob("*.md") if p.stem.isdigit()]
    project.tickets = sorted((t for t in tickets if t is not None), key=lambda t: t.number)
    return project


def all_projects(town: Town) -> list[Project]:
    base = folder(town)
    found = [load(town, d.name) for d in sorted(base.iterdir()) if d.is_dir() and (d / "PROJECT.md").exists()] if base.is_dir() else []
    order = {s: i for i, s in enumerate(PROJECT_STATUSES)}
    return sorted((p for p in found if p is not None), key=lambda p: (order.get(p.status, 9), p.slug))


def require(town: Town, slug: str) -> Project:
    project = load(town, slug)
    if project is None:
        known = ", ".join(p.slug for p in all_projects(town)) or "none yet"
        raise BatonError(f"There's no project called '{slug}'. Projects: {known}.")
    return project


def ticket(town: Town, ref: str) -> tuple[Project, Ticket]:
    m = _REF.match(ref.lower())
    if not m:
        raise BatonError(f"'{ref}' isn't a ticket: tickets are named like garden#3 (the project, #, the number).")
    project = require(town, m.group(1))
    for t in project.tickets:
        if t.number == int(m.group(2)):
            return project, t
    raise BatonError(f"{project.slug} has no ticket #{m.group(2)}. Its tickets: "
                     f"{', '.join(t.ref for t in project.tickets) or 'none yet'}.")


def open_tickets_for(town: Town, resident: str) -> list[Ticket]:
    """The tickets a resident has that aren't done, in projects that aren't done."""
    return [t for p in all_projects(town) if p.status != "done" for t in p.tickets if t.assignee == resident and t.status in OPEN]


def help_wanted(town: Town) -> list[Ticket]:
    """Open tickets nobody has, in active projects that asked for help."""
    return [t for p in all_projects(town) if p.status == "active" and p.help_wanted for t in p.tickets
            if t.status == "open" and not t.assignee]


# -- writing ---------------------------------------------------------------------------

def _save_project(town: Town, p: Project) -> Path:
    path = folder(town) / p.slug / "PROJECT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"title": p.title, "lead": p.lead, "status": p.status, "help_wanted": p.help_wanted,
                            "created": p.created, "updated": p.updated}
    atomic_write(path, join_frontmatter(meta, f"# {p.title}\n\n{p.description}\n" if p.description else f"# {p.title}\n"))
    return path


def _save_ticket(town: Town, t: Ticket) -> Path:
    path = folder(town) / t.project / f"{t.number}.md"
    meta: dict[str, Any] = {"title": t.title, "status": t.status, "assignee": t.assignee, "created_by": t.created_by,
                            "created": t.created, "updated": t.updated}
    body = (t.description + "\n" if t.description else "") + ("\n## Notes\n\n" + "\n".join(t.notes) + "\n" if t.notes else "")
    atomic_write(path, join_frontmatter(meta, body or "\n"))
    return path


def _note(t: Ticket, by: str, text: str) -> None:
    t.notes.append(f"- {now_iso()[:16].replace('T', ' ')} {by}: {' '.join(text.split())[:MAX_NOTE]}")


def _may_steer_project(p: Project, by: str) -> bool:
    return by in (p.lead, "mayor", OWNER)


def new_project(town: Town, by: str, title: object, description: object = "", *, help_wanted: bool = False) -> Project:
    name = _title(title)
    slug = slugify(name, 40)
    with _lock(town):
        if load(town, slug) is not None:
            raise BatonError(f"There's already a project called {slug}: add tickets to it, or give this one another title.")
        stamp = now_iso()
        p = Project(slug, name, by, "active", bool(help_wanted), stamp, stamp, _clean(description, MAX_TEXT))
        _save_project(town, p)
    return p


def update_project(town: Town, by: str, slug: str, *, status: str | None = None, help_wanted: bool | None = None,
                   lead: str | None = None, description: str | None = None) -> Project:
    with _lock(town):
        p = require(town, slug)
        if not _may_steer_project(p, by):
            raise BatonError(f"Only {p.slug}'s lead ({p.lead}), the Mayor or the owner change the project itself. "
                             "Add a ticket, or send_letter to the lead.")
        if status is not None:
            if status not in PROJECT_STATUSES:
                raise BatonError(f"A project's status is one of: {', '.join(PROJECT_STATUSES)}.")
            p.status = status
        if help_wanted is not None:
            p.help_wanted = bool(help_wanted)
        if lead:
            p.lead = lead
        if description is not None:
            p.description = _clean(description, MAX_TEXT)
        p.updated = now_iso()
        _save_project(town, p)
    return p


def new_ticket(town: Town, by: str, slug: str, title: object, description: object = "", *, assignee: str = "") -> Ticket:
    with _lock(town):
        p = require(town, slug)
        if p.status == "done":
            raise BatonError(f"{p.slug} is done. Ask its lead ({p.lead}) to make it active again first.")
        stamp = now_iso()
        t = Ticket(p.slug, max((x.number for x in p.tickets), default=0) + 1, _title(title), "doing" if assignee else "open",
                   assignee, by, stamp, stamp, _clean(description, MAX_TEXT))
        _save_ticket(town, t)
    return t


def claim(town: Town, by: str, ref: str) -> Ticket:
    with _lock(town):
        _, t = ticket(town, ref)
        if t.assignee == by:
            return t
        if t.assignee:
            raise BatonError(f"{t.ref} is {t.assignee}'s. Add a note to it, or send_letter to {t.assignee} to take it over.")
        if t.status == "done":
            raise BatonError(f"{t.ref} is done.")
        t.assignee, t.status, t.updated = by, "doing" if t.status == "open" else t.status, now_iso()
        _note(t, by, "took it")
        _save_ticket(town, t)
    return t


def update_ticket(town: Town, by: str, ref: str, *, status: str | None = None, note: str | None = None,
                  assignee: str | None = None) -> Ticket:
    with _lock(town):
        p, t = ticket(town, ref)
        changes = status is not None or assignee is not None
        if changes and by not in (t.assignee, p.lead, "mayor", OWNER):
            who = f"{t.assignee} has it" if t.assignee else "nobody has it yet: claim it first"
            raise BatonError(f"Only whoever has {t.ref}, the project's lead ({p.lead}), the Mayor or the owner change it "
                             f"({who}). You can add a note.")
        if status is not None:
            if status not in TICKET_STATUSES:
                raise BatonError(f"A ticket's status is one of: {', '.join(TICKET_STATUSES)}.")
            if status == "blocked" and not (note or "").strip():
                raise BatonError("Say what it's blocked on, in the note, so whoever can unblock it knows.")
            if status != t.status:
                _note(t, by, f"{t.status} → {status}")
            t.status = status
        if assignee is not None:
            t.assignee = assignee.strip()
            _note(t, by, f"gave it to {t.assignee}" if t.assignee else "let it go")
            if not t.assignee and t.status == "doing":
                t.status = "open"
        if note and note.strip():
            _note(t, by, note)
        if not changes and not (note or "").strip():
            raise BatonError("Nothing to change: give a status, a note, or who has it.")
        t.updated = now_iso()
        _save_ticket(town, t)
    return t


# -- what agents and the owner see ----------------------------------------------------

def board_text(town: Town, slug: str | None = None, *, resident: str = "") -> str:
    """The board as a resident reads it (``project_board`` with action ``list``)."""
    if slug:
        p = require(town, slug)
        lines = [p.line()]
        if p.description:
            lines.append(first_line(p.description, 300))
        for status in TICKET_STATUSES:
            ts = [t for t in p.tickets if t.status == status]
            if ts:
                lines.append(f"\n{status.capitalize()}:")
                lines += [f"- {t.line()}" for t in (ts if status != "done" else ts[-5:])]
        return "\n".join(lines)
    projects = all_projects(town)
    if not projects:
        return "The board is empty: no projects yet. Start one with action new_project."
    lines = ["Projects:"] + [f"- {p.line()}" for p in projects]
    mine = open_tickets_for(town, resident) if resident else []
    if mine:
        lines += ["", "Your open tickets:"] + [f"- {t.line()}" for t in mine]
    wanted = [t for t in help_wanted(town) if t.created_by != resident]
    if wanted:
        lines += ["", "Help wanted (nobody has these):"] + [f"- {t.line()}" for t in wanted[:10]]
    return "\n".join(lines) + "\n\nOne project's tickets: action list with its name. A ticket in full: read_note commons/projects/<project>/<n>.md"


def tickets_material(town: Town, resident: str) -> str:
    """A round step's material ``tickets``: the step resident's open tickets ("" when there are none)."""
    mine = open_tickets_for(town, resident)
    if not mine:
        return ""
    return "Your open tickets (keep them up to date with project_board):\n\n" + "\n\n".join(t.text() for t in mine)


def overview(town: Town) -> dict[str, Any]:
    return {"projects": [p.overview() for p in all_projects(town)], "statuses": list(TICKET_STATUSES),
            "project_statuses": list(PROJECT_STATUSES)}
