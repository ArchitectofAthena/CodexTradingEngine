# CodexTradingEngine Sepolia Gate 1A Soak Campaign v0.1

## Purpose

This campaign measures whether the reviewed Gate 1A observation membrane preserves its boundaries across repetition.

It performs one explicitly approved, fixed-count campaign:

```text
Source: ethereum-sepolia-blockscout-stats-v0-1
Capture attempts: exactly 25
Spacing: exactly 12 seconds
Maximum rate: 5 requests per minute
Automatic recurrence: false
Stop on first failure: true
```

It is not a recurring monitor and does not widen source eligibility beyond issue #128.

## Run

```bash
export EVE_Q_GATE1_PILOT=1
unset EVE_Q_GATE1_KILL_SWITCH || true

codex-gate1-soak25 run \
  --source-spec registry/source_specs/ethereum_sepolia_blockscout_stats_v0_1.json \
  --producer-commit "$(git rev-parse HEAD)" \
  --output-dir artifacts/sepolia-soak-v0-1
```

The command refuses any count other than 25 and any interval other than 12 seconds.

## Per-capture procedure

Before every attempt:

1. require the explicit pilot flag;
2. check the kill switch;
3. scan for write-capable credential names;
4. verify the source review has not expired;
5. perform DNS/IP preflight and require public addresses.

For each accepted observation:

1. perform one public-IP-pinned HTTPS GET;
2. enforce the exact reviewed host and default TLS port;
3. cap time and response size;
4. normalize the response;
5. emit raw, normalized, snapshot, and resolution hashes;
6. require immediate freshness validation;
7. verify post-capture DNS resolution;
8. persist the complete immutable bundle.

Any failure records a rollback receipt and terminates the campaign. The runner does not silently retry.

## Final corpus replay

After capture attempts finish, the runner reopens every accepted bundle from disk and verifies:

- raw payload hash;
- normalized payload hash;
- artifact hash;
- source ID;
- exact host;
- GET method;
- source and producer provenance;
- resolution receipt;
- false authority fields.

Final replay does not require the earlier captures to remain within their 120-second freshness window. Freshness is verified at capture time; corpus replay verifies immutable integrity afterward.

## Summary artifacts

```text
artifacts/sepolia-soak-v0-1/
├── captures/
├── rollbacks/
├── records.jsonl
├── replay_records.json
├── summary.json
└── summary.txt
```

The summary records:

- requested, attempted, accepted, rejected, rollback, and replay counts;
- each accepted snapshot, raw, normalized, and resolution hash;
- observed timestamp range;
- source and registry identity;
- source review expiry;
- request cadence;
- deterministic ledger hashes;
- residual risks;
- zero proposal, signature, transaction, execution, and capital counts;
- authority false;
- a deterministic receipt hash.

Verify an existing summary:

```bash
codex-gate1-soak25 verify-summary \
  --summary artifacts/sepolia-soak-v0-1/summary.json
```

## PASS meaning

A PASS requires:

```text
captures requested: 25
captures attempted: 25
captures accepted: 25
captures rejected: 0
rollbacks: 0
corpus replayed: 25
all accepted snapshots replayed: true
unauthorized transitions: 0
```

PASS means the membrane kept its recorded shape for this one bounded campaign.

PASS does not mean:

- production reliability;
- independent source corroboration;
- production economics;
- recurring profitability;
- mainnet readiness;
- Gate 2 authority;
- transaction or execution readiness.

## HOLD meaning

The campaign returns HOLD when any attempt fails or the final corpus replay finds a mismatch.

Supported examples include:

- source outage;
- timeout;
- kill-switch activation;
- dangerous credential-name detection;
- source-review expiry;
- host or DNS drift;
- stale observation at capture time;
- raw, normalized, artifact, or replay mismatch;
- authority leakage.

The rollback receipt proves return to Gate 0 while later gates remain locked.

## Gate posture

```text
Gate 0: ACTIVE
Gate 1A: ACTIVE FOR THIS REVIEWED CAMPAIGN
Gate 1B: LOCKED
Gate 2: LOCKED
Gate 3: LOCKED
Gates 4–6: LOCKED
```

> Repetition may test the membrane. It may not teach the membrane to transact.
