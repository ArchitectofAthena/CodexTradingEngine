import json
import subprocess
import sys
from pathlib import Path

CARRIER_PATH = Path("examples/artifact_carrier_manifest.example.json")
ATTESTATION_PATH = Path("examples/receipt_carrier_attestation.example.json")


def run_cli(carrier_path, attestation_path):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.receipt_carrier_attestation",
            "--carrier",
            str(carrier_path),
            "--attestation",
            str(attestation_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_receipt_carrier_attestation_cli_validates_examples():
    result = run_cli(CARRIER_PATH, ATTESTATION_PATH)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"errors": [], "valid": True}
    assert result.stderr == ""


def test_receipt_carrier_attestation_cli_reports_manifest_drift(tmp_path):
    carrier = json.loads(CARRIER_PATH.read_text())
    carrier["payload_type"] = "changed_payload"

    drifted_carrier = tmp_path / "carrier.json"
    drifted_carrier.write_text(json.dumps(carrier))

    result = run_cli(drifted_carrier, ATTESTATION_PATH)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert "carrier_manifest_sha256 mismatch" in payload["errors"]


def test_receipt_carrier_attestation_cli_reports_missing_file(tmp_path):
    missing = tmp_path / "missing.json"

    result = run_cli(missing, ATTESTATION_PATH)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["errors"]
    assert payload["errors"][0].startswith("failed to load input:")
