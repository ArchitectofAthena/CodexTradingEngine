"""Public simulation demo for CodexTradingEngine.

This demo proves the safe public claim:
telemetry + simulation + audit artifact = yes
live capital movement = no
wallet signing = no
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def build_demo_receipt() -> dict:
    now = datetime.now(timezone.utc).isoformat()

    return {
        "schema": "codex.demo_simulation.v0.1",
        "timestamp_utc": now,
        "mode": "SIMULATION_ONLY",
        "market_signal_observed": True,
        "market_data_source": "demo_static_fixture",
        "trade_candidate_simulated": True,
        "candidate": {
            "pair": "ETH/USDC",
            "chain": "Base",
            "direction": "observe_only",
            "notional_usd": 0,
        },
        "risk_gate_evaluated": True,
        "risk_gate_status": "PASS_FOR_SIMULATION_ONLY",
        "charity_allocation_proposed": True,
        "charity_allocation": {
            "enabled": True,
            "mode": "proposal_only",
            "percent": 15,
        },
        "receipt_emitted": True,
        "wallet_signing": False,
        "capital_movement": False,
        "autonomous_execution": False,
        "mainnet_execution": False,
        "artifact_is_command": False,
        "summary": (
            "Telemetry observed, candidate simulated, risk gate evaluated, "
            "charity allocation proposed, receipt emitted. No funds moved."
        ),
    }


def main() -> None:
    receipt = build_demo_receipt()

    print("market signal observed")
    print("trade candidate simulated")
    print("risk gate evaluated")
    print("charity allocation proposed")
    print("receipt emitted")
    print("capital movement: false")
    print("wallet signing: false")
    print()
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
