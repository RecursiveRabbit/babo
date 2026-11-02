"""Checkpoints and BATON.md.

Every checkpoint is appended to ``checkpoints/YYYY-MM-DD.jsonl`` (the record).
``BATON.md`` shows the latest checkpoint for each thread, newest first, and is
re-rendered from the record whenever a checkpoint is written.

The content is the resident's; the format is Babo's. A resident writes its record
only with its tools: ``checkpoint`` adds an entry, ``correct_checkpoint`` corrects
one (a correction is a new entry that names the one it corrects: nothing is ever
rewritten, and both stay in the history). Edits to ``checkpoints/`` and
``BATON.md`` by hand or with a file tool are refused, with what to use instead.

A line in the record that isn't a checkpoint (written by a shell command, or
before the record was gated) is never fatal, never dropped and never changed: it
is shown back to its resident, word for word, until the resident says with
``correct_checkpoint`` what it was meant to be.
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
    corrects: str = ""  # the entry (its time) or stray line (file:line) this one corrects

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
            **({"corrects": self.corrects} if self.corrects else {}),
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
            corrects=str(record.get("corrects") or ""),
        )

    def render(self) -> str:
        how = "written by me" if self.source == "authored" else "mechanical record from the event log"
        if self.corrects:
            how += f", correcting {self.corrects}"
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


# -- the record's gate, corrections, and lines that aren't checkpoints ------------------------

RECORD_REFUSAL = ("Your record (checkpoints/ and BATON.md) is written only with your tools, so it always reads: "
                  "`checkpoint` adds an entry, `correct_checkpoint` corrects one. Your own notes go in knowledge/, "
                  "or use `remember`.")
RESOLVED = "resolved.json"  # stray lines their resident has said what to make of (Babo writes it)
STRAY_SHOWN = 3
STRAY_CHARS = 400


def is_record_path(resident_dir: Path, path: Path) -> bool:
    """Whether ``path`` is part of the resident's record (``checkpoints/`` or ``BATON.md``)."""
    try:
        resolved = path.resolve()
        home = resident_dir.resolve()
    except OSError:
        return False
    return resolved == home / "BATON.md" or resolved.is_relative_to(home / "checkpoints")


def stray_ref(resident_dir: Path, path: Path, number: int) -> str:
    return f"{path.relative_to(resident_dir).as_posix()}:{number}"


def _resolved(resident_dir: Path) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads((resident_dir / "checkpoints" / RESOLVED).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return {}


def strays(resident_dir: Path) -> list[tuple[str, str]]:
    """Lines in the record that aren't checkpoints and haven't been resolved: ``(ref, text)``."""
    done = _resolved(resident_dir)
    out: list[tuple[str, str]] = []
    for path, number in unreadable_lines(resident_dir):
        ref = stray_ref(resident_dir, path, number)
        if ref in done or number == 0:
            continue
        try:
            line = path.read_text(encoding="utf-8").splitlines()[number - 1].strip()
        except (OSError, IndexError, UnicodeDecodeError):
            continue
        try:
            value: object = json.loads(line)
            text = value if isinstance(value, str) else line
        except ValueError:
            text = line
        out.append((ref, text))
    return out


def strays_text(resident_dir: Path) -> str:
    """What the resident sees of them, with its baton, until it resolves them."""
    found = strays(resident_dir)
    if not found:
        return ""
    lines = ["## Also in your record, not written as checkpoints", "",
             "Babo left these exactly as they are. Say what each was meant to be with `correct_checkpoint` "
             "(`entry` is the place shown; give the checkpoint it should have been, or `keep_as_note`)."]
    for ref, text in found[:STRAY_SHOWN]:
        shown = text if len(text) <= STRAY_CHARS else text[:STRAY_CHARS].rstrip() + " …"
        lines.append(f"- `{ref}`: \"{shown}\"")
    if len(found) > STRAY_SHOWN:
        lines.append(f"- … and {len(found) - STRAY_SHOWN} more.")
    return "\n".join(lines)


def _mark_resolved(resident_dir: Path, ref: str, how: str) -> None:
    done = _resolved(resident_dir)
    done[ref] = {"as": how, "at": now_iso()}
    path = resident_dir / "checkpoints" / RESOLVED
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(done, ensure_ascii=False, indent=1) + "\n")


def find_entry(resident_dir: Path, when: str) -> Checkpoint | None:
    """A checkpoint by its time, as its baton shows it (``2026-11-02 05:59``) or in full."""
    wanted = when.strip().replace("T", " ")[:19]
    if len(wanted) < 16:
        return None
    matches = [c for c in iter_checkpoints(resident_dir) if c.at.replace("T", " ")[:len(wanted)] == wanted]
    return matches[-1] if matches else None


def correct(resident_dir: Path, resident: str, entry: str, fields: dict[str, Any], *, session: str = "") -> str:
    """Correct an entry, or say what a stray line was meant to be, with a new entry naming it (nothing is
    rewritten). ``fields`` are the checkpoint as it should be; for an entry, what isn't given is kept."""
    ref = entry.strip()
    stray = next((r for r, _ in strays(resident_dir) if r == ref.replace(" line ", ":")), None)
    base = None if stray else find_entry(resident_dir, ref)
    if stray is None and base is None:
        raise ValueError(f"Nothing in your record is `{ref}`: give an entry's time as your baton shows it "
                         "(2026-11-02 05:59), or a line as Babo showed it (checkpoints/2026-11-02.jsonl:3).")
    known = {"thread", "doing", "confidence", *LIST_FIELDS}
    unknown = set(fields) - known
    if unknown:
        raise ValueError(f"A checkpoint has: {', '.join(sorted(known))} (not {', '.join(sorted(unknown))})")
    data: dict[str, Any] = base.to_record() if base else {"thread": "general", "confidence": 0.5}
    data.update({k: v for k, v in fields.items() if v is not None})
    cp = Checkpoint.from_record({**data, "at": "", "resident": resident, "session": session, "source": "authored",
                                 "trigger": "correction", "tool_calls": 0, "corrects": stray or (base.at if base else ref)})
    if not cp.doing and not any(getattr(cp, name) for name in LIST_FIELDS):
        raise ValueError("Say what it should be: at least `doing`, or what was done, learned or next.")
    append_checkpoint(resident_dir, cp)
    if stray:
        _mark_resolved(resident_dir, stray, "checkpoint")
        return f"Done: `{stray}` is now a checkpoint in your record (the line itself stays, untouched)."
    return f"Done: your entry of {cp.corrects[:16].replace('T', ' ')} is corrected; your baton shows the correction."


def keep_as_note(resident_dir: Path, ref: str) -> str:
    """A stray line the resident keeps as a note: marked resolved; returns its text (the caller files the note)."""
    for found, text in strays(resident_dir):
        if found == ref.strip().replace(" line ", ":"):
            _mark_resolved(resident_dir, found, "note")
            return text
    raise ValueError(f"`{ref}` isn't a line Babo is showing you from your record.")
