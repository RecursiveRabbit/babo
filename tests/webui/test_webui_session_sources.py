"""Operator sessions behind a trusted network source: issue, refuse, revoke, restart.

The WireGuard source rule is the outer authentication (Router side). This module
covers the inner half: an operator arriving from an explicitly trusted peer
address may obtain the same UI session a loopback operator gets, that peer
matching is exact (no headers, no prefixes), and revocation is real — by
operator action and by process restart.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Request

from babo.channels.websocket.runtime import WebSocketConfig
from babo.webui.gateway_tokens import GatewayTokenStore
from babo.webui.http_utils import is_trusted_source_request
from babo.webui.ws_http import GatewayHTTPHandler


def test_trusted_sources_take_exact_addresses_only() -> None:
    assert WebSocketConfig(trusted_sources=["10.0.0.2/32"]).trusted_sources == ["10.0.0.2/32"]
    for bad in ("10.0.0.0/8", "0.0.0.0/0", "10.0.0.2", "example.com", "::/0", "::1/128"):
        with pytest.raises(ValueError):
            WebSocketConfig(trusted_sources=[bad])


def test_only_the_exact_peer_is_trusted_and_headers_never_count() -> None:
    trusted = ["10.0.0.2/32"]
    assert is_trusted_source_request(SimpleNamespace(remote_address=("10.0.0.2", 5000)), trusted)
    assert is_trusted_source_request(SimpleNamespace(remote_address=("::ffff:10.0.0.2", 5000)), trusted)
    assert not is_trusted_source_request(SimpleNamespace(remote_address=("10.0.0.20", 5000)), trusted)
    assert not is_trusted_source_request(SimpleNamespace(remote_address=("10.0.0.99", 5000)), trusted)
    assert not is_trusted_source_request(SimpleNamespace(remote_address=None), trusted)


def _bootstrap(handler: GatewayHTTPHandler, peer: str, headers: dict[str, str] | None = None) -> int:
    connection = SimpleNamespace(remote_address=(peer, 5000))
    request = Request("/webui/bootstrap", Headers({"Host": "10.0.0.2:18790", **(headers or {})}))
    return handler._handle_bootstrap(connection, request).status_code


def _handler(trusted: list[str]) -> GatewayHTTPHandler:
    handler = object.__new__(GatewayHTTPHandler)
    handler.config = WebSocketConfig(trusted_sources=trusted)
    handler.tokens = GatewayTokenStore()
    handler._log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                                   error=lambda *a, **k: None, exception=lambda *a, **k: None)
    handler.ingress = SimpleNamespace(bootstrap_limits=lambda **kwargs: {})
    handler.runtime_model_name = ""
    handler.settings = SimpleNamespace(config=SimpleNamespace(path=""))
    handler._runtime_surface = "webui"
    handler._capabilities = {}
    return handler


def test_a_trusted_peer_gets_a_session_and_an_untrusted_one_gets_nothing() -> None:
    handler = _handler(["10.0.0.2/32"])
    assert _bootstrap(handler, "10.0.0.2") == 200
    issued = len(handler.tokens.issued_tokens), len(handler.tokens.api_tokens)
    assert issued == (1, 1), "a trusted operator gets both the socket and API tokens"
    before = sum(issued)
    assert _bootstrap(handler, "10.0.0.99") == 403
    assert _bootstrap(handler, "10.0.0.99", {"X-Forwarded-For": "10.0.0.2"}) == 403
    assert sum((len(handler.tokens.issued_tokens), len(handler.tokens.api_tokens))) == before


def test_revoking_sessions_kills_the_token_that_asked_for_it() -> None:
    handler = _handler(["10.0.0.2/32"])
    assert _bootstrap(handler, "10.0.0.2") == 200
    api_token = next(iter(handler.tokens.api_tokens))
    request = Request("/api/office", Headers({"Authorization": f"Bearer {api_token}"}))
    assert handler.tokens.check_api_token(request)
    response = handler._handle_tokens_revoke(SimpleNamespace())
    assert json.loads(response.body)["revoked"] == 2
    assert not handler.tokens.api_tokens and not handler.tokens.issued_tokens
    assert not handler.tokens.check_api_token(request), "the revoked token must not work again"


def test_a_restart_invalidates_every_session() -> None:
    before = GatewayTokenStore()
    token = before.issue_api_token(3600)
    after = GatewayTokenStore()  # a new gateway process: new instance, empty store
    assert after.instance_id != before.instance_id
    request = Request("/api/office", Headers({"Authorization": f"Bearer {token}"}))
    assert not after.check_api_token(request)
