from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eve_q.gate1a1_benchmark_corpus import evaluate_corpus

ROOT = Path(__file__).parents[1]
SEAL_PATH = ROOT / "benchmarks" / "gate1a1_fixed_benchmark_seal_v0_1.json"
EXPECTED_SOURCE_COMMIT = "15351318fedf5523a38a9f345d588b7546ecdb75"
EXPECTED_CORPUS_PATH = "benchmarks/gate1a1_fixed_benchmark_corpus_v0_1.json"
EXPECTED_REPORT_PATH = "benchmarks/gate1a1_fixed_benchmark_expected_report_v0_1.json"
EXPECTED_SEAL_KEYS = {
    "schema_version",
    "seal_id",
    "source_commit",
    "corpus_path",
    "corpus_git_blob_sha",
    "expected_report_path",
    "expected_report_git_blob_sha",
    "corpus_sha256",
    "case_qubo_sha256",
    "expected_outcome",
    "authority",
    "artifact_is_command",
    "automatic_gate_promotion",
    "gate1b_activated",
    "may_execute",
    "may_sign",
    "may_submit_transaction",
    "may_access_wallet",
    "may_move_capital",
    "human_promotion_required",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def test_benchmark_seal_binds_exact_control_plane() -> None:
    seal = _load(SEAL_PATH)

    assert set(seal) == EXPECTED_SEAL_KEYS
    assert seal["schema_version"] == "gate1a1-benchmark-seal-v0.1"
    assert seal["seal_id"] == "gate1a1-benchmark-seal:v0.1"
    assert seal["source_commit"] == EXPECTED_SOURCE_COMMIT
    assert seal["corpus_path"] == EXPECTED_CORPUS_PATH
    assert seal["expected_report_path"] == EXPECTED_REPORT_PATH


def test_benchmark_seal_binds_exact_artifacts_and_outcome() -> None:
    seal = _load(SEAL_PATH)
    corpus_path = ROOT / str(seal["corpus_path"])
    expected_report_path = ROOT / str(seal["expected_report_path"])
    corpus = _load(corpus_path)
    expected_report = _load(expected_report_path)
    evaluated_report = evaluate_corpus(corpus)

    assert _git_blob_sha(corpus_path) == seal["corpus_git_blob_sha"]
    assert _git_blob_sha(expected_report_path) == seal["expected_report_git_blob_sha"]
    assert expected_report["corpus_sha256"] == seal["corpus_sha256"]
    assert evaluated_report["corpus_sha256"] == seal["corpus_sha256"]

    corpus_qubo_hashes = [case["qubo"]["qubo_sha256"] for case in corpus["cases"]]
    report_qubo_hashes = [case["qubo_sha256"] for case in expected_report["case_results"]]
    assert corpus_qubo_hashes == seal["case_qubo_sha256"]
    assert report_qubo_hashes == seal["case_qubo_sha256"]

    assert expected_report["overall_outcome"] == seal["expected_outcome"]
    assert evaluated_report["overall_outcome"] == seal["expected_outcome"]
    assert evaluated_report == expected_report


def test_benchmark_seal_cannot_confer_authority() -> None:
    seal = _load(SEAL_PATH)
    required_false = (
        "authority",
        "artifact_is_command",
        "automatic_gate_promotion",
        "gate1b_activated",
        "may_execute",
        "may_sign",
        "may_submit_transaction",
        "may_access_wallet",
        "may_move_capital",
    )
    assert all(seal[field] is False for field in required_false)
    assert seal["human_promotion_required"] is True
