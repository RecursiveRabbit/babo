"""Checkpoints and BATON.md.

Every checkpoint is appended to ``checkpoints/YYYY-MM-DD.jsonl`` (the record).
``BATON.md`` shows the latest checkpoint for each thread, newest first, and is
re-rendered from the record whenever a checkpoint is written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from loguru import logger

from babo.baton.town import atomic_write, now_iso, today

LIST_FIELDS = ("done", "learned", "next", "blockers")


def _strs(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in cast(list[object], value)]
    return [str(value)] if value else []


@dataclass
class Checkpoint:
    thread: str
    doing: str = ""
    done: list[str] = field(default_factory=list)
    learned: list[str] = field(default_factory=list)
    next: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    confidence: float = 0.5
    # authored (by the resident) | mechanical (from the event log)
    source: str = "authored"
    trigger: str = ""
    resident: str = ""
    session: str = ""
    at: str = ""
    tool_calls: int = 0

    def to_record(self) -> dict[str, Any]:
        return {
            "at": self.at or now_iso(),
            "resident": self.resident,
            "session": self.session,
            "thread": self.thread,
            "doing": self.doing,
            **{name: list(getattr(self, name)) for name in LIST_FIELDS},
            "confidence": self.confidence,
            "source": self.source,
            "trigger": self.trigger,
            "tool_calls": self.tool_calls,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Checkpoint:
        return cls(
            thread=str(record.get("thread") or "general"),
            doing=str(record.get("doing") or ""),
            done=_strs(record.get("done")),
            learned=_strs(record.get("learned")),
            next=_strs(record.get("next")),
            blockers=_strs(record.get("blockers")),
            confidence=float(record.get("confidence") or 0.0),
            source=str(record.get("source") or "authored"),
            trigger=str(record.get("trigger") or ""),
            resident=str(record.get("resident") or ""),
            session=str(record.get("session") or ""),
            at=str(record.get("at") or ""),
            tool_calls=int(record.get("tool_calls") or 0),
        )

    def render(self) -> str:
        how = "written by me" if self.source == "authored" else "mechanical record from the event log"
        lines = [f"## {self.thread}", f"_{self.at[:16].replace('T', ' ')} · {how} · confidence {self.confidence:.1f}_", ""]
        if self.doing:
            lines.append(f"**Doing:** {self.doing}")
        for name, label in (("done", "Done"), ("learned", "Learned"), ("next", "Next"), ("blockers", "Blockers")):
            items = getattr(self, name)
            if items:
                lines.append(f"**{label}:**")
                lines += [f"- {item}" for item in items]
        return "\n".join(lines).rstrip() + "\n"


_reported: set[tuple[str, int]] = set()


def _records(resident_dir: Path) -> list[tuple[Path, int, Checkpoint | None]]:
    """Every line of the checkpoint record: the checkpoint, or None for a line that isn't one (a line
    written by hand or by a tool, cut short, or not a record at all). Such a line is skipped, never fatal:
    the baton is read for every prompt, so one bad line must not stop the agent (or the Town page)."""
    out: list[tuple[Path, int, Checkpoint | None]] = []
    for path in sorted((resident_dir / "checkpoints").glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            out.append((path, 0, None))
            continue
        for number, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                record: object = json.loads(line)
                checkpoint = Checkpoint.from_record(cast(dict[str, Any], record)) if isinstance(record, dict) else None
            except (ValueError, TypeError):
                checkpoint = None
            out.append((path, number, checkpoint))
    return out


def unreadable_lines(resident_dir: Path) -> list[tuple[Path, int]]:
    """The lines of the checkpoint record that aren't checkpoints (for ``babo doctor``)."""
    return [(path, number) for path, number, checkpoint in _records(resident_dir) if checkpoint is None]


def iter_checkpoints(resident_dir: Path) -> list[Checkpoint]:
    out: list[Checkpoint] = []
    new: dict[str, int] = {}
    for path, number, checkpoint in _records(resident_dir):
        if checkpoint is None:
            if (str(path), number) not in _reported:
                _reported.add((str(path), number))
                new[str(path)] = new.get(str(path), 0) + 1
            continue
        out.append(checkpoint)
    for path, count in new.items():  # (once per file, not once per line)
        logger.warning("Babo: {} line(s) in {} aren't checkpoints; shown to their resident (babo doctor lists them)", count, path)
    out.sort(key=lambda c: c.at)
    return out


def latest_by_thread(resident_dir: Path) -> list[Checkpoint]:
    latest: dict[str, Checkpoint] = {}
    for cp in iter_checkpoints(resident_dir):
        latest[cp.thread] = cp
    return sorted(latest.values(), key=lambda c: c.at, reverse=True)


def current_entry(resident_dir: Path, thread: str | None = None) -> Checkpoint | None:
    entries = latest_by_thread(resident_dir)
    if thread:
        for cp in entries:
            if cp.thread == thread:
                return cp
    return entries[0] if entries else None


# BATON.md stays small: the most recent threads only (every checkpoint stays in checkpoints/).
BATON_THREADS = 12


def render_baton(entries: list[Checkpoint]) -> str:
    if not entries:
        return "# Baton\n\nNo checkpoints yet.\n"
    body = "\n".join(cp.render() for cp in entries[:BATON_THREADS])
    older = len(entries) - BATON_THREADS
    more = f"\n{older} older thread(s) are in checkpoints/ (search_memory finds them).\n" if older > 0 else ""
    return "# Baton\n\nMy latest checkpoint for each thread, newest first.\n\n" + body + more


def append_checkpoint(resident_dir: Path, cp: Checkpoint) -> Path:
    cp.at = cp.at or now_iso()
    path = resident_dir / "checkpoints" / f"{today()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(cp.to_record(), ensure_ascii=False) + "\n")
    atomic_write(resident_dir / "BATON.md", render_baton(latest_by_thread(resident_dir)))
    return path
