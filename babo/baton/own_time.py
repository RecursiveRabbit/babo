"""Own time: a slot for each resident that is its own (step 26).

Every so often (weekly, unless the owner sets daily or off, for the town or for one
resident), upkeep gives each resident a turn that asks nothing of it: to reflect on
what it's been doing, revise itself (``revise_self``), write a lesson or a letter, post
on the square, move a project of its own on, or simply rest. It runs with the resident's
own profile, when the model is free, like the rounds, and is shown beside them (the Rounds
tab, ``babo own-time``) with what it said it did. The owner can give a resident its time
now, too.

What a resident does with it is its own: Babo writes down only the few lines it says
about it, as it does for a round step.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from babo.baton.registry import Registry
from babo.baton.town import BatonError, Town, atomic_write, now_iso

EVERY = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
CHOICES = ("daily", "weekly", "off")
DEFAULT = "weekly"
MARK = "[Babo: your own time]"

MESSAGE = (
    f"{MARK} This is your own time ({{when}}). Nothing is asked of you, and nobody is waiting on you. It's yours to use as "
    "you like: look back on what you've been doing and what you'd do differently; revise how you see yourself "
    "(`revise_self`); write down a lesson worth keeping; write a letter to a neighbour; start a thread on the square; move a "
    "project of your own on; or rest. When you're done, say in a few lines what you did with it (or that you rested): "
    "that's all Babo keeps of it."
)


def _settings_path(town: Town) -> Path:
    return town.state / "own-time.json"


def _runs_path(town: Town) -> Path:
    return town.state / "own-time" / "runs.jsonl"


def _requests_path(town: Town) -> Path:
    return town.state / "runtime" / "own-time-requests.json"


def settings(town: Town) -> dict[str, Any]:
    try:
        data: object = json.loads(_settings_path(town).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    raw = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    every = str(raw.get("every") or DEFAULT)
    residents = cast(dict[str, Any], raw.get("residents") or {}) if isinstance(raw.get("residents"), dict) else {}
    return {"every": every if every in CHOICES else DEFAULT,
            "residents": {str(k): str(v) for k, v in residents.items() if str(v) in CHOICES}}


def set_every(town: Town, every: str, resident: str = "") -> str:
    """How often own time comes: for the town, or (``resident``) for one resident ("" to follow the town)."""
    every = every.strip().lower()
    current = settings(town)
    if resident:
        agent = Registry(town).require_active(resident)
        if every in ("", "town", "default"):
            current["residents"].pop(agent.id, None)
            said = f"{agent.id}'s own time follows the town's ({current['every']})."
        elif every in CHOICES:
            current["residents"][agent.id] = every
            said = f"{agent.id}'s own time: {every}."
        else:
            raise BatonError(f"Own time is one of: {', '.join(CHOICES)} (or town, to follow the town's).")
    else:
        if every not in CHOICES:
            raise BatonError(f"Own time is one of: {', '.join(CHOICES)}.")
        current["every"] = every
        said = f"Own time for the town: {every}."
    _settings_path(town).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(_settings_path(town), json.dumps(current, indent=2) + "\n")
    return said


def every_for(town: Town, resident: str) -> str:
    s = settings(town)
    return s["residents"].get(resident, s["every"])


def runs(town: Town, resident: str | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    try:
        lines = _runs_path(town).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = cast(dict[str, Any], json.loads(line))
        except ValueError:
            continue
        if resident is None or item.get("resident") == resident:
            out.append(item)
    return list(reversed(out))[:limit]


def _last(town: Town, resident: str) -> datetime | None:
    for item in runs(town, resident, limit=50):
        try:
            return datetime.fromisoformat(str(item.get("started")))
        except ValueError:
            continue
    return None


def request(town: Town, resident: str) -> str:
    """The owner gives a resident its own time now (upkeep starts it within a minute, when the model is free)."""
    from babo.baton import activity

    agent = Registry(town).require_active(resident)
    wanted = requested(town)
    if agent.id not in wanted:
        wanted.append(agent.id)
    _requests_path(town).parent.mkdir(parents=True, exist_ok=True)
    atomic_write(_requests_path(town), json.dumps(wanted) + "\n")
    activity.note(town, f"own_time:{agent.id}", "own_time", f"{agent.id}'s own time", status="waiting",
                  detail="starts within a minute, when the model is free", resident=agent.id)
    return f"{agent.id}'s own time starts within a minute, when the model is free."


def requested(town: Town) -> list[str]:
    try:
        data: object = json.loads(_requests_path(town).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(x) for x in cast(list[object], data)] if isinstance(data, list) else []


def clear_requests(town: Town) -> None:
    _requests_path(town).unlink(missing_ok=True)


def due(town: Town, *, now: datetime) -> list[tuple[str, str]]:
    """Whose own time it is, each with why: asked for by the owner, or its time has come round."""
    out: list[tuple[str, str]] = [(r, "given by the owner") for r in requested(town)]
    asked = {r for r, _ in out}
    for agent in Registry(town).all():
        if agent.status != "active" or agent.id in asked or not agent.first_session_done:
            continue
        every = every_for(town, agent.id)
        if every == "off":
            continue
        last = _last(town, agent.id)
        if last is None or now - last >= EVERY[every]:
            out.append((agent.id, f"its {every} own time"))
    return out


def record(town: Town, resident: str, *, started: str, status: str, said: str, why: str) -> dict[str, Any]:
    item = {"resident": resident, "started": started, "finished": now_iso(), "status": status, "why": why, "said": said[:2000]}
    _runs_path(town).parent.mkdir(parents=True, exist_ok=True)
    with _runs_path(town).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def next_time(town: Town, resident: str) -> str:
    every = every_for(town, resident)
    if every == "off":
        return ""
    last = _last(town, resident)
    return (last + EVERY[every]).isoformat(timespec="minutes") if last else "at the next upkeep pass"


def overview(town: Town) -> dict[str, Any]:
    s = settings(town)
    rows = [{"resident": a.id, "name": "" if a.name == "unchosen" else a.name, "office": a.office, "every": every_for(town, a.id),
             "own_setting": a.id in s["residents"], "next": next_time(town, a.id), "recent": runs(town, a.id, limit=3)}
            for a in Registry(town).all() if a.status == "active"]
    return {"every": s["every"], "choices": list(CHOICES), "residents": rows}
