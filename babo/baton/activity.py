"""What Babo is working on right now, so every interface can show it where it was asked for (step 20).

Something that takes a while (a checkpoint being written, a session being frozen and
reviewed, a round or a rehearsal, an eval, upkeep asked for now) has one entry here,
by its *key* (``checkpoint:<resident>:<session>``, ``round:<name>`` ...): *waiting*
(asked for, not started yet), *running*, then *done* or *failed*, with when it
started and how it went. The web interface shows an entry beside the button that
asked for it; the terminal waits on it with a spinner; ``babo activity`` lists them.

One file (``state/runtime/activity.json``), small: finished entries are kept for a
while so "done 12 s ago" can be shown, then dropped.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from filelock import FileLock

from babo.baton.town import Town, atomic_write, now_iso

STATES = ("waiting", "running", "done", "failed")
KEEP_FINISHED = timedelta(minutes=30)
KEEP_AT_MOST = 60


@dataclass
class Activity:
    key: str
    kind: str  # checkpoint | freeze | round | rehearsal | eval | upkeep
    label: str  # what it is, in a few words ("archivist: writing a checkpoint")
    status: str = "running"
    detail: str = ""  # how it went, or what it's waiting for
    started: str = ""
    finished: str = ""
    resident: str = ""
    session: str = ""

    @property
    def active(self) -> bool:
        return self.status in ("waiting", "running")


def _path(town: Town) -> Path:
    return town.state / "runtime" / "activity.json"


def _lock(town: Town) -> FileLock:
    return FileLock(str(town.locks / "activity.lock"), timeout=10)


def _read(town: Town) -> dict[str, Activity]:
    try:
        raw: object = json.loads(_path(town).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    out: dict[str, Activity] = {}
    for item in cast(list[dict[str, Any]], raw) if isinstance(raw, list) else []:
        try:
            entry = Activity(**{k: str(v) for k, v in item.items() if k in Activity.__dataclass_fields__})
        except TypeError:
            continue
        out[entry.key] = entry
    return out


def _write(town: Town, entries: dict[str, Activity]) -> None:
    cutoff = (datetime.now().astimezone() - KEEP_FINISHED).isoformat(timespec="seconds")
    kept = [e for e in entries.values() if e.active or (e.finished or e.started) >= cutoff]
    kept.sort(key=lambda e: e.started, reverse=True)
    _path(town).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(_path(town), json.dumps([asdict(e) for e in kept[:KEEP_AT_MOST]], ensure_ascii=False) + "\n")


def note(town: Town, key: str, kind: str, label: str, *, status: str = "running", detail: str = "",
         resident: str = "", session: str = "") -> Activity:
    """Start (or restart) the entry for ``key``."""
    assert status in STATES
    entry = Activity(key, kind, label, status, detail, now_iso(), "" if status in ("waiting", "running") else now_iso(),
                     resident, session)
    with _lock(town):
        entries = _read(town)
        entries[key] = entry
        _write(town, entries)
    return entry


def update(town: Town, key: str, status: str, detail: str = "") -> None:
    """Move the entry for ``key`` on (``running``, ``done``, ``failed``); nothing if there's none."""
    assert status in STATES
    with _lock(town):
        entries = _read(town)
        entry = entries.get(key)
        if entry is None:
            return
        if entry.status == "waiting" and status == "running":
            entry.started = now_iso()  # (how long it has been running, not waiting)
        entry.status, entry.detail = status, detail or entry.detail
        entry.finished = now_iso() if status in ("done", "failed") else ""
        _write(town, entries)


@contextmanager
def tracked(town: Town, key: str, kind: str, label: str, *, resident: str = "", session: str = "") -> Generator[Activity]:
    """Run something as the entry for ``key``: running, then done or failed (with why)."""
    entry = note(town, key, kind, label, resident=resident, session=session)
    try:
        yield entry
    except BaseException as exc:
        update(town, key, "failed", f"{type(exc).__name__}: {exc}"[:300])
        raise
    update(town, key, "done", entry.detail)


def recent(town: Town) -> list[Activity]:
    """Everything running or waiting, and what finished in the last half hour, newest first."""
    newest = sorted(_read(town).values(), key=lambda e: e.started, reverse=True)
    return sorted(newest, key=lambda e: not e.active)  # (stable: the running ones first, each group newest first)


def get(town: Town, key: str) -> Activity | None:
    return _read(town).get(key)


def overview(town: Town) -> list[dict[str, Any]]:
    return [{**asdict(e), "active": e.active} for e in recent(town)]
