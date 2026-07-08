import json
import subprocess
import sys
from pathlib import Path

MANIFEST_PATH = Path("examples/artifact_carrier_manifest.example.json")


def run_cli(manifest_path):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "eve_q.artifact_carrier",
            "--manifest",
            str(manifest_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_artifact_carrier_cli_validates_example_manifest():
    result = run_cli(MANIFEST_PATH)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"errors": [], "valid": True}
    assert result.stderr == ""


def test_artifact_carrier_cli_reports_invalid_manifest(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest["execution_authority"] = "scheduler"

    invalid_manifest = tmp_path / "invalid_manifest.json"
    invalid_manifest.write_text(json.dumps(manifest))

    result = run_cli(invalid_manifest)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert any("execution_authority must be none" in error for error in payload["errors"])


def test_artifact_carrier_cli_reports_missing_file(tmp_path):
    missing = tmp_path / "missing.json"

    result = run_cli(missing)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["valid"] is False
    assert payload["errors"]
    assert payload["errors"][0].startswith("failed to load input:")
