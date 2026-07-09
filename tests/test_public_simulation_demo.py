import json

from eve_q.demo_simulation import build_demo_receipt, main


def test_public_demo_receipt_is_simulation_only():
    receipt = build_demo_receipt()

    assert receipt["schema"] == "codex.demo_simulation.v0.1"
    assert receipt["mode"] == "SIMULATION_ONLY"

    assert receipt["market_signal_observed"] is True
    assert receipt["trade_candidate_simulated"] is True
    assert receipt["risk_gate_evaluated"] is True
    assert receipt["charity_allocation_proposed"] is True
    assert receipt["receipt_emitted"] is True

    assert receipt["wallet_signing"] is False
    assert receipt["capital_movement"] is False
    assert receipt["autonomous_execution"] is False
    assert receipt["mainnet_execution"] is False
    assert receipt["artifact_is_command"] is False

    assert receipt["candidate"]["notional_usd"] == 0
    assert receipt["charity_allocation"]["mode"] == "proposal_only"
    assert receipt["charity_allocation"]["percent"] == 15


def test_public_demo_outputs_safe_proof_handle(capsys):
    main()

    captured = capsys.readouterr().out

    assert "market signal observed" in captured
    assert "trade candidate simulated" in captured
    assert "risk gate evaluated" in captured
    assert "charity allocation proposed" in captured
    assert "receipt emitted" in captured
    assert "capital movement: false" in captured
    assert "wallet signing: false" in captured

    json_payload = captured.split("\n\n", 1)[1]
    receipt = json.loads(json_payload)

    assert receipt["mode"] == "SIMULATION_ONLY"
    assert receipt["capital_movement"] is False
    assert receipt["wallet_signing"] is False
