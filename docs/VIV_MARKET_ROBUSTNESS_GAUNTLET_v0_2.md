# ViV Market Robustness Gauntlet v0.2

Status: candidate implementation  
Issue: #140  
Authority: none

## Purpose

ViV v0.2 attacks the **evidence produced by the existing market robustness engine**.

She does not create new price shocks, discover markets, call RPC endpoints, execute Rust repricing, access wallets, borrow liquidity, sign, broadcast, deploy, or move capital.

```text
existing delta robustness engine
  → deterministic slippage / fee / latency / gas / rate scenarios
  → exact repricing evidence
  → DeltaRobustnessReceipt
  → ViV market evidence gauntlet
  → blocked mutation | escaped mutation
  → builder repair loop
  → human promotion
```

> ViV does not generate the storm. She attacks the story the receipt tells about surviving it.

## Existing organs reused

The implementation deliberately reuses:

- `eve_q.delta_robustness.PerturbationScenario`
- `eve_q.delta_robustness.DeltaRobustnessReceipt`
- `eve_q.perturbation_calibration`
- the existing Rust exact repricer
- `eve_q.viv_adversarial.run_viv_gauntlet(...)`
- `eve_q.viv_adversarial_receipt.v0.1`

No second market model, perturbation engine, or receipt family is introduced.

## Serialized robustness validator

`validate_delta_robustness_artifact(...)` checks a JSON representation of the existing robustness receipt.

It recomputes and verifies:

- scenario count;
- survival count;
- survival rate;
- worst-case log delta;
- median log delta;
- failure-reason counts;
- robustness class;
- ordered scenario-set SHA-256;
- the truncated `delta-robustness:` content-addressed receipt ID;
- scenario namespaces and uniqueness;
- snapshot hashes and request namespaces;
- per-result failure semantics;
- all authority locks.

The validator provides a first-class artifact boundary for saved, transmitted, or reviewed robustness evidence. It does not certify market safety.

## Mutation pack

v0.2 attacks ten ways a robustness report could lie:

1. flip authority to true;
2. inflate survival count;
3. inflate survival rate;
4. promote robustness class;
5. suppress the worst-case delta;
6. delete a scenario result while leaving stale summaries;
7. suppress failure-reason counts;
8. tamper with the scenario-set hash;
9. tamper with the receipt ID;
10. flip one per-scenario margin result.

Every attack is deterministic from the root seed and case ID. The candidate is deep-copied and must remain unchanged.

## Result semantics

### `blocked`

The robustness validator rejected the exact mutated artifact. This proves only that the configured mutation did not cross that validator invocation.

### `escaped`

The mutated evidence passed validation. The existing ViV receipt marks `repair_required: true` and returns the finding to the builder loop.

Passing all configured attacks is evidence, not certification.

## CLI

```bash
codex-viv-market-gauntlet \
  --candidate delta-robustness-receipt.json \
  --seed 7331 \
  --created-at 2026-08-05T00:00:00Z \
  --receipt-out viv-market-receipt.json
```

Equivalent module invocation:

```bash
python -m eve_q.viv_market_adversarial ...
```

The CLI has no plugin parameter, callback import path, URL, wallet, RPC, or execution option.

Exit codes:

- `0`: all configured mutations were blocked;
- `1`: invalid baseline, malformed input, or harness error;
- `2`: at least one mutation escaped.

## Role separation

```text
Hecate
  guards external ingress.

Delta robustness engine
  generates and reprices bounded adverse market states.

ViV market gauntlet
  attacks the serialized claim about those results.

Paladine
  reviews consent and boundary integrity.

Loopmother
  reviews outward consequences before externalization.
```

## Hard boundaries

```yaml
role: sandboxed_market_evidence_adversary
self_certifying: false
authority: false
network_access: false
market_discovery: false
repricing_execution: false
dynamic_code_loading: false
human_promotion_required: true
may_execute: false
may_deploy: false
may_merge: false
may_sign: false
may_broadcast: false
may_access_wallet: false
may_move_capital: false
may_mutate_canonical_memory: false
```

## Threat-model limits

- v0.2 attacks JSON evidence, not running markets or processes.
- It does not validate economic assumptions beyond internal receipt consistency.
- A coherent receipt may still be based on poor data, incomplete scenarios, or an inadequate model.
- The validator duplicates the current canonical receipt arithmetic and must evolve with that contract.
- Floating-point comparisons use the same narrow tolerance as the receipt constructors.
- Determinism improves reproducibility, not completeness.

## Root law

> The storm engine perturbs. The adversary falsifies. The builder repairs. The human promotes.
