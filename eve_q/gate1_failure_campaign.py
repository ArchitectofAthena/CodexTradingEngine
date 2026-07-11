from __future__ import annotations

import argparse
import hashlib
import json
import random
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from eve_q.gate1_hardening import (
    Gate1HardeningError,
    build_resolution_receipt,
    build_rollback_receipt,
    validate_resolution_receipt,
    validate_rollback_receipt,
)
from eve_q.live_read_only_telemetry import (
    SourceSpec,
    TelemetryBoundaryError,
    TransportResult,
    build_snapshot,
    canonical_json_bytes,
    iso_z,
    sha256_hex,
    validate_snapshot,
)

CONTRACT_VERSION = "eve_q_gate1_failure_campaign_v0.1"
ARTIFACT_TYPE = "Gate1FailureCampaignSummary"
DEFAULT_CYCLES = 100
DEFAULT_SEED = 424243

CASE_NAMES: tuple[str, ...] = (
    "independent_agreement",
    "conflicting_sources",
    "weak_provenance_agreement",
    "source_outage",
    "stale_snapshot",
    "malformed_payload",
    "replay_hash_mismatch",
    "non_public_dns",
    "dns_address_drift",
)

NON_AUTHORITY = {
    "artifact_is_command": False,
    "authority": False,
    "human_promotion_required": True,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_move_capital": False,
}


@dataclass(frozen=True)
class CoalitionObservation:
    source_id: str
    provenance_group: str
    normalized_sha256: str


@dataclass(frozen=True)
class CoalitionDecision:
    evidence_state: str
    disposition: str
    reason: str


Resolver = Callable[..., Iterable[tuple[Any, ...]]]


def canonical_sha256(document: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def classify_coalition(
    observations: Sequence[CoalitionObservation],
) -> CoalitionDecision:
    """Classify source agreement without granting authority.

    Agreement is not truth. Independent corroboration can become GROUNDED
    observation evidence, but never a proposal or execution command.
    """
    if len(observations) < 2:
        return CoalitionDecision(
            evidence_state="INSUFFICIENT",
            disposition="HOLD",
            reason="fewer than two observations",
        )

    payload_hashes = {item.normalized_sha256 for item in observations}
    provenance_groups = {item.provenance_group for item in observations}

    if len(payload_hashes) > 1:
        return CoalitionDecision(
            evidence_state="CONFLICTING",
            disposition="HOLD",
            reason="independent observations disagree",
        )

    if len(provenance_groups) < 2:
        return CoalitionDecision(
            evidence_state="HERDING_RISK",
            disposition="HOLD",
            reason="agreement lacks provenance independence",
        )

    return CoalitionDecision(
        evidence_state="GROUNDED",
        disposition="OBSERVE_ONLY",
        reason="matching observations have independent provenance",
    )


def _spec(
    source_id: str,
    host: str,
    *,
    ttl_seconds: int = 300,
) -> SourceSpec:
    return SourceSpec(
        source_id=source_id,
        source_kind="market_snapshot",
        url=f"https://{host}/v1/market",
        allowed_hosts=(host,),
        freshness_ttl_seconds=ttl_seconds,
        timeout_seconds=5.0,
        max_response_bytes=4096,
    )


def _result(
    *,
    body: bytes,
    host: str,
    retrieved_at: str,
    content_type: str = "application/json; charset=utf-8",
) -> TransportResult:
    return TransportResult(
        status=200,
        headers={"Content-Type": content_type},
        body=body,
        final_url=f"https://{host}/v1/market",
        retrieved_at=retrieved_at,
    )


def _resolver_for(*addresses: str) -> Resolver:
    def resolver(
        host: str,
        port: int,
        *,
        family: int,
        type: int,
        proto: int,
    ) -> list[tuple[Any, ...]]:
        del host, family
        records: list[tuple[Any, ...]] = []
        for address in addresses:
            socket_family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr: tuple[Any, ...]
            if socket_family == socket.AF_INET6:
                sockaddr = (address, port, 0, 0)
            else:
                sockaddr = (address, port)
            records.append((socket_family, type, proto, "", sockaddr))
        return records

    return resolver


def _authority_fields() -> dict[str, bool]:
    return dict(NON_AUTHORITY)


def _base_record(index: int, case_name: str) -> dict[str, Any]:
    return {
        "cycle_index": index,
        "case": case_name,
        "passed": False,
        "evidence_state": "UNRESOLVED",
        "disposition": "HOLD",
        "reason": "not evaluated",
        "rollback_artifact_id": None,
        **_authority_fields(),
        "gate_posture": {
            "gate_0": "ACTIVE",
            "gate_1": "PILOT_ONLY",
            "gate_2_through_6": "LOCKED",
        },
    }


def _payload(value: str, source: str) -> bytes:
    return canonical_json_bytes({"price": value, "source": source})


def run_case(
    case_name: str,
    *,
    index: int,
    producer_commit: str,
    observed_at: datetime,
    rng: random.Random,
) -> dict[str, Any]:
    record = _base_record(index, case_name)
    observed_text = iso_z(observed_at)
    price = f"{100 + rng.randrange(0, 5000) / 100:.2f}"

    try:
        if case_name == "independent_agreement":
            digest = sha256_hex(_payload(price, "normalized"))
            decision = classify_coalition(
                (
                    CoalitionObservation("source-a", "provider-a", digest),
                    CoalitionObservation("source-b", "provider-b", digest),
                )
            )
            record.update(
                passed=(
                    decision.evidence_state == "GROUNDED"
                    and decision.disposition == "OBSERVE_ONLY"
                ),
                evidence_state=decision.evidence_state,
                disposition=decision.disposition,
                reason=decision.reason,
            )

        elif case_name == "conflicting_sources":
            first = sha256_hex(_payload(price, "source-a"))
            second_price = f"{float(price) + 1.0:.2f}"
            second = sha256_hex(_payload(second_price, "source-b"))
            decision = classify_coalition(
                (
                    CoalitionObservation("source-a", "provider-a", first),
                    CoalitionObservation("source-b", "provider-b", second),
                )
            )
            record.update(
                passed=(
                    decision.evidence_state == "CONFLICTING"
                    and decision.disposition == "HOLD"
                ),
                evidence_state=decision.evidence_state,
                disposition=decision.disposition,
                reason=decision.reason,
            )

        elif case_name == "weak_provenance_agreement":
            digest = sha256_hex(_payload(price, "shared-upstream"))
            decision = classify_coalition(
                (
                    CoalitionObservation("mirror-a", "shared-provider", digest),
                    CoalitionObservation("mirror-b", "shared-provider", digest),
                )
            )
            record.update(
                passed=(
                    decision.evidence_state == "HERDING_RISK"
                    and decision.disposition == "HOLD"
                ),
                evidence_state=decision.evidence_state,
                disposition=decision.disposition,
                reason=decision.reason,
            )

        elif case_name == "source_outage":
            rollback = build_rollback_receipt(
                producer_commit=producer_commit,
                trigger="source_outage",
                started_at=observed_text,
                completed_at=observed_text,
            )
            findings = validate_rollback_receipt(rollback)
            record.update(
                passed=(findings == []),
                evidence_state="SOURCE_OUTAGE",
                disposition="ROLLBACK_TO_GATE_0",
                reason="source outage produced a valid rollback receipt",
                rollback_artifact_id=rollback["artifact_id"],
            )

        elif case_name == "stale_snapshot":
            spec = _spec("stale-source", "stale.example.test", ttl_seconds=30)
            document, raw_bytes, normalized_bytes = build_snapshot(
                spec,
                _result(
                    body=_payload(price, "stale-source"),
                    host="stale.example.test",
                    retrieved_at=observed_text,
                ),
                producer_commit=producer_commit,
            )
            findings = validate_snapshot(
                document,
                raw_bytes,
                normalized_bytes,
                now=observed_at + timedelta(seconds=31),
            )
            record.update(
                passed=("telemetry snapshot is stale" in findings),
                evidence_state="STALE",
                disposition="REJECT",
                reason="stale snapshot rejected",
            )

        elif case_name == "malformed_payload":
            spec = _spec("malformed-source", "malformed.example.test")
            try:
                build_snapshot(
                    spec,
                    _result(
                        body=b"not-json",
                        host="malformed.example.test",
                        retrieved_at=observed_text,
                    ),
                    producer_commit=producer_commit,
                )
            except TelemetryBoundaryError as exc:
                passed = exc.code == "malformed_json"
                reason = exc.code
            else:
                passed = False
                reason = "malformed payload was accepted"
            record.update(
                passed=passed,
                evidence_state="MALFORMED",
                disposition="REJECT",
                reason=reason,
            )

        elif case_name == "replay_hash_mismatch":
            spec = _spec("tamper-source", "tamper.example.test")
            document, raw_bytes, normalized_bytes = build_snapshot(
                spec,
                _result(
                    body=_payload(price, "tamper-source"),
                    host="tamper.example.test",
                    retrieved_at=observed_text,
                ),
                producer_commit=producer_commit,
            )
            findings = validate_snapshot(
                document,
                raw_bytes + b"tampered",
                normalized_bytes,
                now=observed_at,
            )
            record.update(
                passed=("raw payload hash mismatch" in findings),
                evidence_state="TAMPERED",
                disposition="REJECT",
                reason="replay hash mismatch rejected",
            )

        elif case_name == "non_public_dns":
            spec = _spec("private-dns", "private-dns.example.test")
            try:
                build_resolution_receipt(
                    spec,
                    producer_commit=producer_commit,
                    created_at=observed_text,
                    resolver=_resolver_for("127.0.0.1"),
                )
            except Gate1HardeningError as exc:
                passed = exc.code == "non_public_address_rejected"
                reason = exc.code
            else:
                passed = False
                reason = "non-public DNS answer was accepted"
            record.update(
                passed=passed,
                evidence_state="DNS_POLICY_FAILURE",
                disposition="REJECT",
                reason=reason,
            )

        elif case_name == "dns_address_drift":
            spec = _spec("drift-source", "drift.example.test")
            receipt = build_resolution_receipt(
                spec,
                producer_commit=producer_commit,
                created_at=observed_text,
                resolver=_resolver_for("8.8.8.8"),
            )
            findings = validate_resolution_receipt(
                receipt,
                current_spec=spec,
                resolver=_resolver_for("1.1.1.1"),
            )
            record.update(
                passed=any(
                    "DNS resolution changed" in finding for finding in findings
                ),
                evidence_state="DNS_DRIFT",
                disposition="REJECT_AND_ROLLBACK",
                reason="postflight address-set drift rejected",
            )

        else:
            raise ValueError(f"unsupported campaign case: {case_name}")

    except Exception as exc:  # campaign records unexpected failures, then fails closed
        record.update(
            passed=False,
            evidence_state="INTERNAL_FAILURE",
            disposition="ROLLBACK_TO_GATE_0",
            reason=f"{type(exc).__name__}: {exc}",
        )

    record["record_sha256"] = canonical_sha256(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )
    return record


def build_case_schedule(cycles: int, seed: int) -> list[str]:
    if cycles < len(CASE_NAMES):
        raise ValueError(f"cycles must be at least {len(CASE_NAMES)}")
    rng = random.Random(seed)
    schedule: list[str] = []
    while len(schedule) < cycles:
        block = list(CASE_NAMES)
        rng.shuffle(block)
        schedule.extend(block)
    return schedule[:cycles]


def generate_records(
    *,
    cycles: int,
    seed: int,
    producer_commit: str,
) -> list[dict[str, Any]]:
    if len(producer_commit) != 40 or any(
        character not in "0123456789abcdef" for character in producer_commit.lower()
    ):
        raise ValueError("producer_commit must be a 40-character hexadecimal SHA")

    schedule = build_case_schedule(cycles, seed)
    rng = random.Random(seed)
    epoch = datetime(2026, 7, 11, 22, 30, tzinfo=timezone.utc)
    return [
        run_case(
            case_name,
            index=index,
            producer_commit=producer_commit.lower(),
            observed_at=epoch + timedelta(seconds=index),
            rng=rng,
        )
        for index, case_name in enumerate(schedule)
    ]


def build_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    cycles: int,
    seed: int,
    producer_commit: str,
) -> dict[str, Any]:
    case_counts = {name: 0 for name in CASE_NAMES}
    case_passes = {name: 0 for name in CASE_NAMES}
    for record in records:
        case_name = str(record["case"])
        case_counts[case_name] += 1
        if record.get("passed") is True:
            case_passes[case_name] += 1

    failures = sum(record.get("passed") is not True for record in records)
    unauthorized = sum(
        bool(record.get("authority"))
        or bool(record.get("may_generate_live_proposal"))
        or bool(record.get("may_execute"))
        or bool(record.get("may_move_capital"))
        for record in records
    )
    rollback_count = sum(
        record.get("disposition") == "ROLLBACK_TO_GATE_0"
        for record in records
    )
    ledger_sha256 = canonical_sha256(list(records))

    acceptance = {
        "all_cases_exercised": all(case_counts.values()),
        "all_cases_passed": all(
            case_passes[name] == case_counts[name] for name in CASE_NAMES
        ),
        "zero_unexpected_failures": failures == 0,
        "zero_unauthorized_transitions": unauthorized == 0,
        "outage_rollback_proven": case_passes["source_outage"] > 0,
        "conflict_holds": case_passes["conflicting_sources"] > 0,
        "herding_risk_holds": case_passes["weak_provenance_agreement"] > 0,
        "independent_agreement_observation_only": (
            case_passes["independent_agreement"] > 0
        ),
        "stale_rejected": case_passes["stale_snapshot"] > 0,
        "malformed_rejected": case_passes["malformed_payload"] > 0,
        "tamper_rejected": case_passes["replay_hash_mismatch"] > 0,
        "non_public_dns_rejected": case_passes["non_public_dns"] > 0,
        "dns_drift_rejected": case_passes["dns_address_drift"] > 0,
    }

    summary: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "campaign": {
            "cycles_requested": cycles,
            "seed": seed,
            "producer_commit": producer_commit.lower(),
            "network_calls_permitted": False,
        },
        "results": {
            "records": len(records),
            "failures": failures,
            "unauthorized_transitions": unauthorized,
            "rollback_count": rollback_count,
            "case_counts": case_counts,
            "case_passes": case_passes,
            "ledger_sha256": ledger_sha256,
        },
        "acceptance": acceptance,
        "ok": all(acceptance.values()),
        **_authority_fields(),
        "gate_posture": {
            "gate_0": "ACTIVE",
            "gate_1": "PILOT_ONLY",
            "gate_2_through_6": "LOCKED",
        },
    }
    summary["artifact_id"] = canonical_sha256(summary)
    return summary


def run_campaign(
    output_dir: Path,
    *,
    cycles: int = DEFAULT_CYCLES,
    seed: int = DEFAULT_SEED,
    producer_commit: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    records = generate_records(
        cycles=cycles,
        seed=seed,
        producer_commit=producer_commit,
    )
    summary = build_summary(
        records,
        cycles=cycles,
        seed=seed,
        producer_commit=producer_commit,
    )

    ledger_path = output_dir / "campaign.jsonl"
    ledger_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Gate 1 synthetic failure campaign."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--producer-commit", required=True)
    args = parser.parse_args()

    summary = run_campaign(
        args.output_dir,
        cycles=args.cycles,
        seed=args.seed,
        producer_commit=args.producer_commit,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["ok"]:
        return 1
    print("Gate 1 synthetic failure campaign: PASS")
    print(f"Summary: {args.output_dir / 'summary.json'}")
    print(f"Ledger: {args.output_dir / 'campaign.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
