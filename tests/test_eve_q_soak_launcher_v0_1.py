from pathlib import Path


def test_soak_launcher_is_simulation_only_and_fail_closed():
    launcher = Path("scripts/run_eve_q_soak_v0_1.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in launcher
    assert "--cycles" in launcher
    assert "--control-plane-root" in launcher
    assert "summary[\"ok\"] is True" in launcher
    assert "proposal_failures" in launcher
    assert "chain_failures" in launcher
    assert "unauthorized_promotions" in launcher
    assert "replay_failures" in launcher

    forbidden = [
        "private_key",
        "wallet_sign",
        "send_transaction",
        "broadcast_transaction",
        "eth_sendRawTransaction",
    ]
    for phrase in forbidden:
        assert phrase not in launcher
