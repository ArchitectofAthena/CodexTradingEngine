"""Transfer valuation, RPC, checkpoint, and price resolver behavior."""

from __future__ import annotations

from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from omega_telemetry.models import PricePoint
from omega_telemetry.pricing import PriceResolver
from omega_telemetry.whale_watcher import JsonRpcClient, hex_to_int, short_addr, token_decimals
from tests.omega_helpers import (
    ADDRESS_A,
    ADDRESS_B,
    CONTRACT,
    Response,
    StaticPrice,
    block,
    session_for,
    transfer_log,
    watcher,
)


async def test_price_cache_normalizes_symbol_and_preserves_decimal_precision() -> None:
    precise = "12345.678901234567890123456789"
    session = session_for(Response({"ethereum": {"usd": precise}}))
    resolver = PriceResolver(session, {"eth": "ethereum"})
    point = await resolver.get_usd_price("eth")
    assert point is not None and point.usd == Decimal(precise) and point.symbol == "ETH"
    assert await resolver.get_usd_price("ETH") is point
    assert await resolver.get_usd_price("UNMAPPED") is None
    session.get.assert_called_once()
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "payload", [[], {}, {"ethereum": None}, {"ethereum": {}}, {"ethereum": {"usd": None}}]
)
async def test_price_missing_or_malformed_response_is_unavailable(payload: Any) -> None:
    resolver = PriceResolver(session_for(Response(payload)), {"ETH": "ethereum"})
    assert await resolver.get_usd_price("ETH") is None


@pytest.mark.parametrize("status", [302, 500])
async def test_price_http_failure_never_yields_price(status: int) -> None:
    resolver = PriceResolver(session_for(Response(status=status)), {"ETH": "ethereum"})
    assert await resolver.get_usd_price("ETH") is None


async def test_expired_price_has_no_stale_fallback_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = session_for(Response({"ethereum": {"usd": "1"}}))
    resolver = PriceResolver(session, {"ETH": "ethereum"})
    clock = [1000.0]
    monkeypatch.setattr("omega_telemetry.pricing.time.monotonic", lambda: clock[0])
    assert await resolver.get_usd_price("ETH") is not None
    clock[0] += 61
    session.get.side_effect = TimeoutError()
    assert await resolver.get_usd_price("ETH") is None
    assert resolver._cache == {}


async def test_price_json_number_uses_decimal_parser() -> None:
    class NumericResponse(Response):
        async def json(self, **kwargs: Any) -> Any:
            return kwargs["loads"]('{"ethereum":{"usd":0.12345678901234567890123456789}}')

    resolver = PriceResolver(session_for(NumericResponse()), {"ETH": "ethereum"})
    point = await resolver.get_usd_price("ETH")
    assert point is not None and point.usd == Decimal("0.12345678901234567890123456789")


@pytest.mark.parametrize(
    "units, expected, severity",
    [
        (0, 0, None),
        (999 * 10**18, 0, None),
        (1000 * 10**18, 1, "high"),
        (10000 * 10**18, 1, "critical"),
    ],
)
async def test_native_threshold_inclusive_and_critical_boundary(
    tmp_path: Path, units: int, expected: int, severity: str | None
) -> None:
    instance = watcher(tmp_path)
    await instance._scan_native_transfers(block(units))
    rows = instance.db.recent_events()
    assert len(rows) == expected
    if rows:
        assert rows[0]["severity"] == severity
        assert rows[0]["data"]["authority"] is False
        assert rows[0]["data"]["artifact_is_command"] is False


async def test_native_wei_precision_does_not_change_global_decimal_context(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    original = getcontext().prec
    await instance._scan_native_transfers(block(10**30 + 1))
    data = instance.db.recent_events()[0]["data"]
    assert Decimal(data["amount"]) == Decimal("1000000000000.000000000000000001")
    assert Decimal(data["usd_value_exact"]) == Decimal("1000000000000.000000000000000001")
    assert getcontext().prec == original


async def test_erc20_units_and_per_log_identity_are_preserved(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.rpc.call = AsyncMock(
        return_value=[
            transfer_log(data=hex(1000 * 10**6 + 1)),
            transfer_log(logIndex="0x1", data=hex(1000 * 10**6 + 2)),
        ]
    )
    await instance._scan_erc20_logs(42)
    await instance._scan_erc20_logs(42)
    rows = instance.db.recent_events()
    assert len(rows) == 2
    assert {Decimal(row["amount"]) for row in rows} == {
        Decimal("1000.000001"),
        Decimal("1000.000002"),
    }
    assert all(row["data"]["contract"] == CONTRACT for row in rows)
    assert {row["data"]["log_index"] for row in rows} == {0, 1}


async def test_erc20_empty_dust_and_malformed_records_do_not_hide_good_log(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.rpc.call = AsyncMock(
        return_value=[None, {}, transfer_log(data="0x0"), transfer_log(data="0x1"), transfer_log()]
    )
    await instance._scan_erc20_logs(42)
    assert len(instance.db.recent_events()) == 1
    instance.rpc.call.return_value = []
    await instance._scan_erc20_logs(42)
    assert len(instance.db.recent_events()) == 1


async def test_no_price_skips_both_transfer_scanners(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.price_resolver.get_usd_price = AsyncMock(return_value=None)
    instance.rpc.call = AsyncMock()
    await instance._scan_native_transfers(block())
    await instance._scan_erc20_logs(42)
    assert instance.db.recent_events() == []
    instance.rpc.call.assert_not_awaited()


@pytest.mark.parametrize(
    "usd, stamp", [("NaN", None), ("-1", None), ("1", "garbage"), ("1", "2999-01-01T00:00:00Z")]
)
async def test_adversarial_unusable_injected_price_points_fail_closed(
    tmp_path: Path, usd: str, stamp: str | None
) -> None:
    instance = watcher(tmp_path)
    instance.price_resolver = StaticPrice(usd, stamp)  # type: ignore[assignment]
    await instance._scan_native_transfers(block())
    assert instance.db.recent_events() == []


async def test_adversarial_wrong_price_symbol_fails_closed(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.price_resolver.get_usd_price = AsyncMock(
        return_value=PricePoint("BTC", Decimal("100000"), "fixture")
    )
    await instance._scan_native_transfers(block())
    assert instance.db.recent_events() == []


async def test_native_invalid_container_and_missing_identity(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    await instance._scan_native_transfers({"transactions": {}})
    await instance._scan_native_transfers({"transactions": [None]})
    await instance._scan_native_transfers(block(hash=None))
    assert instance.db.recent_events() == []


async def test_poll_bounds_catchup_and_commits_checkpoint_after_success(tmp_path: Path) -> None:
    instance = watcher(tmp_path, max_blocks_per_poll=2)
    instance.db.set_state("whale_watcher:last_block:base", "30")

    async def rpc(method: str, params: list[Any]) -> Any:
        if method == "eth_blockNumber":
            return "0x2b"
        if method == "eth_getBlockByNumber":
            return {"number": params[0], "transactions": []}
        assert method == "eth_getLogs"
        return []

    instance.rpc.call = AsyncMock(side_effect=rpc)
    await instance.poll_once()
    calls = instance.rpc.call.await_args_list
    assert [call.args[1][0] for call in calls if call.args[0] == "eth_getBlockByNumber"] == [
        "0x2a",
        "0x2b",
    ]
    assert instance.db.get_state("whale_watcher:last_block:base") == "43"
    instance.rpc.call.reset_mock()
    await instance.poll_once()
    instance.rpc.call.assert_awaited_once_with("eth_blockNumber", [])


@pytest.mark.parametrize(
    "returned",
    [None, {"number": "0x29", "transactions": []}, {"number": "0x2a", "transactions": {}}],
)
async def test_adversarial_invalid_block_retains_previous_checkpoint(
    tmp_path: Path, returned: Any
) -> None:
    instance = watcher(tmp_path)
    instance.db.set_state("whale_watcher:last_block:base", "41")
    instance.rpc.call = AsyncMock(side_effect=["0x2a", returned])
    with pytest.raises(ValueError):
        await instance.poll_once()
    assert instance.db.get_state("whale_watcher:last_block:base") == "41"


async def test_malformed_log_envelope_does_not_advance_checkpoint(tmp_path: Path) -> None:
    instance = watcher(tmp_path)
    instance.rpc.call = AsyncMock(side_effect=["0x2a", {"number": "0x2a", "transactions": []}, {}])
    with pytest.raises(ValueError, match="logs"):
        await instance.poll_once()
    assert instance.db.get_state("whale_watcher:last_block:base") is None


@pytest.mark.parametrize(
    "labels, expected",
    [
        ({ADDRESS_A: "Exchange"}, "exchange_withdrawal"),
        ({ADDRESS_B: "Exchange"}, "exchange_deposit"),
        ({ADDRESS_A: "A", ADDRESS_B: "B"}, "large_transfer"),
    ],
)
async def test_exchange_labels_classify_transfer_context_only(
    tmp_path: Path, labels: dict[str, str], expected: str
) -> None:
    instance = watcher(tmp_path, exchange_labels=labels)
    await instance._scan_native_transfers(block())
    row = instance.db.recent_events()[0]
    assert row["event_type"] == expected and row["data"]["directional_signal"] == "unknown"


@pytest.mark.parametrize(
    "overrides",
    [
        {"native_asset": []},
        {"exchange_labels": ["bad"]},
        {"erc20_tokens": [None]},
        {"erc20_tokens": "bad"},
        {"max_blocks_per_poll": 0},
        {"token_usd_threshold": "NaN"},
        {"native_asset": {"symbol": "ETH", "usd_threshold": "-1"}},
    ],
)
def test_watcher_config_rejects_invalid_shapes_and_thresholds(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        watcher(tmp_path, **overrides)


@pytest.mark.parametrize("decimals", [True, -1, 256, 1.5])
def test_invalid_asset_decimals_are_rejected(decimals: Any) -> None:
    with pytest.raises(ValueError):
        token_decimals(decimals)


def test_address_and_quantity_compatibility_helpers() -> None:
    assert hex_to_int(None) == 0 and hex_to_int("0x2a") == 42
    assert short_addr("") == "unknown"


async def test_rpc_success_binds_version_id_method_and_disables_redirects() -> None:
    session = session_for(
        Response({"jsonrpc": "2.0", "id": 1, "result": "0x2a"}),
        Response({"jsonrpc": "2.0", "id": 2, "result": []}),
    )
    rpc = JsonRpcClient(session, "https://rpc.example.invalid")
    assert await rpc.call("eth_blockNumber", []) == "0x2a"
    assert await rpc.call("eth_getLogs", [{}]) == []
    assert session.post.call_args.kwargs["json"]["id"] == 2
    assert session.post.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "payload",
    [[], {"jsonrpc": "2.0", "id": 1, "error": {"message": "fixture"}}, {"jsonrpc": "2.0", "id": 1}],
)
async def test_rpc_malformed_error_and_missing_result_are_explicit(payload: Any) -> None:
    with pytest.raises(RuntimeError):
        await JsonRpcClient(session_for(Response(payload)), "https://rpc.example.invalid").call(
            "eth_blockNumber", []
        )


async def test_adversarial_rpc_redirect_rejected() -> None:
    with pytest.raises(RuntimeError, match="redirect"):
        await JsonRpcClient(session_for(Response(status=302)), "https://rpc.example.invalid").call(
            "eth_blockNumber", []
        )


@pytest.mark.parametrize(
    "method",
    ["eth_sendTransaction", "eth_sendRawTransaction", "eth_sign", "personal_unlockAccount"],
)
async def test_adversarial_capital_rpc_methods_never_reach_transport(method: str) -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="read-only allowlist"):
        await JsonRpcClient(session, "https://rpc.example.invalid").call(method, [])
    session.post.assert_not_called()
