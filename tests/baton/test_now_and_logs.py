"""What's happening right now, and Babo's services' logs: the terminal, the web and the files they read."""

from __future__ import annotations

from pathlib import Path

import pytest

from babo.baton import activity, logs, views
from babo.baton.town import Town

LOG = """2026-11-04 10:00:00.000 | INFO     | babo.cli.gateway:serve:12 - Gateway started
2026-11-04 10:00:01.000 | DEBUG    | babo.agent:turn:3 - a detail
2026-11-04 10:00:02.000 | WARNING  | babo.agent:turn:9 - slow reply
2026-11-04 10:00:03.000 | ERROR    | babo.agent:turn:20 - it broke
Traceback (most recent call last):
  File "x.py", line 1, in <module>
RuntimeError: no model
2026-11-04 10:00:04.000 | INFO     | babo.agent:turn:30 - carried on
"""


@pytest.fixture
def log_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(logs, "folder", lambda: tmp_path)
    (tmp_path / "gateway.log").write_text(LOG, encoding="utf-8")
    return tmp_path


def test_a_log_is_read_by_entry_with_a_traceback_kept_with_its_error(log_folder: Path) -> None:
    entries = logs.tail("gateway")
    assert [e["level"] for e in entries] == ["INFO", "WARNING", "ERROR", "INFO"]
    assert entries[2]["text"].endswith("RuntimeError: no model") and "Traceback" in entries[2]["text"]
    assert [e["level"] for e in logs.tail("gateway", level="WARNING")] == ["WARNING", "ERROR"]
    assert len(logs.tail("gateway", level="DEBUG")) == 5
    assert [e["text"].endswith("carried on") for e in logs.tail("gateway", 1)] == [True]
    assert logs.tail("queue") == []  # not written yet
    with pytest.raises(ValueError):
        logs.path("../config")


def test_a_service_logs_to_its_file(log_folder: Path) -> None:
    from loguru import logger

    sink = logs.add_file_sink("upkeep")
    assert sink is not None
    try:
        logger.info("Upkeep pass done")
        logger.complete()
    finally:
        logger.remove(sink)
    assert [e["text"].endswith("Upkeep pass done") for e in logs.tail("upkeep")] == [True]


def test_right_now_says_what_is_running(town: Town, make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(views, "_queue_stats", lambda _cfg: {"slots": 2, "active": 1, "waiting": 3})
    activity.note(town, "round:night", "round", "The night round", detail="step 2")
    now = views.right_now(town, make_config("mayor").baton)
    assert now["queue"]["waiting"] == 3 and [a["key"] for a in now["activity"]] == ["round:night"]
    assert now["sessions"] == [] and now["errands"] == [] and "waiting" in now["upkeep"]


def test_the_terminal_shows_now_and_logs(town: Town, make_config, log_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rich.console import Console
    from typer.testing import CliRunner

    from babo.baton import cli

    monkeypatch.setattr(cli, "_town", lambda _config: (town, make_config("mayor")))
    monkeypatch.setattr(cli, "console", Console(width=200, force_terminal=False))
    monkeypatch.setattr(views, "_queue_stats", lambda _cfg: {})
    out = CliRunner().invoke(cli.app, ["now"]).output
    assert "the queue isn't answering" in out and "All quiet" in out
    activity.note(town, "eval:town", "eval", "Eval of town", detail="3 of 31 tasks")
    assert "Eval of town" in CliRunner().invoke(cli.app, ["now"]).output
    out = CliRunner().invoke(cli.app, ["logs", "--level", "ERROR"]).output
    assert "it broke" in out and "RuntimeError: no model" in out and "carried on" not in out
    assert "Nothing logged yet" in CliRunner().invoke(cli.app, ["logs", "queue"]).output
    bad = CliRunner().invoke(cli.app, ["logs", "secrets"])
    assert bad.exit_code == 1 and "the services are" in bad.output

