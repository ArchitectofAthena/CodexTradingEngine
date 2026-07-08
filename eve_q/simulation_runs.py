import argparse
import json
from pathlib import Path
from typing import Any

from eve_q.immutable_receipts import (
    JsonlReceiptLedger,
    canonical_json_bytes,
    forbidden_paths,
    seal_receipt,
    sha256_hex,
)

SIMULATION_RUN_SCHEMA = "eve_q.simulation_run.v0.1"
SIMULATION_RECEIPT_SCHEMA = "eve_q.simulation_run_receipt.v0.1"
SIMULATION_PROMOTION_PRECHECK_SCHEMA = "eve_q.simulation_promotion_precheck.v0.1"
SIMULATION_RUN_VERSION = "0.1.0"

SIMULATION_ENVIRONMENT = "simulation"


class SimulationRunError(RuntimeError):
    pass


class JsonlSimulationRunLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        events = []

        for line in self.path.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))

        return events

    def append_run(self, simulation_run: dict[str, Any]) -> dict[str, Any]:
        validate_simulation_run(simulation_run)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        events = self.read_events()
        sequence = len(events) + 1

        entry = {
            "sequence": sequence,
            "event_type": "simulation_run_recorded",
            "simulation_run_id": simulation_run["simulation_run_id"],
            "simulation_run": simulation_run,
            "execution_authority": "none",
            "artifact_is_command": False,
            "may_execute": False,
            "may_move_capital": False,
        }

        with self.path.open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

        return entry


def validate_counts(
    candidate_count: int,
    accepted_count: int,
    rejected_count: int,
) -> None:
    counts = [candidate_count, accepted_count, rejected_count]

    if any(isinstance(count, bool) or not isinstance(count, int) for count in counts):
        raise SimulationRunError("simulation counts must be integers")

    if any(count < 0 for count in counts):
        raise SimulationRunError("simulation counts cannot be negative")

    if accepted_count + rejected_count != candidate_count:
        raise SimulationRunError("accepted_count plus rejected_count must equal candidate_count")


def simulation_run_digest_source(
    simulation_run: dict[str, Any],
) -> dict[str, Any]:
    digest_source = dict(simulation_run)
    digest_source.pop("simulation_run_id", None)

    return digest_source


def expected_simulation_run_id(
    simulation_run: dict[str, Any],
) -> str:
    return "sha256:" + sha256_hex(
        canonical_json_bytes(simulation_run_digest_source(simulation_run))
    )


def build_simulation_run(
    strategy_id: str,
    seed: int,
    market_snapshot_hash: str,
    candidate_count: int,
    accepted_count: int,
    rejected_count: int,
    result_summary_hash: str,
    risk_flags: list[str] | None = None,
    perturbation_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    validate_counts(candidate_count, accepted_count, rejected_count)

    simulation_run = {
        "schema": SIMULATION_RUN_SCHEMA,
        "version": SIMULATION_RUN_VERSION,
        "environment": SIMULATION_ENVIRONMENT,
        "strategy_id": strategy_id,
        "seed": seed,
        "market_snapshot_hash": market_snapshot_hash,
        "candidate_count": candidate_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "risk_flags": list(risk_flags or []),
        "result_summary_hash": result_summary_hash,
        "perturbation_id": perturbation_id,
        "created_at": created_at,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
        "validation_law": (
            "If results are unbelievable right off the bat, "
            "test, simulate, and make slight changes."
        ),
        "boundary_law": [
            "Simulation is the root.",
            "No simulation receipt, no probe plan.",
            "No probe plan, no testnet.",
            "No testnet proof, no live discussion.",
            "The simulator observes.",
            "The artifact records.",
            "The human promotes.",
        ],
    }

    forbidden = forbidden_paths(simulation_run)
    if forbidden:
        joined = ", ".join(forbidden)
        raise SimulationRunError(f"forbidden simulation fields present: {joined}")

    simulation_run["simulation_run_id"] = expected_simulation_run_id(simulation_run)
    validate_simulation_run(simulation_run)

    return simulation_run


def validate_simulation_run(
    simulation_run: dict[str, Any],
) -> None:
    if simulation_run.get("schema") != SIMULATION_RUN_SCHEMA:
        raise SimulationRunError("simulation run schema mismatch")

    if simulation_run.get("environment") != SIMULATION_ENVIRONMENT:
        raise SimulationRunError("simulation run environment must be simulation")

    forbidden = forbidden_paths(simulation_run)
    if forbidden:
        joined = ", ".join(forbidden)
        raise SimulationRunError(f"forbidden simulation fields present: {joined}")

    validate_counts(
        simulation_run.get("candidate_count"),
        simulation_run.get("accepted_count"),
        simulation_run.get("rejected_count"),
    )

    if not isinstance(simulation_run.get("risk_flags"), list):
        raise SimulationRunError("risk_flags must be a list")

    if simulation_run.get("execution_authority") != "none":
        raise SimulationRunError("simulation execution authority must be none")

    if simulation_run.get("artifact_is_command") is not False:
        raise SimulationRunError("simulation artifact_is_command must be false")

    if simulation_run.get("may_execute") is not False:
        raise SimulationRunError("simulation may_execute must be false")

    if simulation_run.get("may_move_capital") is not False:
        raise SimulationRunError("simulation may_move_capital must be false")

    if simulation_run.get("human_promotion_required") is not True:
        raise SimulationRunError("simulation human promotion must be required")

    expected_id = expected_simulation_run_id(simulation_run)

    if simulation_run.get("simulation_run_id") != expected_id:
        raise SimulationRunError("simulation_run_id digest mismatch")


def build_simulation_receipt(
    simulation_run: dict[str, Any],
) -> dict[str, Any]:
    validate_simulation_run(simulation_run)

    return {
        "receipt_type": "SimulationRunReceipt",
        "receipt_version": SIMULATION_RUN_VERSION,
        "schema": SIMULATION_RECEIPT_SCHEMA,
        "environment": SIMULATION_ENVIRONMENT,
        "simulation_run_id": simulation_run["simulation_run_id"],
        "strategy_id": simulation_run["strategy_id"],
        "seed": simulation_run["seed"],
        "market_snapshot_hash": simulation_run["market_snapshot_hash"],
        "candidate_count": simulation_run["candidate_count"],
        "accepted_count": simulation_run["accepted_count"],
        "rejected_count": simulation_run["rejected_count"],
        "risk_flags": simulation_run["risk_flags"],
        "result_summary_hash": simulation_run["result_summary_hash"],
        "perturbation_id": simulation_run["perturbation_id"],
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "human_promotion_required": True,
    }


def seal_simulation_run(
    simulation_run: dict[str, Any],
    previous_cid: str | None,
    ipfs: Any,
    receipt_ledger: JsonlReceiptLedger,
) -> dict[str, Any]:
    receipt = build_simulation_receipt(simulation_run)

    return seal_receipt(
        receipt,
        previous_cid=previous_cid,
        ipfs=ipfs,
        ledger=receipt_ledger,
    )


def require_simulation_receipt_for_probe_plan(
    source_simulation_receipt_cid: str | None,
    ledger_audit: dict[str, Any] | None = None,
) -> bool:
    if not source_simulation_receipt_cid:
        raise SimulationRunError("probe planning requires simulation receipt CID")

    if ledger_audit is None:
        return True

    if ledger_audit.get("valid") is not True:
        raise SimulationRunError("probe planning requires valid receipt ledger audit")

    receipt_cids = ledger_audit.get("receipt_cids")

    if not isinstance(receipt_cids, list):
        raise SimulationRunError("probe planning requires receipt CID membership list")

    if source_simulation_receipt_cid not in receipt_cids:
        raise SimulationRunError("simulation receipt CID must be present in audited ledger")

    if ledger_audit.get("execution_authority") != "none":
        raise SimulationRunError("ledger audit execution authority must be none")

    if ledger_audit.get("may_execute") is not False:
        raise SimulationRunError("ledger audit may_execute must be false")

    if ledger_audit.get("may_move_capital") is not False:
        raise SimulationRunError("ledger audit may_move_capital must be false")

    return True


def build_simulation_promotion_precheck(
    source_simulation_receipt_cid: str,
    ledger_audit: dict[str, Any],
    merkle_anchor_cid: str | None = None,
) -> dict[str, Any]:
    require_simulation_receipt_for_probe_plan(
        source_simulation_receipt_cid,
        ledger_audit=ledger_audit,
    )

    return {
        "schema": SIMULATION_PROMOTION_PRECHECK_SCHEMA,
        "version": SIMULATION_RUN_VERSION,
        "source_simulation_receipt_cid": source_simulation_receipt_cid,
        "ledger_path": ledger_audit.get("ledger_path"),
        "ledger_event_count": ledger_audit.get("event_count"),
        "merkle_anchor_cid": merkle_anchor_cid,
        "probe_plan_eligible": True,
        "execution_authority": "none",
        "artifact_is_command": False,
        "may_execute": False,
        "may_move_capital": False,
        "may_sign": False,
        "may_broadcast": False,
        "human_promotion_required": True,
        "boundary_law": [
            "No simulation receipt, no probe plan.",
            "No audited receipt membership, no probe plan.",
            "A probe plan is not a transaction.",
            "A precheck cannot sign.",
            "A precheck cannot broadcast.",
            "The simulator observes.",
            "The artifact records.",
            "The human promotes.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and optionally ledger a simulation run artifact."
    )
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--market-snapshot-hash", required=True)
    parser.add_argument("--candidate-count", required=True, type=int)
    parser.add_argument("--accepted-count", required=True, type=int)
    parser.add_argument("--rejected-count", required=True, type=int)
    parser.add_argument("--result-summary-hash", required=True)
    parser.add_argument("--risk-flag", action="append", default=[])
    parser.add_argument("--perturbation-id", default=None)
    parser.add_argument(
        "--created-at",
        default="1970-01-01T00:00:00Z",
    )
    parser.add_argument(
        "--simulation-ledger",
        default=None,
        help="Optional JSONL simulation run ledger path.",
    )

    args = parser.parse_args()

    try:
        simulation_run = build_simulation_run(
            strategy_id=args.strategy_id,
            seed=args.seed,
            market_snapshot_hash=args.market_snapshot_hash,
            candidate_count=args.candidate_count,
            accepted_count=args.accepted_count,
            rejected_count=args.rejected_count,
            result_summary_hash=args.result_summary_hash,
            risk_flags=args.risk_flag,
            perturbation_id=args.perturbation_id,
            created_at=args.created_at,
        )

        ledger_event = None
        if args.simulation_ledger:
            ledger = JsonlSimulationRunLedger(Path(args.simulation_ledger))
            ledger_event = ledger.append_run(simulation_run)

    except SimulationRunError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "simulation_run": simulation_run,
                "ledger_event": ledger_event,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
