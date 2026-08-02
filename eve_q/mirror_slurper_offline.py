"""Deterministic offline adversarial evaluator for recorded AMM pool snapshots.

MirrorSlurper v0.1 is an immune-system surface, not a trader. It accepts only
recorded JSON documents, simulates constant-product routes under adverse
conditions, emits a canonical review receipt, and carries no network, wallet,
proposal, execution, or capital authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

ARTIFACT_TYPE = "MirrorSlurperOfflineReceipt"
CONTRACT_VERSION = "mirror_slurper_offline_v0.1"
SNAPSHOT_VERSION = "mirror_slurper_pool_snapshot_v0.1"
CANDIDATE_VERSION = "mirror_slurper_candidate_v0.1"
POLICY_VERSION = "mirror_slurper_stress_policy_v0.1"
AMM_MODEL = "constant_product_x_y_k_v0.1"
GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1": "PILOT_ONLY",
    "gate_2_through_6": "LOCKED",
}
FALSE_BOUNDARIES = {
    "artifact_is_command": False,
    "authority": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_move_capital": False,
}


class MirrorSlurperError(ValueError):
    """Raised when an offline input violates the reviewed contract."""


def canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    """Return canonical UTF-8 JSON for stable identifiers."""

    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_without_id(document: Mapping[str, Any], id_field: str) -> dict[str, Any]:
    payload = deepcopy(dict(document))
    payload.pop(id_field, None)
    return payload


def compute_document_id(document: Mapping[str, Any], id_field: str) -> str:
    """Compute a content identifier with the identifier field omitted."""

    return sha256_hex(canonical_json_bytes(_payload_without_id(document, id_field)))


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MirrorSlurperError(f"{field} must be an object")
    return value


def _require_sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise MirrorSlurperError(f"{field} must be an array")
    return value


def _require_exact_keys(
    document: Mapping[str, Any],
    *,
    field: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    keys = set(document)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise MirrorSlurperError(f"{field} missing required fields: {', '.join(missing)}")
    if unknown:
        raise MirrorSlurperError(f"{field} contains unknown fields: {', '.join(unknown)}")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MirrorSlurperError(f"{field} must be a non-empty string")
    return value.strip()


def _require_bool(value: Any, expected: bool, field: str) -> None:
    if value is not expected:
        raise MirrorSlurperError(f"{field} must be {str(expected).lower()}")


def _require_int(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MirrorSlurperError(f"{field} must be an integer")
    if value < minimum:
        raise MirrorSlurperError(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise MirrorSlurperError(f"{field} must be no more than {maximum}")
    return value


def _require_decimal(
    value: Any,
    field: str,
    *,
    minimum: Decimal = Decimal("0"),
    strictly_positive: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise MirrorSlurperError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise MirrorSlurperError(f"{field} must be a valid decimal string") from exc
    if not parsed.is_finite():
        raise MirrorSlurperError(f"{field} must be finite")
    if strictly_positive and parsed <= 0:
        raise MirrorSlurperError(f"{field} must be greater than zero")
    if not strictly_positive and parsed < minimum:
        raise MirrorSlurperError(f"{field} must be at least {minimum}")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _require_hex_id(value: Any, field: str, length: int = 64) -> str:
    text = _require_string(value, field).lower()
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise MirrorSlurperError(f"{field} must be a {length}-character hexadecimal string")
    return text


def _require_utc_timestamp(value: Any, field: str) -> str:
    text = _require_string(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MirrorSlurperError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MirrorSlurperError(f"{field} must include a UTC offset")
    if parsed.utcoffset().total_seconds() != 0:
        raise MirrorSlurperError(f"{field} must be UTC")
    return text


def _validate_boundaries(document: Mapping[str, Any], field: str) -> None:
    for key, expected in FALSE_BOUNDARIES.items():
        _require_bool(document.get(key), expected, f"{field}.{key}")


def validate_pool_snapshot(snapshot: Mapping[str, Any]) -> None:
    _require_exact_keys(
        snapshot,
        field="snapshot",
        required={
            "snapshot_version",
            "snapshot_id",
            "captured_at",
            "source",
            "amm_model",
            "pools",
            "artifact_is_command",
            "authority",
            "may_generate_live_proposal",
            "may_execute",
            "may_move_capital",
        },
    )
    if snapshot["snapshot_version"] != SNAPSHOT_VERSION:
        raise MirrorSlurperError(f"snapshot.snapshot_version must be {SNAPSHOT_VERSION}")
    if snapshot["amm_model"] != AMM_MODEL:
        raise MirrorSlurperError(f"snapshot.amm_model must be {AMM_MODEL}")
    _require_utc_timestamp(snapshot["captured_at"], "snapshot.captured_at")
    _validate_boundaries(snapshot, "snapshot")

    source = _require_mapping(snapshot["source"], "snapshot.source")
    _require_exact_keys(
        source,
        field="snapshot.source",
        required={"kind", "label", "recorded_offline", "network_fetch_performed"},
    )
    _require_string(source["kind"], "snapshot.source.kind")
    _require_string(source["label"], "snapshot.source.label")
    _require_bool(source["recorded_offline"], True, "snapshot.source.recorded_offline")
    _require_bool(
        source["network_fetch_performed"],
        False,
        "snapshot.source.network_fetch_performed",
    )

    pools = _require_sequence(snapshot["pools"], "snapshot.pools")
    if not pools:
        raise MirrorSlurperError("snapshot.pools must contain at least one pool")
    seen_ids: set[str] = set()
    for index, raw_pool in enumerate(pools):
        pool = _require_mapping(raw_pool, f"snapshot.pools[{index}]")
        _require_exact_keys(
            pool,
            field=f"snapshot.pools[{index}]",
            required={
                "pool_id",
                "chain",
                "dex",
                "token0",
                "token1",
                "reserve0",
                "reserve1",
                "fee_bps",
            },
        )
        pool_id = _require_string(pool["pool_id"], f"snapshot.pools[{index}].pool_id")
        if pool_id in seen_ids:
            raise MirrorSlurperError(f"duplicate pool_id: {pool_id}")
        seen_ids.add(pool_id)
        _require_string(pool["chain"], f"snapshot.pools[{index}].chain")
        _require_string(pool["dex"], f"snapshot.pools[{index}].dex")
        token0 = _require_string(pool["token0"], f"snapshot.pools[{index}].token0")
        token1 = _require_string(pool["token1"], f"snapshot.pools[{index}].token1")
        if token0 == token1:
            raise MirrorSlurperError(f"pool {pool_id} must contain two distinct tokens")
        _require_decimal(
            pool["reserve0"],
            f"snapshot.pools[{index}].reserve0",
            strictly_positive=True,
        )
        _require_decimal(
            pool["reserve1"],
            f"snapshot.pools[{index}].reserve1",
            strictly_positive=True,
        )
        _require_int(
            pool["fee_bps"],
            f"snapshot.pools[{index}].fee_bps",
            minimum=0,
            maximum=1000,
        )

    supplied_id = _require_hex_id(snapshot["snapshot_id"], "snapshot.snapshot_id")
    expected_id = compute_document_id(snapshot, "snapshot_id")
    if supplied_id != expected_id:
        raise MirrorSlurperError("snapshot.snapshot_id does not match canonical content")


def validate_candidate(candidate: Mapping[str, Any]) -> None:
    _require_exact_keys(
        candidate,
        field="candidate",
        required={
            "candidate_version",
            "candidate_id",
            "chain",
            "start_token",
            "amount_in",
            "gas_cost_start_token",
            "flash_fee_bps",
            "failure_reserve_start_token",
            "route",
            "artifact_is_command",
            "authority",
            "may_generate_live_proposal",
            "may_execute",
            "may_move_capital",
        },
    )
    if candidate["candidate_version"] != CANDIDATE_VERSION:
        raise MirrorSlurperError(f"candidate.candidate_version must be {CANDIDATE_VERSION}")
    _validate_boundaries(candidate, "candidate")
    _require_string(candidate["chain"], "candidate.chain")
    start_token = _require_string(candidate["start_token"], "candidate.start_token")
    _require_decimal(candidate["amount_in"], "candidate.amount_in", strictly_positive=True)
    _require_decimal(candidate["gas_cost_start_token"], "candidate.gas_cost_start_token")
    _require_int(candidate["flash_fee_bps"], "candidate.flash_fee_bps", minimum=0, maximum=1000)
    _require_decimal(
        candidate["failure_reserve_start_token"],
        "candidate.failure_reserve_start_token",
    )

    route = _require_sequence(candidate["route"], "candidate.route")
    if len(route) < 2:
        raise MirrorSlurperError("candidate.route must contain at least two legs")
    seen_pool_ids: set[str] = set()
    expected_token = start_token
    for index, raw_leg in enumerate(route):
        leg = _require_mapping(raw_leg, f"candidate.route[{index}]")
        _require_exact_keys(
            leg,
            field=f"candidate.route[{index}]",
            required={"pool_id", "token_in", "token_out"},
        )
        pool_id = _require_string(leg["pool_id"], f"candidate.route[{index}].pool_id")
        if pool_id in seen_pool_ids:
            raise MirrorSlurperError("candidate.route may not reuse a pool in v0.1")
        seen_pool_ids.add(pool_id)
        token_in = _require_string(leg["token_in"], f"candidate.route[{index}].token_in")
        token_out = _require_string(leg["token_out"], f"candidate.route[{index}].token_out")
        if token_in != expected_token:
            raise MirrorSlurperError(
                f"candidate.route[{index}].token_in must continue from {expected_token}"
            )
        if token_out == token_in:
            raise MirrorSlurperError(f"candidate.route[{index}] must change tokens")
        expected_token = token_out
    if expected_token != start_token:
        raise MirrorSlurperError("candidate.route must return to candidate.start_token")

    supplied_id = _require_hex_id(candidate["candidate_id"], "candidate.candidate_id")
    expected_id = compute_document_id(candidate, "candidate_id")
    if supplied_id != expected_id:
        raise MirrorSlurperError("candidate.candidate_id does not match canonical content")


def validate_stress_policy(policy: Mapping[str, Any]) -> None:
    _require_exact_keys(
        policy,
        field="policy",
        required={
            "policy_version",
            "policy_id",
            "minimum_worst_case_profit_start_token",
            "delay_adverse_bps_per_block",
            "scenarios",
            "artifact_is_command",
            "authority",
            "may_generate_live_proposal",
            "may_execute",
            "may_move_capital",
        },
    )
    if policy["policy_version"] != POLICY_VERSION:
        raise MirrorSlurperError(f"policy.policy_version must be {POLICY_VERSION}")
    _validate_boundaries(policy, "policy")
    _require_decimal(
        policy["minimum_worst_case_profit_start_token"],
        "policy.minimum_worst_case_profit_start_token",
    )
    _require_int(
        policy["delay_adverse_bps_per_block"],
        "policy.delay_adverse_bps_per_block",
        minimum=0,
        maximum=1000,
    )
    scenarios = _require_sequence(policy["scenarios"], "policy.scenarios")
    if not scenarios:
        raise MirrorSlurperError("policy.scenarios must contain at least one stress scenario")
    names: set[str] = set()
    for index, raw_scenario in enumerate(scenarios):
        scenario = _require_mapping(raw_scenario, f"policy.scenarios[{index}]")
        _require_exact_keys(
            scenario,
            field=f"policy.scenarios[{index}]",
            required={
                "name",
                "gas_multiplier",
                "reserve_shift_bps",
                "slippage_bps",
                "delay_blocks",
            },
        )
        name = _require_string(scenario["name"], f"policy.scenarios[{index}].name")
        if name == "baseline":
            raise MirrorSlurperError("policy scenario name 'baseline' is reserved")
        if name in names:
            raise MirrorSlurperError(f"duplicate stress scenario name: {name}")
        names.add(name)
        _require_decimal(
            scenario["gas_multiplier"],
            f"policy.scenarios[{index}].gas_multiplier",
            strictly_positive=True,
        )
        _require_int(
            scenario["reserve_shift_bps"],
            f"policy.scenarios[{index}].reserve_shift_bps",
            minimum=0,
            maximum=5000,
        )
        _require_int(
            scenario["slippage_bps"],
            f"policy.scenarios[{index}].slippage_bps",
            minimum=0,
            maximum=5000,
        )
        _require_int(
            scenario["delay_blocks"],
            f"policy.scenarios[{index}].delay_blocks",
            minimum=0,
            maximum=100,
        )
        effective_shift = scenario["reserve_shift_bps"] + (
            scenario["delay_blocks"] * policy["delay_adverse_bps_per_block"]
        )
        if effective_shift >= 10_000:
            raise MirrorSlurperError(
                f"policy.scenarios[{index}] effective reserve shift must be below 10000 bps"
            )

    supplied_id = _require_hex_id(policy["policy_id"], "policy.policy_id")
    expected_id = compute_document_id(policy, "policy_id")
    if supplied_id != expected_id:
        raise MirrorSlurperError("policy.policy_id does not match canonical content")


def _pool_index(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(pool["pool_id"]): dict(pool)
        for pool in _require_sequence(snapshot["pools"], "snapshot.pools")
    }


def _oriented_reserves(
    pool: Mapping[str, Any],
    token_in: str,
    token_out: str,
) -> tuple[Decimal, Decimal, bool]:
    token0 = str(pool["token0"])
    token1 = str(pool["token1"])
    reserve0 = _require_decimal(pool["reserve0"], "pool.reserve0", strictly_positive=True)
    reserve1 = _require_decimal(pool["reserve1"], "pool.reserve1", strictly_positive=True)
    if token_in == token0 and token_out == token1:
        return reserve0, reserve1, True
    if token_in == token1 and token_out == token0:
        return reserve1, reserve0, False
    raise MirrorSlurperError(
        f"pool {pool['pool_id']} does not support route {token_in}->{token_out}"
    )


def _simulate_swap(
    amount_in: Decimal,
    pool: MutableMapping[str, Any],
    token_in: str,
    token_out: str,
    *,
    effective_reserve_shift_bps: int,
    slippage_bps: int,
) -> tuple[Decimal, dict[str, str]]:
    reserve_in, reserve_out, forward = _oriented_reserves(pool, token_in, token_out)
    shift = Decimal(effective_reserve_shift_bps) / Decimal(10_000)
    stressed_reserve_in = reserve_in * (Decimal(1) + shift)
    stressed_reserve_out = reserve_out * (Decimal(1) - shift)
    if stressed_reserve_out <= 0:
        raise MirrorSlurperError(f"pool {pool['pool_id']} stressed reserve is not positive")

    fee_bps = _require_int(pool["fee_bps"], "pool.fee_bps", minimum=0, maximum=1000)
    fee_multiplier = Decimal(10_000 - fee_bps) / Decimal(10_000)
    amount_after_fee = amount_in * fee_multiplier
    raw_amount_out = (amount_after_fee * stressed_reserve_out) / (
        stressed_reserve_in + amount_after_fee
    )
    slippage_multiplier = Decimal(10_000 - slippage_bps) / Decimal(10_000)
    received_amount_out = raw_amount_out * slippage_multiplier
    if received_amount_out <= 0 or raw_amount_out >= stressed_reserve_out:
        raise MirrorSlurperError(f"pool {pool['pool_id']} produced an invalid swap output")

    updated_reserve_in = stressed_reserve_in + amount_in
    updated_reserve_out = stressed_reserve_out - raw_amount_out
    if forward:
        pool["reserve0"] = _decimal_text(updated_reserve_in)
        pool["reserve1"] = _decimal_text(updated_reserve_out)
    else:
        pool["reserve1"] = _decimal_text(updated_reserve_in)
        pool["reserve0"] = _decimal_text(updated_reserve_out)

    return received_amount_out, {
        "amount_in": _decimal_text(amount_in),
        "raw_amount_out": _decimal_text(raw_amount_out),
        "received_amount_out": _decimal_text(received_amount_out),
        "stressed_reserve_in": _decimal_text(stressed_reserve_in),
        "stressed_reserve_out": _decimal_text(stressed_reserve_out),
    }


def _scenario_result(
    snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    pools = _pool_index(snapshot)
    candidate_chain = str(candidate["chain"])
    amount = _require_decimal(candidate["amount_in"], "candidate.amount_in", strictly_positive=True)
    principal = amount
    delay_bps = _require_int(
        policy["delay_adverse_bps_per_block"],
        "policy.delay_adverse_bps_per_block",
    ) * _require_int(scenario["delay_blocks"], "scenario.delay_blocks")
    effective_shift = _require_int(
        scenario["reserve_shift_bps"], "scenario.reserve_shift_bps"
    ) + delay_bps
    slippage_bps = _require_int(scenario["slippage_bps"], "scenario.slippage_bps")

    leg_results: list[dict[str, Any]] = []
    for index, raw_leg in enumerate(_require_sequence(candidate["route"], "candidate.route")):
        leg = _require_mapping(raw_leg, f"candidate.route[{index}]")
        pool_id = str(leg["pool_id"])
        pool = pools.get(pool_id)
        if pool is None:
            raise MirrorSlurperError(f"candidate route references unknown pool: {pool_id}")
        if str(pool["chain"]) != candidate_chain:
            raise MirrorSlurperError(
                f"pool {pool_id} chain {pool['chain']} does not match candidate chain {candidate_chain}"
            )
        amount, mechanics = _simulate_swap(
            amount,
            pool,
            str(leg["token_in"]),
            str(leg["token_out"]),
            effective_reserve_shift_bps=effective_shift,
            slippage_bps=slippage_bps,
        )
        leg_results.append(
            {
                "index": index,
                "pool_id": pool_id,
                "token_in": leg["token_in"],
                "token_out": leg["token_out"],
                **mechanics,
            }
        )

    flash_fee = principal * Decimal(int(candidate["flash_fee_bps"])) / Decimal(10_000)
    gas_multiplier = _require_decimal(
        scenario["gas_multiplier"],
        "scenario.gas_multiplier",
        strictly_positive=True,
    )
    gas_cost = _require_decimal(
        candidate["gas_cost_start_token"],
        "candidate.gas_cost_start_token",
    ) * gas_multiplier
    failure_reserve = _require_decimal(
        candidate["failure_reserve_start_token"],
        "candidate.failure_reserve_start_token",
    )
    gross_profit = amount - principal
    net_profit = gross_profit - flash_fee - gas_cost - failure_reserve

    return {
        "name": scenario["name"],
        "gas_multiplier": _decimal_text(gas_multiplier),
        "reserve_shift_bps": int(scenario["reserve_shift_bps"]),
        "delay_blocks": int(scenario["delay_blocks"]),
        "delay_adverse_bps": delay_bps,
        "effective_reserve_shift_bps": effective_shift,
        "slippage_bps": slippage_bps,
        "final_amount_start_token": _decimal_text(amount),
        "gross_profit_start_token": _decimal_text(gross_profit),
        "flash_fee_start_token": _decimal_text(flash_fee),
        "gas_cost_start_token": _decimal_text(gas_cost),
        "failure_reserve_start_token": _decimal_text(failure_reserve),
        "net_profit_start_token": _decimal_text(net_profit),
        "legs": leg_results,
    }


def _receipt_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    return _payload_without_id(document, "receipt_id")


def compute_receipt_id(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(_receipt_payload(document)))


def evaluate_recorded_route(
    snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one cyclic route against recorded pools and deterministic stress."""

    validate_pool_snapshot(snapshot)
    validate_candidate(candidate)
    validate_stress_policy(policy)

    with localcontext() as context:
        context.prec = 60
        baseline = {
            "name": "baseline",
            "gas_multiplier": "1",
            "reserve_shift_bps": 0,
            "slippage_bps": 0,
            "delay_blocks": 0,
        }
        results = [_scenario_result(snapshot, candidate, policy, baseline)]
        for raw_scenario in _require_sequence(policy["scenarios"], "policy.scenarios"):
            results.append(
                _scenario_result(
                    snapshot,
                    candidate,
                    policy,
                    _require_mapping(raw_scenario, "policy scenario"),
                )
            )

        net_values = [Decimal(str(result["net_profit_start_token"])) for result in results]
        baseline_net = net_values[0]
        worst_case_net = min(net_values)
        minimum = _require_decimal(
            policy["minimum_worst_case_profit_start_token"],
            "policy.minimum_worst_case_profit_start_token",
        )

        failure_modes: list[str] = []
        for result, net in zip(results, net_values, strict=True):
            if net < 0:
                failure_modes.append(f"scenario:{result['name']}:negative_net_profit")
        if baseline_net <= 0:
            verdict = "REJECT"
            failure_modes.insert(0, "baseline_not_profitable")
        elif worst_case_net < minimum:
            verdict = "HOLD"
            failure_modes.insert(0, "stress_floor_not_met")
        else:
            verdict = "CANDIDATE"

        receipt: dict[str, Any] = {
            "artifact_type": ARTIFACT_TYPE,
            "contract_version": CONTRACT_VERSION,
            "receipt_id": "",
            "snapshot": {
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_version": snapshot["snapshot_version"],
                "captured_at": snapshot["captured_at"],
                "amm_model": snapshot["amm_model"],
            },
            "candidate": {
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["candidate_version"],
                "chain": candidate["chain"],
                "start_token": candidate["start_token"],
                "amount_in": candidate["amount_in"],
                "route": deepcopy(candidate["route"]),
            },
            "policy": {
                "policy_id": policy["policy_id"],
                "policy_version": policy["policy_version"],
                "minimum_worst_case_profit_start_token": policy[
                    "minimum_worst_case_profit_start_token"
                ],
                "delay_adverse_bps_per_block": policy["delay_adverse_bps_per_block"],
            },
            "evaluation": {
                "verdict": verdict,
                "baseline_net_profit_start_token": _decimal_text(baseline_net),
                "worst_case_net_profit_start_token": _decimal_text(worst_case_net),
                "scenario_count": len(results),
                "failure_modes": sorted(set(failure_modes)),
                "scenario_results": results,
            },
            "gate_posture": dict(GATE_POSTURE),
            "offline_only": True,
            "recorded_snapshot_only": True,
            "human_review_required": True,
            "artifact_is_command": False,
            "authority": False,
            "may_generate_live_proposal": False,
            "may_execute": False,
            "may_move_capital": False,
        }
        receipt["receipt_id"] = compute_receipt_id(receipt)
        return receipt


def _load_json(path: Path) -> Mapping[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return _require_mapping(document, str(path))


def write_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adversarially evaluate a route using recorded pool snapshots only."
    )
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        receipt = evaluate_recorded_route(
            _load_json(args.snapshot),
            _load_json(args.candidate),
            _load_json(args.policy),
        )
    except (OSError, json.JSONDecodeError, MirrorSlurperError) as exc:
        print(f"MirrorSlurper offline evaluation: HOLD ({exc})")
        return 1

    if args.output:
        print(write_receipt(args.output, receipt))
    else:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
