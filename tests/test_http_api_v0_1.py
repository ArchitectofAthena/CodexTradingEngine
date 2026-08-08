from http import HTTPStatus

import pytest

from eve_q import http_api_v0_1 as api


def test_validate_bind_host_accepts_loopback_only():
    assert api.validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert api.validate_bind_host("::1") == "::1"
    with pytest.raises(ValueError):
        api.validate_bind_host("0.0.0.0")
    with pytest.raises(ValueError):
        api.validate_bind_host("10.0.0.5")


def test_health_is_execution_locked():
    status, payload = api.dispatch("GET", "/v1/health", {}, None)
    assert status == HTTPStatus.OK
    assert payload["status"] == "READY"
    assert payload["execution"] == "LOCKED"
    assert payload["localhost_only"] is True
    assert payload["authority"] is False
    assert payload["may_execute"] is False
    assert payload["may_sign"] is False
    assert payload["may_broadcast"] is False
    assert payload["may_move_capital"] is False


def test_channels_include_http_without_gaining_authority():
    status, payload = api.dispatch("GET", "/v1/channels", {}, None)
    assert status == HTTPStatus.OK
    assert payload["channels"]["http_api"]["transport"] == "http_json"
    assert payload["channels"]["http_api"]["localhost_only"] is True
    assert payload["authority"] is False


def test_default_shadow_research_is_in_memory_and_has_no_tx_hashes():
    status, payload = api.dispatch("POST", "/v1/research/shadow", {}, {})
    assert status == HTTPStatus.OK
    assert payload["summary"]["execution"] == "LOCKED"
    assert payload["summary"]["mode"] == "shadow"
    assert payload["summary"]["tx_hashes"] == []
    assert payload["persistence"]["written_to_disk"] is False
    assert payload["persistence"]["proposal_written"] is False
    assert payload["authority"] is False
    assert payload["may_submit_transaction"] is False
    assert payload["may_move_capital"] is False


def test_shadow_routes_require_complete_economic_fields():
    body = {"routes": [{"route": "x", "chain": "base"}]}
    with pytest.raises(api.ApiError) as caught:
        api.dispatch("POST", "/v1/research/shadow", {}, body)
    assert caught.value.status == HTTPStatus.BAD_REQUEST


def test_shadow_routes_accept_operator_supplied_candidate():
    body = {
        "cycle_id": "api-test-cycle",
        "routes": [
            {
                "route": "mock-route",
                "chain": "base",
                "expected_profit_eth": "0.010",
                "gas_cost_eth": "0.002",
                "slippage_eth": "0.001",
                "safety_margin_eth": "0.001",
            }
        ],
    }
    status, payload = api.dispatch("POST", "/v1/research/shadow", {}, body)
    assert status == HTTPStatus.OK
    assert payload["summary"]["selected_route"] == "mock-route"
    assert payload["summary"]["chain"] == "base"
    assert payload["summary"]["tx_hashes"] == []
    assert payload["authority"] is False


def test_unknown_route_fails_closed():
    with pytest.raises(api.ApiError) as caught:
        api.dispatch("GET", "/v1/nope", {}, None)
    assert caught.value.status == HTTPStatus.NOT_FOUND


def test_openapi_has_no_execution_surface():
    status, payload = api.dispatch("GET", "/v1/openapi.json", {}, None)
    assert status == HTTPStatus.OK
    paths = set(payload["paths"])
    assert "/v1/research/shadow" in paths
    assert "/v1/gate-descent/validate" in paths
    assert not any("wallet" in path or "broadcast" in path or "execute" in path for path in paths)
