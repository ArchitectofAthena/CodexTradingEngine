# Gate 1A.1 ViV Economic and Epistemic Gauntlet v0.1

## Purpose

Extend the existing deterministic ViV enclosure over the Gate 1A.1 evidence bundle.

```text
valid bounded evidence bundle
→ deep copy
→ deterministic mutation seed
→ one economic, source, benchmark, gate, language, or charity attack
→ strict validator
→ blocked | escaped
→ immutable ViV receipt
→ human repair loop if any escape exists
```

This is not a second adversarial engine. It reuses `AdversarialCase`, `run_viv_gauntlet`, receipt hashing, candidate immutability checks, and ViV’s non-authority doctrine from `eve_q.viv_adversarial`.

## Baseline evidence posture

The fixture preserves:

- measured gas, protocol fees, slippage, liquidity, and latency;
- two fresh, independently operated, reviewed Ethereum Sepolia sources;
- observation-only consensus with no averaging or route selection;
- exact classical/QAOA QUBO and constraint pairing;
- all three precommitted QAOA seeds;
- complete run disclosure;
- the honest benchmark outcome `QAOA_ADDS_NO_MEASURABLE_VALUE`;
- testnet research-only language;
- rollback and kill-switch readiness;
- Gate 1B locked;
- charity as target-only, non-causal, non-authoritative telemetry.

## Eighteen required mutations

| # | Mutation | Required containment |
|---|---|---|
| 1 | omit gas | blocked |
| 2 | omit protocol fees | blocked |
| 3 | suppress slippage | blocked |
| 4 | inflate liquidity | blocked |
| 5 | erase latency | blocked |
| 6 | promote stale telemetry | blocked |
| 7 | collapse conflicting sources into false consensus | blocked |
| 8 | disguise shared provenance as independence | blocked |
| 9 | pair QAOA with a weaker classical baseline | blocked |
| 10 | change QUBO or constraints between paired runs | blocked |
| 11 | cherry-pick favorable QAOA seeds | blocked |
| 12 | suppress failed or infeasible runs | blocked |
| 13 | convert testnet edge into profitability language | blocked |
| 14 | convert receipt success into gate permission | blocked |
| 15 | weaken rollback or kill-switch state | blocked |
| 16 | describe target-chain gas hypotheses as measured facts | blocked |
| 17 | claim charity impact without transfer and outcome evidence | blocked |
| 18 | convert charity telemetry into automatic reward or authority | blocked |

Every mutation is deterministic from the root seed and case ID. ViV mutates only a copy; the candidate must remain byte-identical.

## Decision posture

```text
all mutations blocked
→ gauntlet pass as containment evidence
→ not certification

any mutation escaped
→ gauntlet fail
→ repair_required = true
→ Gate 1A.1 HOLD until a human repairs and reruns
```

A blocked mutation demonstrates that one attack was contained. It does not prove the target correct, complete, profitable, safe, or ready for Gate 1B.

## CLI

```bash
codex-gate1a1-viv \
  --candidate tests/fixtures/gate1a1_viv_evidence_bundle_v0_1.json \
  --seed 145 \
  --receipt-out artifacts/gate1a1/viv-receipt.json
```

Expected decision-critical fields:

```yaml
case_count: 18
blocked_count: 18
escaped_count: 0
overall_outcome: pass
candidate_unchanged: true
self_certifying: false
authority: false
human_promotion_required: true
```

## Boundary

```yaml
self_certifying: false
authority: false
artifact_is_command: false
network_access: false
dynamic_code_loading: false
may_execute: false
may_deploy: false
may_merge: false
may_sign: false
may_broadcast: false
may_access_wallet: false
may_move_capital: false
may_mutate_canonical_memory: false
human_promotion_required: true
```

> ViV may break the candidate, never the enclosure. The adversary records. The human promotes.
