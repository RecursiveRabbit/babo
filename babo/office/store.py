"""Where the office keeps what the owner said: desired agents and project crews.

``state/agents.json`` is the desired-state record — one entry per managed agent,
written only through the office's configuration actions, never by a runtime
read (a cached "current state" here would be the duplicate registry the contract
forbids). Crews are files beside their project, so residents can read them with
what they already have: ``commons/projects/<slug>/CREW.md``.

Both are checked writes: an agent's resident must be a registered resident, and
a project must exist before a crew can stand on it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from filelock import FileLock

from babo.baton import projects as project_board
from babo.baton.notes import join_frontmatter, split_frontmatter
from babo.baton.registry import Registry
from babo.baton.town import BatonError, Town, atomic_write, now_iso

HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
CREW_FILE = "CREW.md"
# The four labels Babo emits in records; the Manager adds `babo.launch` at run.
LABEL_KEYS = ("babo.managed", "babo.resident", "babo.project", "babo.crew")


def _handle(value: object) -> str:
    handle = str(value or "").strip().lower()
    if not HANDLE_RE.match(handle):
        raise BatonError("an agent's handle is lowercase letters, digits and dashes (at most 63 characters)")
    return handle


def _known_resident(town: Town, value: object, what: str = "resident") -> str:
    resident = str(value or "").strip()
    if not resident:
        raise BatonError(f"missing {what}")
    if Registry(town).get(resident) is None:
        raise BatonError(f"'{resident}' isn't a resident of this town, so it can't be a {what}")
    return resident


class AgentStore:
    """The desired-state record for managed agents (``state/agents.json``)."""

    def __init__(self, town: Town) -> None:
        self.path: Path = town.state / "agents.json"
        self._lock = FileLock(str(town.locks / "agents.lock"), timeout=30)

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        agents = raw.get("agents")
        return cast(dict[str, Any], agents) if isinstance(agents, dict) else {}

    def all(self) -> dict[str, dict[str, Any]]:
        return {handle: cast(dict[str, Any], entry) for handle, entry in self.load().items()
                if isinstance(entry, dict)}

    def get(self, handle: str) -> dict[str, Any] | None:
        entry = self.load().get(handle)
        return cast(dict[str, Any], entry) if isinstance(entry, dict) else None

    def upsert(self, entry: dict[str, Any]) -> dict[str, Any]:
        handle = _handle(entry.get("handle"))
        with self._lock:
            agents = self.load()
            raw_previous = agents.get(handle)
            previous: dict[str, Any] = raw_previous if isinstance(raw_previous, dict) else {}
            saved = {
                "handle": handle,
                "resident": str(entry.get("resident") or previous.get("resident") or ""),
                "project": str(entry.get("project") or previous.get("project") or ""),
                "crew": str(entry.get("crew") or previous.get("crew") or ""),
                "desired": str(entry.get("desired") or previous.get("desired") or "running"),
                "labels": dict(entry.get("labels") or previous.get("labels") or {}),
                "created": str(previous.get("created") or now_iso()),
                "updated": now_iso(),
            }
            agents[handle] = saved
            atomic_write(self.path, json.dumps({"agents": agents}, indent=2, sort_keys=True) + "\n")
        return saved

    def remove(self, handle: str) -> bool:
        with self._lock:
            agents = self.load()
            if agents.pop(_handle(handle), None) is None:
                return False
            atomic_write(self.path, json.dumps({"agents": agents}, indent=2, sort_keys=True) + "\n")
        return True

    # -- checked changes --------------------------------------------------
    def record(self, town: Town, change: dict[str, Any]) -> str:
        """Record or update one desired agent. Its resident must be a resident."""
        handle = _handle(change.get("handle") or change.get("agent"))
        resident = _known_resident(town, change.get("resident"))
        project = str(change.get("project") or "").strip()
        if project and project_board.load(town, project) is None:
            raise BatonError(f"there's no project '{project}' for this agent to work on")
        crew = str(change.get("crew") or project).strip()
        desired = str(change.get("desired") or "running").strip()
        if desired not in ("running", "frozen"):
            raise BatonError("an agent's desired state is running (awake) or frozen")
        labels = {"babo.managed": "true", "babo.resident": resident}
        if project:
            labels["babo.project"] = project
            labels["babo.crew"] = crew
        self.upsert({"handle": handle, "resident": resident, "project": project, "crew": crew,
                     "desired": desired, "labels": labels})
        return f"Recorded {handle} for {resident}{f' on {project}' if project else ''} (desired: {desired})."

    def set_desired(self, handle: str, desired: str) -> None:
        entry = self.get(handle)
        if entry is None:
            raise BatonError(f"'{handle}' isn't recorded here, so it has no desired state to change")
        entry["desired"] = desired
        self.upsert(entry)


class CrewStore:
    """A project's crew, as a file beside the project (``commons/projects/<slug>/CREW.md``)."""

    def __init__(self, town: Town) -> None:
        self.town = town

    def _file(self, project: str) -> Path:
        return project_board.folder(self.town) / project / CREW_FILE

    def read(self, project: str) -> dict[str, Any]:
        path = self._file(project)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {"project": project, "lead": "", "crew": [], "exists": False}
        meta, _body = split_frontmatter(text)
        lead = str(meta.get("lead") or "")
        raw = meta.get("crew") or []
        crew = [str(m) for m in cast(list[object], raw)] if isinstance(raw, list) else []
        return {"project": project, "lead": lead, "crew": crew, "exists": True}

    def write(self, change: dict[str, Any]) -> str:
        """Set a project's one lead and its crew. Handles are the agents' names."""
        project = str(change.get("project") or "").strip()
        if project_board.load(self.town, project) is None:
            raise BatonError(f"there's no project '{project}' to give a crew")
        lead = _handle(change.get("lead")) if str(change.get("lead") or "").strip() else ""
        raw_crew = change.get("crew") or []
        if not isinstance(raw_crew, list):
            raise BatonError("crew must be a list of agent handles")
        crew = [_handle(m) for m in cast(list[object], raw_crew)]
        crew = [m for m in crew if m != lead]
        path = self._file(project)
        if not crew and not lead:
            if path.exists():
                path.unlink()
            return f"No lead and no crew on {project}; its file is gone."
        body = (f"The office on {project}: one lead, and the crew. The lead's role is routing and "
                f"review; authority stays with each agent's own profile and the owner's decisions.\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, join_frontmatter({"lead": lead, "crew": crew}, body))
        return f"The office on {project}: lead {lead or '(none)'}, crew of {len(crew)}."

    def all(self) -> dict[str, dict[str, Any]]:
        return {p.slug: self.read(p.slug) for p in project_board.all_projects(self.town)}
