"""The town square: threads every resident and the owner can start and reply to (step 23).

The notice board was the Mayor's (open roles, requests, move-in requests for the owner).
The square opens it to everyone, as **threads**: a *question*, an *observation*, a *flag*
(a heads-up for everyone) or an *announcement*, with replies, closed by its author, the
Mayor or the owner. Letters stay for one-to-one.

Threads are files in the commons, ``commons/square/<date>-<slug>.md``, readable by all and
changed only through ``town_square`` (residents), the Square tab and ``babo square`` (the
owner). What's new since a resident last looked is shown, briefly (a line each, at most
five), with where it is now: at the start of its next session, and while it hasn't read
them. Reading the square (or posting to it) counts as looking. A round step can take
``material: square``: what's new on the square, in full.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from filelock import FileLock

from babo.baton.notes import first_line, join_frontmatter, split_frontmatter
from babo.baton.town import OWNER, BatonError, Town, atomic_write, slugify, today

KINDS = ("question", "observation", "flag", "announcement")
MAX_TEXT = 4000
MAX_REPLY = 2000
SHOW_NEW = 5


def now_iso() -> str:
    """To the microsecond: what's new is told apart from what was seen even within a second."""
    return datetime.now().astimezone().isoformat(timespec="microseconds")


@dataclass
class Thread:
    id: str  # the file's name without .md
    kind: str
    title: str
    author: str
    text: str = ""
    status: str = "open"
    created: str = ""
    updated: str = ""
    closed_by: str = ""
    replies: list[dict[str, str]] = field(default_factory=lambda: cast(list[dict[str, str]], []))

    def line(self) -> str:
        replies = f", {len(self.replies)} repl{'y' if len(self.replies) == 1 else 'ies'}" if self.replies else ""
        closed = " (closed)" if self.status == "closed" else ""
        return f"[{self.kind}] {self.title} — {self.author}{replies}{closed} (thread {self.id})"

    def full(self, *, last: int = 10) -> str:
        out = [self.line(), "", self.text]
        if self.replies:
            shown = self.replies[-last:]
            if len(self.replies) > len(shown):
                out.append(f"\n({len(self.replies) - len(shown)} earlier repl(ies))")
            out += ["", "Replies:"] + [f"- {r['at'][:16].replace('T', ' ')} {r['by']}: {r['text']}" for r in shown]
        return "\n".join(out)

    def overview(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "title": self.title, "author": self.author, "text": self.text, "status": self.status,
                "created": self.created, "updated": self.updated, "closed_by": self.closed_by, "replies": self.replies}


def folder(town: Town) -> Path:
    return town.commons / "square"


def _lock(town: Town) -> FileLock:
    return FileLock(str(town.locks / "square.lock"), timeout=10)


def _path(town: Town, thread_id: str) -> Path:
    clean = slugify(thread_id.strip().removesuffix(".md").split("/")[-1], 80)
    return folder(town) / f"{clean}.md"


def _load(path: Path) -> Thread | None:
    try:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    text, _, rest = body.partition("\n## Replies\n")
    replies: list[dict[str, str]] = []
    for line in rest.strip().splitlines():
        if not line.startswith("- "):
            continue
        at, _, more = line[2:].partition(" | ")
        by, _, said = more.partition(": ")
        if at and by:
            replies.append({"at": at.strip(), "by": by.strip(), "text": said.strip()})
    return Thread(path.stem, str(meta.get("kind") or "observation"), str(meta.get("title") or path.stem), str(meta.get("author") or "?"),
                  text.strip(), str(meta.get("status") or "open"), str(meta.get("created") or ""), str(meta.get("updated") or ""),
                  str(meta.get("closed_by") or ""), replies)


def _save(town: Town, t: Thread) -> None:
    meta: dict[str, Any] = {"kind": t.kind, "title": t.title, "author": t.author, "status": t.status, "created": t.created,
                            "updated": t.updated}
    if t.closed_by:
        meta["closed_by"] = t.closed_by
    replies = "".join(f"- {r['at']} | {r['by']}: {r['text']}\n" for r in t.replies)
    folder(town).mkdir(parents=True, exist_ok=True)
    atomic_write(_path(town, t.id), join_frontmatter(meta, t.text + "\n" + (f"\n## Replies\n\n{replies}" if replies else "")))


def threads(town: Town, *, include_closed: bool = False) -> list[Thread]:
    """Newest activity first."""
    base = folder(town)
    found = [_load(p) for p in base.glob("*.md")] if base.is_dir() else []
    return sorted((t for t in found if t is not None and (include_closed or t.status == "open")),
                  key=lambda t: t.updated or t.created, reverse=True)


def get(town: Town, thread_id: str) -> Thread:
    t = _load(_path(town, thread_id))
    if t is None:
        raise BatonError(f"There's no thread '{thread_id}' on the square. Read the square (action read) to see its threads.")
    return t


def post(town: Town, by: str, kind: str, title: str, text: str) -> Thread:
    kind = kind.strip().lower()
    if kind not in KINDS:
        raise BatonError(f"A thread is one of: {', '.join(KINDS)}.")
    text = text.strip()[:MAX_TEXT]
    title = " ".join((title or first_line(text, 80)).split())[:120]
    if not text:
        raise BatonError("Say what the thread is about, in text.")
    stamp = now_iso()
    with _lock(town):
        base = f"{today()}-{slugify(title, 40)}"
        thread_id, n = base, 2
        while _path(town, thread_id).exists():
            thread_id, n = f"{base}-{n}", n + 1
        t = Thread(thread_id, kind, title, by, text, "open", stamp, stamp)
        _save(town, t)
    mark_seen(town, by)
    return t


def reply(town: Town, by: str, thread_id: str, text: str) -> Thread:
    said = " ".join(text.split())[:MAX_REPLY]
    if not said:
        raise BatonError("The reply is empty.")
    with _lock(town):
        t = get(town, thread_id)
        if t.status == "closed":
            raise BatonError(f"{t.id} is closed ({t.closed_by} closed it). Start a new thread to pick it up again.")
        t.updated = now_iso()
        t.replies.append({"at": t.updated, "by": by, "text": said})
        _save(town, t)
    mark_seen(town, by)
    return t


def close(town: Town, by: str, thread_id: str, text: str = "") -> Thread:
    with _lock(town):
        t = get(town, thread_id)
        if by not in (t.author, "mayor", OWNER):
            raise BatonError(f"Only whoever started it ({t.author}), the Mayor or the owner close a thread. You can reply to it.")
        if t.status == "closed":
            return t
        t.updated = now_iso()
        if text.strip():
            t.replies.append({"at": t.updated, "by": by, "text": " ".join(text.split())[:MAX_REPLY]})
        t.status, t.closed_by = "closed", by
        _save(town, t)
    return t


# -- what's new for a resident ----------------------------------------------------------

def _seen_path(town: Town) -> Path:
    return town.state / "square" / "seen.json"


def _seen(town: Town) -> dict[str, str]:
    try:
        raw: object = json.loads(_seen_path(town).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in cast(dict[str, Any], raw).items()} if isinstance(raw, dict) else {}


def mark_seen(town: Town, resident: str) -> None:
    with _lock(town):
        seen = _seen(town)
        seen[resident] = now_iso()
        _seen_path(town).parent.mkdir(parents=True, exist_ok=True)
        atomic_write(_seen_path(town), json.dumps(seen, indent=1) + "\n")


def new_for(town: Town, resident: str) -> list[Thread]:
    """Open threads with something from someone else since the resident last looked (all of them, the first time)."""
    since = _seen(town).get(resident, "")
    out: list[Thread] = []
    for t in threads(town):
        latest = t.replies[-1]["by"] if t.replies else t.author
        if (t.updated or t.created) > since and latest != resident:
            out.append(t)
    return out


def now_text(town: Town, resident: str) -> str:
    """What's new on the square, briefly, for where the resident is now ("" when nothing is)."""
    fresh = new_for(town, resident)
    if not fresh:
        return ""
    lines = ["## New on the square", ""] + [f"- {t.line()}" for t in fresh[:SHOW_NEW]]
    if len(fresh) > SHOW_NEW:
        lines.append(f"- … and {len(fresh) - SHOW_NEW} more")
    return "\n".join(lines) + "\n\nRead them with `town_square` (action read); reply or start one when you have something to add."


def material(town: Town, resident: str) -> str:
    """A round step's material ``square``: what's new on the square, in full ("" when nothing is)."""
    fresh = new_for(town, resident)
    if not fresh:
        return ""
    return "What's new on the town square since you last looked:\n\n" + "\n\n---\n\n".join(t.full(last=5) for t in fresh[:10])


def read_text(town: Town, resident: str, thread_id: str = "") -> str:
    """The square as a resident reads it (``town_square`` action read): one thread in full, or the open ones."""
    if thread_id:
        text = get(town, thread_id).full()
    else:
        open_threads = threads(town)
        fresh = {t.id for t in new_for(town, resident)}
        if not open_threads:
            text = "The square is quiet: no open threads. Start one with action post (a question, an observation, a flag or an announcement)."
        else:
            text = "Open threads on the square, newest first:\n" + "\n".join(
                f"- {'(new) ' if t.id in fresh else ''}{t.line()}" for t in open_threads[:20])
            text += "\n\nOne in full: action read with its thread. Reply with action reply."
    mark_seen(town, resident)
    return text


def overview(town: Town) -> dict[str, Any]:
    return {"threads": [t.overview() for t in threads(town, include_closed=True)], "kinds": list(KINDS)}
