# Strategy-Packet Consumer and Seeded Planning-Uplift Benchmark v0.1

## Purpose

This lane connects the SpiralBloom remote-planning compiler to the Codex local
verification engine without granting remote providers execution authority or making
the local fast path depend on cloud availability.

The input is a `local_strategy_packet_v0.1` artifact compiled by
`ArchitectofAthena/spiralbloom-os`. Codex does not trust the packet merely because it
has a valid hash or several agreeing providers. It reconstructs the local benchmark
case, route candidates, provider identities, and amount buckets before accepting a
single evaluation hint.

The output is a deterministic historical-replay receipt that compares the
packet-guided candidate with the existing local-only exact baseline.

## Architecture

```text
sanitized remote evidence
→ SpiralBloom strategy-packet compiler
→ expiring local_strategy_packet_v0.1
→ Codex packet hash / TTL / lineage membrane
→ local candidate-universe reconstruction
→ bounded compare-only hint
→ identical local route QUBO
→ exact classical comparison
→ Rust route repricing
→ source-bound perturbation calibration
→ Rust-backed robustness evaluation
→ bounded provider / amount-bucket geometry
→ exact local flash-QUBO comparison
→ Rust capacity and repayment verification
→ planning-uplift receipt
→ human review
```

Nothing in this chain signs, borrows, submits, schedules, deploys, mutates a wallet,
or promotes itself.

## Packet membrane

`eve_q/strategy_packet_uplift.py` accepts only the exact top-level surface of
`local_strategy_packet_v0.1`.

It rejects:

- packet-hash drift;
- stale or internally inconsistent TTLs;
- unknown packet versions;
- packet or evidence authority escalation;
- raw provider response retention;
- unknown provider identities;
- malformed evidence hashes or timestamps;
- disagreement-summary drift;
- missing `agreement_is_not_truth`;
- a remote dependency on the local fast path;
- missing human-promotion or deterministic-revalidation requirements;
- incomplete prohibited-action declarations;
- snapshot-manifest mismatch;
- source-commit mismatch;
- benchmark mismatch;
- route, provider, or bucket identifiers absent from the locally reconstructed case;
- any evaluation mode other than `compare_only`.

A CID or Git hash binds lineage. It does not make the source true.

## Codex evaluation extension

The upstream packet proposal remains human-readable and carries one bounded extension:

```json
{
  "proposal_id": "proposal:seeded-triangle-review",
  "summary": "Evaluate one locally reconstructed candidate.",
  "assumptions": ["The corpus is synthetic."],
  "local_tests": ["Run exact and Rust-backed checks."],
  "codex_evaluation": {
    "benchmark_id": "hybrid-benchmark:seeded-triangle-v0-1",
    "route_candidate_id": "triangle:c75caa8d3b0d0a5134bd",
    "allowed_provider_ids": [
      "flash-provider:seed-a",
      "flash-provider:seed-b"
    ],
    "allowed_bucket_ids": [
      "flash-bucket:usd-0500",
      "flash-bucket:usd-1000"
    ],
    "evaluation_mode": "compare_only",
    "authority": false
  }
}
```

The identifiers are hints only. Codex enumerates the candidate universe from the
local seeded case and rejects any identifier that cannot be reconstructed.

## Identical-QUBO law

The packet-guided route assignment is decoded on the same complete route QUBO used by
the local exact baseline. Its confidence receipt therefore exposes a meaningful
energy gap to the local exact solution.

The provider-and-bucket hint creates a bounded flash-liquidity subspace for the
selected route. The exact classical result and the packet-guided flash receipt use the
same locally reconstructed flash QUBO for that subspace.

No provider text can override either model score.

## Uplift interpretation

The experiment records deltas against the local-only baseline for:

- route QUBO energy gap;
- exact Rust route log delta;
- perturbation survival rate;
- worst-case log delta;
- exact Rust-verified net profit;
- repayment feasibility;
- candidate diversity.

The receipt classifies each packet-guided proposal as:

- `positive` — locally verified and adds a measured improvement or distinct verified
  candidate coverage;
- `neutral` — locally verified but does not outperform the baseline;
- `rejected` — fails one or more local verification membranes.

The overall result may be `positive`, `neutral`, or `no_verified_uplift`.

A zero or negative result is valid evidence. The benchmark is designed to discover
whether remote planning helps, not to manufacture a favorable conclusion.

## Seeded fixture

`examples/seeded_strategy_packet_v0_1.json` is a deterministic teaching fixture. It
binds to:

```text
SpiralBloom commit:
b64c3753fca90f869302dca45850256936d80e0f

CodexTradingEngine source commit:
17d0107ded1148a4b7d118d68068b1664400d3eb

Verified phone-node snapshot manifest:
bafkreifllgyxq2dluftpa5y6qtalomjonpe3tuwv5g2jnyd4luas52yvna
```

Its timestamps are intentionally fixed. Replay tests supply a fixed `--now`; normal
runtime validation rejects the fixture after expiry.

## CLI

After building the isolated Rust verifiers:

```bash
cargo build --manifest-path rust/delta-verifier/Cargo.toml --bins

python -m eve_q.strategy_packet_uplift \
  --packet examples/seeded_strategy_packet_v0_1.json \
  --case benchmarks/seeded_market_v0_1.json \
  --route-verifier rust/delta-verifier/target/debug/codex-delta-verifier \
  --flash-verifier rust/delta-verifier/target/debug/codex-flash-liquidity-verifier \
  --receipt-out artifacts/planning_uplift_receipt.json \
  --now 2026-07-11T03:00:00Z \
  --expected-manifest-cid bafkreifllgyxq2dluftpa5y6qtalomjonpe3tuwv5g2jnyd4luas52yvna \
  --expected-source-commit \
    ArchitectofAthena/spiralbloom-os=b64c3753fca90f869302dca45850256936d80e0f \
  --expected-source-commit \
    ArchitectofAthena/CodexTradingEngine=17d0107ded1148a4b7d118d68068b1664400d3eb
```

## CI

`Strategy Packet Uplift CI` runs:

- Python 3.11 and 3.13 contract tests;
- module compilation;
- JSON fixture and receipt-schema syntax validation;
- hash, TTL, authority, raw-response, candidate-ID, manifest, and commit rejection
  tests;
- a full replay through both compiled Rust verifier binaries;
- deterministic repeated receipt comparison;
- artifact upload for human inspection.

CI performs no remote provider call.

## Boundaries

- historical replay only;
- no live feed;
- no automatic provider call;
- no remote dependency on a time-critical path;
- no raw provider response storage;
- no wallet or signer;
- no RPC or mempool interaction;
- no borrowing or capital movement;
- no scheduler or deployment authority;
- no self-promotion;
- all packets, hints, models, evidence, comparisons, and receipts retain
  `authority: false`;
- human review remains the promotion gate.

## Design law

```text
Remote intelligence may widen the possibility space.
Local reconstruction decides what exists.
Exact comparison measures the cost of the hint.
Rust verifies arithmetic.
Perturbation tests durability.
A receipt records the experiment.
No result authorizes action.
```
