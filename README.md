# CodexTradingEngine

**Simulation-first crypto telemetry and safety research engine for Termux/Python.**

CodexTradingEngine emits proposals, artifact receipts, risk reports, TTL evaluations, CID-backed carrier manifests, charity allocation artifacts, and bounded arbitrage research candidates. It does **not** autonomously move capital.

## Safety Posture

- No wallet signing
- No autonomous capital movement
- No scheduler-triggered execution
- No webhook-triggered execution
- No reverse execution channel
- Human promotion required for real capital touchpoints
- Artifacts are records, not commands
- Metadata is pointer, not authority
- CID-backed carrier manifests may point to memory, but keys remain consent

## Core Law

```text
Agent proposes.
Artifact records.
Verifier gates.
Registry remembers.
Human promotes.
```

```text
Telemetry before autonomy.
Policy before runtime.
Membrane before motion.
```

## Current Constitutional Surfaces

- `contracts/organ_contract.json` defines the local constitutional membrane.
- `contracts/ttl_policy.json` defines time-bounded authority and graceful degradation.
- `contracts/artifact_carrier_manifest.json` defines safe CID-backed carrier manifests.
- `eve_q/receipt_emitter.py` emits artifact receipts.
- `eve_q/organ_contract.py` validates receipts against the organ contract.
- `eve_q/ttl_policy.py` evaluates TTL state without runtime authority.
- `eve_q/artifact_carrier.py` validates artifact carrier manifests.

## Allowed Outputs

CodexTradingEngine may produce:

- artifact receipts
- safety bridge receipts
- risk reports
- simulation summaries
- drift audits
- testnet results
- charity allocation proposals
- CID-backed carrier manifests
- QAOA-ready price-delta candidates
- QAOA confidence receipts
- Rust exact-repricing evidence
- perturbed-state robustness receipts
- flash-liquidity geometry candidates
- Rust flash-liquidity verification evidence

These outputs are review artifacts. They are not commands.

## Forbidden Capabilities

CodexTradingEngine must not perform:

- wallet signing
- transaction signing
- autonomous capital movement
- governance mutation
- webhook-triggered execution
- scheduler-triggered execution
- silent remote command execution
- self-promotion
- receipt mutation after emission

## Artifact Carrier Law

```text
The image carries the acorn.
The CID points to the memory.
The key is consent.
The artifact never commands.
```

Artifact carrier manifests can point to public, encrypted, or private payloads. Private or encrypted payloads require encryption metadata and human-held or external-vault key custody. Secrets, wallet seeds, private keys, API keys, shell commands, and execution fields are rejected.

## Hybrid Arbitrage Research Lane

```text
Python constructs the market graph, QUBO, policy context, and receipts.
Qiskit QAOA triangulates and samples price-delta candidates.
Rust performs exact route, fee, slippage, latency, gas, and margin verification.
Classical solvers remain available for fallback, benchmarking, and independent checks.
```

The implementation is intentionally simulation-only. Qiskit performs bounded local sampling and emits confidence evidence. Python binds that evidence to a strict request and invokes an explicit local Rust verifier with `shell=False`. Rust independently reconstructs candidate identity, reprices the route, and returns `authority: false` evidence.

Phase 2C-1 then generates deterministic alternate market states for reserve movement, cost changes, slippage, latency, and gas. Every state is hash-bound and sent through the same Rust verifier. The resulting receipt records survival rate, worst-case delta, median delta, failure reasons, and a declared robustness class. The included scenario values are teaching fixtures, not calibrated market probabilities.

Phase 2C-2 expands a route into provider, borrowed-asset, and amount-bucket geometry. QAOA may rank complete route-plus-liquidity candidates. A second isolated Rust binary reconstructs the triangular route, verifies declared capacity, calculates provider repayment, and determines whether the complete loop can repay itself above a declared minimum-profit threshold. No borrowing or transaction submission occurs.

The complete Python → Rust subprocess, robustness, and flash-liquidity paths are exercised in CI against real compiled verifier binaries, including candidate-identity rejection and authority-boundary checks.

```text
QAOA discovers the geometry of the opportunity.
Rust confirms that the geometry still exists.
Perturbation tests whether that geometry survives pressure.
Flash-liquidity verification tests whether temporary capital can be repaid.
Python controls what may happen with that knowledge.
Human review remains the promotion gate.
```

## Status

This repository is an early-stage safety, telemetry, and arbitrage-research project.

It is not a live autonomous trading engine.
It is not a wallet.
It is not a transaction signer.
It is not financial advice.

Human review and explicit human promotion remain required for any real-world capital touchpoint.

<!-- constitutional-surfaces-index:start -->

## Constitutional Surfaces Index

CodexTradingEngine is simulation-first and safety-gated. These surfaces define the current artifact membrane:

| Surface | File | Purpose |
| --- | --- | --- |
| Artifact carrier validator | `eve_q/artifact_carrier.py` | Validates CID-backed carrier manifests without granting execution authority. |
| Artifact carrier example | `examples/artifact_carrier_manifest.example.json` | Provides a deterministic teaching artifact for safe carrier manifests. |
| Artifact carrier example docs | `docs/artifact_carrier_manifest_example.md` | Documents the carrier law: the artifact carries memory, not authority. |
| Receipt carrier attestation validator | `eve_q/receipt_carrier_attestation.py` | Binds a receipt identifier to a carrier manifest digest and CID as a review artifact. |
| Receipt carrier attestation example | `examples/receipt_carrier_attestation.example.json` | Demonstrates safe receipt-to-carrier attestation. |
| Receipt carrier attestation docs | `docs/receipt_carrier_attestation_example.md` | Documents attestation drift detection and non-execution boundaries. |
| Membrane metadata extractor and attestation bridge | `eve_q/membrane_tool.py` | Extracts carrier manifests from PNG Comment metadata, validates carrier law, and can compare receipt attestations without execution authority. |
| QAOA delta triangulation core | `eve_q/qaoa_delta.py` | Enumerates triangular price deltas, builds QUBO/Ising contracts, and provides a classical fallback with `authority: false`. |
| QAOA sampling and confidence receipts | `eve_q/qaoa_sampling.py` | Performs bounded local sampling, deterministic decoding, and exact-baseline comparison. |
| Python-to-Rust repricing bridge | `eve_q/rust_repricing.py` | Binds candidate evidence to a strict subprocess request and fails closed on protocol drift. |
| Perturbed-state robustness engine | `eve_q/delta_robustness.py` | Reprices a selected candidate across deterministic alternate market states and emits non-authoritative survival evidence. |
| Flash-liquidity geometry | `eve_q/flash_liquidity.py` | Expands routes into provider and amount-bucket choices, builds the combined QUBO, and validates Rust evidence. |
| Rust exact delta verifier | `rust/delta-verifier/` | Reprices a closed triangular route after fee, slippage, latency, gas, and margin assumptions without network access. |
| Rust flash-liquidity verifier | `rust/delta-verifier/src/bin/codex-flash-liquidity-verifier.rs` | Verifies route identity, capacity, provider repayment, and minimum net profit without borrowing or network access. |
| Repricing request schema | `schemas/delta_repricing_request.schema.json` | Defines the strict hash-bound candidate request surface. |
| Repricing response schema | `schemas/delta_repricing_response.schema.json` | Defines the strict exact-verification response surface. |
| Robustness receipt schema | `schemas/delta_robustness_receipt.schema.json` | Defines scenario, survival, failure, and authority invariants for robustness evidence. |
| Flash-liquidity request schema | `schemas/flash_liquidity_request.schema.json` | Defines the route, provider, bucket, capacity, and repayment request surface. |
| Flash-liquidity response schema | `schemas/flash_liquidity_response.schema.json` | Defines exact capacity and repayment verification evidence. |
| Hybrid delta architecture | `docs/QAOA_DELTA_TRIANGULATION_v0_1.md` | Defines Python, Qiskit, Rust, fallback, and authority boundaries. |
| Phase 2A architecture | `docs/QAOA_DELTA_PHASE_2A.md` | Defines bounded QAOA sampling and confidence receipts. |
| Phase 2B architecture | `docs/QAOA_DELTA_PHASE_2B.md` | Defines the isolated Python-to-Rust exact-repricing contract. |
| Phase 2C-1 architecture | `docs/QAOA_DELTA_PHASE_2C1.md` | Defines deterministic perturbed-state robustness evidence. |
| Phase 2C-2 architecture | `docs/QAOA_DELTA_PHASE_2C2.md` | Defines route-plus-provider-plus-amount geometry and repayment verification. |
| Hybrid delta CI | `.github/workflows/hybrid-delta-ci.yml` | Validates Python 3.11/3.13, Qiskit 2.5, stable Rust, exact repricing, robustness, and flash-liquidity verification. |

Membrane bridge:

`python -m eve_q.membrane_tool --image <png> --attestation <attestation.json>`

Chain:

`image metadata -> carrier manifest -> receipt attestation -> validation result`

Hybrid delta chain:

`market snapshot -> triangular cycles -> route QUBO -> QAOA route receipt -> Rust exact repricing -> perturbed-state robustness -> route/provider/bucket QUBO -> QAOA liquidity receipt -> Rust capacity and repayment verification -> policy review -> simulation receipt`

Current law:

```text
Image carries acorn.
The validator compares.
The attestation binds.
The image carries.
Receipt remembers.
Carrier points.
Hash detects drift.
TTL expires.
CI guards.
Human promotes.
```

Safety boundary:

- no autonomous capital movement
- no wallet signing
- no scheduler authority
- no reverse execution channel
- no IPFS daemon dependency for validation
- no image metadata dependency for validation
- no metadata writing
- no flash-loan execution
- no remote quantum execution by default

<!-- constitutional-surfaces-index:end -->
