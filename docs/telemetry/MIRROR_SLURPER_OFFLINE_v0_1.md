# MirrorSlurper Offline v0.1

## Purpose

Turn the historical `MirrorSlurper` ethics lock into a deterministic adversarial
review membrane for recorded automated-market-maker pool snapshots.

```text
recorded pool snapshot
+ cyclic route candidate
+ stress policy
→ constant-product replay
→ adverse scenario replay
→ CANDIDATE | HOLD | REJECT
→ canonical receipt
```

MirrorSlurper tries to break an apparent edge before any separately reviewed
system can consider promotion. It is an immune system, not an execution engine.

## Supported model

v0.1 deliberately supports only:

- recorded JSON snapshots;
- one chain per candidate;
- constant-product `x*y=k` pools;
- cyclic routes that finish in the starting token;
- unique pools within a route;
- costs denominated in the starting token;
- deterministic gas, reserve, delay, and slippage stress.

Stable-swap curves, concentrated liquidity, token taxes, rebasing assets,
bridges, oracle settlement, live mempool state, and MEV simulation remain out of
scope. A pool label may name its historical venue, but the evaluator applies
only the declared constant-product fixture model.

## Adversarial dimensions

Each stress scenario can increase:

- gas cost through a multiplier;
- adverse input/output reserves in basis points;
- route-output haircut in basis points;
- execution delay in blocks.

Delay is converted to additional adverse reserve movement through the policy's
`delay_adverse_bps_per_block`. The evaluator records both the configured and
effective shifts.

## Verdicts

```text
REJECT
= baseline net profit is zero or negative

HOLD
= baseline is positive but the worst reviewed scenario misses the policy floor

CANDIDATE
= baseline is positive and every reviewed scenario preserves the policy floor
```

`CANDIDATE` is a review classification only. It is not a live proposal,
approval, order, transaction, or execution instruction.

## Determinism and receipts

Snapshot, candidate, and policy documents carry canonical SHA-256 identifiers.
Unknown fields fail closed. Monetary values are decimal strings rather than
binary floating-point numbers. The final receipt ID is SHA-256 over canonical
JSON with `receipt_id` omitted.

The receipt records:

- exact input identities;
- baseline and worst-case net values;
- each scenario's route mechanics and costs;
- failure modes;
- Gate 0 active, Gate 1 pilot-only, Gates 2–6 locked;
- authority, proposal, execution, and capital permissions false.

## CLI

```bash
python -m eve_q.mirror_slurper_offline \
  tests/fixtures/mirror_slurper/pool_snapshot_v0_1.json \
  tests/fixtures/mirror_slurper/candidate_v0_1.json \
  tests/fixtures/mirror_slurper/stress_policy_v0_1.json
```

Write a receipt without changing any input:

```bash
python -m eve_q.mirror_slurper_offline SNAPSHOT CANDIDATE POLICY \
  --output mirror_receipt.json
```

## Boundary

```text
recorded snapshot != current market
simulation != quote
CANDIDATE != proposal
receipt != approval
human review != execution
```

The module performs no network request and contains no wallet, key, signing,
transaction construction, order submission, broadcast, scheduler, webhook,
background loop, autonomous promotion, or capital movement surface.
