from pathlib import Path


def test_gate1_boundary_seal_keeps_authority_outside_artifact():
    text = Path("docs/telemetry/EVE_Q_GATE1_BOUNDARY_SEAL_v0_1.md").read_text(encoding="utf-8")
    assert "Observation is permitted" in text
    assert "Authority remains outside the artifact" in text
