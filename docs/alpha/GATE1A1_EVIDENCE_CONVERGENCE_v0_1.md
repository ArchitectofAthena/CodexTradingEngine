# Gate 1A.1 Evidence Convergence v0.1

Gate 1A.1 converts independently produced evidence into one deterministic review decision without activating any later gate.

```text
source quorum
+ exact classical/QAOA pairing
+ reproducible Rust origin and replay
+ ViV economic and epistemic attacks
+ complete friction-aware economics
+ simulation-only charity target contract
+ rollback evidence
→ HOLD | QAOA_RESEARCH_ONLY | READY_FOR_GATE1B_REVIEW
```

## Purpose

The convergence organ is deliberately boring at the authority boundary. It reads one inert, schema-valid evidence bundle and emits:

- a content-addressed evidence digest;
- explicit hold reasons;
- one compact operator report;
- one deterministic next decision;
- an authority-false receipt.

It does not collect telemetry, average sources, select routes, run QAOA, compile Rust, execute ViV attacks, activate Gate 1B, create wallets, sign, submit transactions, transfer charity funds, or move capital.

## Commands

```bash
codex-gate1a1 \
  --evidence benchmarks/gate1a1_evidence_bundle_seed_v0_1.json \
  --generated-at 2026-08-06T16:00:00Z \
  --output artifacts/gate1a1-evidence/decision-receipt.json
```

The seeded bundle is a deterministic contract fixture. It is not real market, source-quorum, QAOA-value, Rust-provenance, charity-impact, or readiness evidence.

## Decision law

### `HOLD`

Any critical defect forces `HOLD`, including:

- fewer than two independently operated reviewed sources;
- source disagreement, shared-provenance concentration, staleness, unit ambiguity, or expired review;
- missing exact classical/QAOA pair;
- different QUBO hashes or assumptions between paired runs;
- missing solver, resource, or repeated-seed evidence;
- verifier disagreement;
- unexplained Rust origin, build, binary, target, schema, clean-tree, or replay state;
- incomplete required ViV coverage or any critical escaped mutation;
- incomplete or unit-ambiguous economics;
- omitted gas, protocol fees, slippage, latency, liquidity, repayment, or other declared friction evidence;
- incomplete simulation-only charity target contract;
- failed kill-switch or rollback replay.

### `QAOA_RESEARCH_ONLY`

All Gate 1A.1 evidence requirements are sound, but QAOA has not demonstrated reproducible measurable value under the recorded benchmark contract.

This is a successful evidence outcome. Classical methods may remain the operational research spine while QAOA stays available for continued comparison.

### `READY_FOR_GATE1B_REVIEW`

All required Gate 1A.1 evidence is complete and QAOA has met the supplied value criterion.

This result means only:

> A human may inspect a separate Gate 1B proposal.

It does not activate Gate 1B or widen any execution, wallet, signing, transaction, charity-transfer, or capital boundary.

## Compact surface

The text report is deliberately summary-first:

```text
WORKFLOW
SOURCE_QUORUM
FRESHNESS
ECONOMICS
CLASSICAL_BASELINE
QAOA_COMPARISON
RUST_VERIFICATION
ADVERSARIAL_RESULTS
EXECUTION_LOCKS
CHARITY_POSTURE
ROLLBACK
NEXT_DECISION
```

Raw evidence remains outside the receipt and is referenced through the source bundle's `evidence_refs`. A reference points to evidence; it does not grant that evidence authority.

## Determinism

The evidence digest hashes the complete canonical input bundle.

The decision receipt digest hashes stable decision material and intentionally excludes `generated_at`. Identical evidence therefore produces the same receipt identity across runtimes and invocation times.

## Boundary

```yaml
artifact_is_command: false
authority: false
automatic_gate_promotion: false
gate1b_activated: false
may_execute: false
may_sign: false
may_submit_transaction: false
may_access_wallet: false
may_move_capital: false
human_promotion_required: true
```

> Evidence may converge. Authority does not emerge from convergence.

Tracks #145.
