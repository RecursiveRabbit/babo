"""The office routes: a live view, checked changes, and one honest lifecycle verb."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Request as WsRequest

from babo.baton import projects as project_board
from babo.baton.town import Town
from babo.webui import office_api
from baton.office_fakes import FakeCore


def _routes(town: Town, index_path: Path, monkeypatch: pytest.MonkeyPatch, *,
            manager: FakeCore | None = None, authorized: bool = True) -> office_api.OfficeRoutes:
    from babo.config.schema import Config

    cfg = Config.model_validate({"baton": {"town": str(town.root), "indexPath": str(index_path),
                                          "office": {"backend": "stub"}}})
    monkeypatch.setattr("babo.config.loader.load_config", lambda *_a, **_k: cfg)
    monkeypatch.setattr(office_api, "_OPS", None)
    backend = manager or FakeCore()
    monkeypatch.setattr(office_api, "_manager", lambda: backend)
    payloads: dict[int, dict[str, Any]] = {}

    def payload(request: WsRequest) -> dict[str, Any] | None:
        return payloads.get(id(request))

    routes = office_api.OfficeRoutes(authorized=lambda _r: authorized, payload=payload)
    routes.payloads = payloads  # type: ignore[attr-defined]
    routes.manager = backend  # type: ignore[attr-defined]
    return routes


async def _call(routes: office_api.OfficeRoutes, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    request = WsRequest(path, Headers())
    if body is not None:
        routes.payloads[id(request)] = body  # type: ignore[attr-defined]
    try:
        response = await routes.dispatch(request, path)
    finally:
        routes.payloads.pop(id(request), None)  # type: ignore[attr-defined]
    assert response is not None
    text = response.body.decode() if response.body else ""
    try:
        return response.status_code, json.loads(text)
    except ValueError:
        return response.status_code, text


def _project(town: Town, title: str = "Control plane") -> str:
    return project_board.new_project(town, "mayor", title).slug


async def test_the_view_joins_records_and_shows_what_is_missing(town: Town, index_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _project(town)
    routes = _routes(town, index_path, monkeypatch)
    status, body = await _call(routes, "/api/office/agents/record",
                              {"handle": "crew-1", "resident": "archivist", "project": slug})
    assert status == 200 and "crew-1" in body["message"]

    status, view = await _call(routes, "/api/office")
    assert status == 200
    assert view["manager"] == {"name": "fake", "available": True, "said": ""}
    agent = next(a for a in view["agents"] if a["handle"] == "crew-1")
    assert agent["status"] == "missing" and agent["desired"] == "running"
    assert view["missing"] == ["crew-1"]
    assert next(p for p in view["projects"] if p["slug"] == slug)["agents"] == ["crew-1"]


async def test_an_unreachable_manager_is_shown_as_unknown_not_running(town: Town, index_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _project(town)
    manager = FakeCore(unavailable="the manager core is unavailable")
    routes = _routes(town, index_path, monkeypatch, manager=manager)
    await _call(routes, "/api/office/agents/record", {"handle": "crew-1", "resident": "archivist", "project": slug})
    status, view = await _call(routes, "/api/office")
    assert status == 200
    assert view["manager"]["available"] is False
    agent = next(a for a in view["agents"] if a["handle"] == "crew-1")
    assert agent["status"] == "unknown" and agent["desired"] == "running"


async def test_crew_changes_go_through_the_same_checks(town: Town, index_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _project(town)
    routes = _routes(town, index_path, monkeypatch)
    status, body = await _call(routes, "/api/office/crew", {"project": slug, "lead": "crew-1", "crew": ["crew-2"]})
    assert status == 200 and body["crew"]["lead"] == "crew-1"
    status, _body = await _call(routes, "/api/office/crew", {"project": slug, "crew": ["Not A Handle"]})
    assert status == 400


async def test_unauthorized_reads_are_refused(town: Town, index_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = _routes(town, index_path, monkeypatch, authorized=False)
    status, _body = await _call(routes, "/api/office")
    assert status == 401


async def test_the_office_view_reports_the_ui_listener_not_the_health_port(town: Town, index_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    routes = _routes(town, index_path, monkeypatch)
    from babo.config.schema import Config

    cfg = Config.model_validate({"baton": {"town": str(town.root), "indexPath": str(index_path),
                                          "office": {"backend": "stub"}},
                                 "gateway": {"host": "10.0.0.11", "port": 18790},
                                 "channels": {"websocket": {"host": "10.0.0.11", "port": 8843}}})
    monkeypatch.setattr("babo.config.loader.load_config", lambda *_a, **_k: cfg)
    monkeypatch.setattr(office_api, "_ops", lambda: __import__("babo.office.control", fromlist=["Ops"]).Ops())
    status, view = await _call(routes, "/api/office")
    assert status == 200
    assert view["listener"] == "10.0.0.11:8843", "the UI port, never the health port"


async def test_before_the_core_lands_the_office_says_so(town: Town, index_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """No core, no pretending: desired records are listed, agents are `unknown`,
    and the banner names the reason. A stub here would be a second core."""
    from babo.office.api import CoreNotBuiltError

    slug = _project(town)
    routes = _routes(town, index_path, monkeypatch)
    await _call(routes, "/api/office/agents/record", {"handle": "crew-1", "resident": "archivist", "project": slug})

    def unbuilt(_cfg: object = None) -> object:
        raise CoreNotBuiltError("the native manager core hasn't landed yet")

    monkeypatch.setattr(office_api, "_manager", unbuilt)
    status, view = await _call(routes, "/api/office")
    assert status == 200
    assert view["manager"]["available"] is False and "hasn't landed" in view["manager"]["said"]
    agent = next(a for a in view["agents"] if a["handle"] == "crew-1")
    assert agent["status"] == "unknown" and agent["desired"] == "running"
    assert agent["said"] == view["manager"]["said"]


async def test_a_lifecycle_action_without_a_manager_says_unavailable_and_touches_nothing(
        town: Town, index_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hole, named in the product: no Manager, no ring, and nothing executed here.

    This is the HTTP-shaped half of `test_the_other_three_verbs_...`, which moved to
    tests/baton/test_office_hop.py when the UI stopped executing lifecycle. The claim
    here is only what a route can claim: the page is told `unavailable` by name, and
    the core in this process was never asked.
    """
    monkeypatch.delenv("BABO_MANAGER_URL", raising=False)
    routes = _routes(town, index_path, monkeypatch)
    status, body = await _call(routes, "/api/office/agents/wake", {"handle": "crew-1", "reason": "try"})
    assert status == 503
    assert body["state"] == "unavailable"
    assert "no Manager is configured" in body["said"]
    assert routes.manager.audit == [], "an unavailable Manager must not fall back to executing here"
