"""Babo's services' logs, where the web interface and the terminal can read them (step 21).

The services (the gateway, the model queue, upkeep) log to the console, which on the
host goes to journald: out of reach of the web interface, which runs in the agent's
container. Each also keeps its own file here, ``<Babo's data folder>/logs/<service>.log``
(5 MB, then rotated; three kept), read by the Town page's *Activity* tab and
``babo logs``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger

SERVICES = ("gateway", "queue", "upkeep")
LEVELS = ("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")
_TAIL_BYTES = 512 * 1024
_LEVEL = re.compile(r"\|\s*(DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)\s*\|")


def folder() -> Path:
    from babo.config.paths import get_runtime_subdir

    return get_runtime_subdir("logs")


def path(service: str) -> Path:
    if service not in SERVICES:
        raise ValueError(f"the services are: {', '.join(SERVICES)}")
    return folder() / f"{service}.log"


def add_file_sink(service: str) -> int | None:
    """Also log this service to its file (alongside the console). Never stops a service from starting."""
    from babo.utils.log_config import LOG_FORMAT, prepare_log_record

    try:
        return logger.add(path(service), format=LOG_FORMAT, level="INFO", colorize=False, filter=prepare_log_record,
                          rotation="5 MB", retention=3, enqueue=True, encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.warning("Babo: no log file for {}: {}", service, exc)
        return None


def tail(service: str, lines: int = 200, *, level: str = "INFO") -> list[dict[str, Any]]:
    """The last ``lines`` entries of a service's log at ``level`` or above, oldest first. A line without a
    level (a traceback's) belongs to the entry before it."""
    wanted = LEVELS.index(level.upper()) if level.upper() in LEVELS else 1
    try:
        with path(service).open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    if size > _TAIL_BYTES:
        text = text.split("\n", 1)[-1]  # (the first line is likely cut)
    entries: list[dict[str, Any]] = []
    for raw in text.splitlines():
        m = _LEVEL.search(raw)
        if m:
            entries.append({"level": m.group(1), "text": raw})
        elif entries and raw.strip():
            entries[-1]["text"] += "\n" + raw
    return [e for e in entries if LEVELS.index(e["level"]) >= wanted][-lines:]
