from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from eve_q.gate1a1_benchmark_corpus import canonical_sha256, evaluate_corpus, render_summary

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "benchmarks" / "gate1a1_fixed_benchmark_corpus_v0_1.json"
SEAL = ROOT / "benchmarks" / "gate1a1_fixed_benchmark_seal_v0_1.json"
EXPECTED_REPORT = ROOT / "benchmarks" / "gate1a1_fixed_benchmark_expected_report_v0_1.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def reseal_corpus_id(corpus: dict[str, object]) -> None:
    payload = {key: value for key, value in corpus.items() if key != "corpus_id"}
    corpus["corpus_id"] = f"gate1a1-benchmark-corpus:{canonical_sha256(payload)[:24]}"


def reseal_run(run: dict[str, object]) -> None:
    payload = {key: value for key, value in run.items() if key != "run_sha256"}
    run["run_sha256"] = canonical_sha256(payload)


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def test_fixed_corpus_is_deterministic_and_adds_no_measurable_value() -> None:
    corpus = load_fixture()
    first = evaluate_corpus(corpus)
    second = evaluate_corpus(copy.deepcopy(corpus))

    assert first == second
    assert first["overall_outcome"] == "QAOA_ADDS_NO_MEASURABLE_VALUE"
    assert first["hold_reasons"] == []
    assert len(first["case_results"]) == 3
    assert all(item["solution_agreement"] is True for item in first["case_results"])
    assert all(item["verifier_agreement"] is True for item in first["case_results"])
    assert first["authority"] is False
    assert first["gate1b_activated"] is False
    assert first["may_execute"] is False
    assert first["may_move_capital"] is False


def test_immutable_seal_binds_exact_control_plane_and_payload() -> None:
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    corpus = load_fixture()
    expected_report = json.loads(EXPECTED_REPORT.read_text(encoding="utf-8"))

    assert set(seal) == {
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
    assert seal["source_commit"] == "15351318fedf5523a38a9f345d588b7546ecdb75"
    assert seal["corpus_path"] == "benchmarks/gate1a1_fixed_benchmark_corpus_v0_1.json"
    assert seal["expected_report_path"] == "benchmarks/gate1a1_fixed_benchmark_expected_report_v0_1.json"
    assert seal["corpus_git_blob_sha"] == git_blob_sha(FIXTURE)
    assert seal["expected_report_git_blob_sha"] == git_blob_sha(EXPECTED_REPORT)
    assert seal["corpus_sha256"] == canonical_sha256(corpus)
    assert seal["corpus_sha256"] == expected_report["corpus_sha256"]
    assert seal["case_qubo_sha256"] == [
        case["qubo"]["qubo_sha256"] for case in corpus["cases"]
    ]
    assert evaluate_corpus(corpus) == expected_report
    assert seal["expected_outcome"] == expected_report["overall_outcome"]
    assert seal["expected_outcome"] == "QAOA_ADDS_NO_MEASURABLE_VALUE"

    for field in (
        "authority",
        "artifact_is_command",
        "automatic_gate_promotion",
        "gate1b_activated",
        "may_execute",
        "may_sign",
        "may_submit_transaction",
        "may_access_wallet",
        "may_move_capital",
    ):
        assert seal[field] is False
    assert seal["human_promotion_required"] is True


def test_qubo_hash_tamper_forces_hold() -> None:
    corpus = load_fixture()
    corpus["cases"][0]["qubo"]["linear"][0][1] = -99.0
    reseal_corpus_id(corpus)

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert any("qubo_sha256" in reason for reason in report["hold_reasons"])


def test_qaoa_must_bind_exact_classical_qubo() -> None:
    corpus = load_fixture()
    corpus["cases"][0]["qaoa"]["same_qubo_sha256"] = "0" * 64
    reseal_corpus_id(corpus)

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert any("not bound" in reason for reason in report["hold_reasons"])


def test_duplicate_seed_cherry_pick_forces_hold() -> None:
    corpus = load_fixture()
    runs = corpus["cases"][0]["qaoa"]["runs"]
    runs[1]["seed"] = runs[0]["seed"]
    reseal_run(runs[1])
    reseal_corpus_id(corpus)

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert report["hold_reasons"]


def test_objective_rewrite_cannot_be_resealed_by_claim_only() -> None:
    corpus = load_fixture()
    run = corpus["cases"][1]["qaoa"]["runs"][0]
    run["objective_value"] = -6000.0
    reseal_run(run)
    reseal_corpus_id(corpus)

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert any("objective_value" in reason for reason in report["hold_reasons"])


def test_authority_flip_forces_hold() -> None:
    corpus = load_fixture()
    corpus["may_execute"] = True

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert any("may_execute" in reason for reason in report["hold_reasons"])


def test_expected_outcome_is_machine_checked() -> None:
    corpus = load_fixture()
    corpus["cases"][2]["expected_outcome"] = "QAOA_CANDIDATE_FOR_FURTHER_TESTING"
    reseal_corpus_id(corpus)

    report = evaluate_corpus(corpus)

    assert report["overall_outcome"] == "HOLD"
    assert any("expected_outcome mismatch" in reason for reason in report["hold_reasons"])


def test_summary_is_compact_and_preserves_locks() -> None:
    summary = render_summary(evaluate_corpus(load_fixture()))

    assert "GATE1A1_BENCHMARK=QAOA_ADDS_NO_MEASURABLE_VALUE" in summary
    assert "CASES=3" in summary
    assert "AUTHORITY=false" in summary
    assert "GATE1B_ACTIVATED=false" in summary
    assert "HUMAN_PROMOTION_REQUIRED=true" in summary
