# EVE_Q++ Gate 1 Bounded Soak Scaffold v0.1

## Purpose

This slice implements the non-live orchestration required between an approved source-review artifact and the later reviewed live campaign.

```text
Gate1SourceReviewArtifact [ELIGIBLE]
→ Gate1BoundedSoakPlan
→ per-capture pilot and kill-switch check
→ injected capture adapter
→ snapshot and DNS-resolution receipt replay
→ bounded capture ledger
→ rollback payload on first failure
→ Gate1BoundedSoakSummary
→ human review
```

No source is selected or committed here. CI uses only synthetic adapters and performs no network calls.

## Dependency order

```text
#77 source-review contract
→ #78 non-live soak scaffold
→ #76 reviewed bounded live campaign
→ #68 Gate 1 evidence decision
```

## Reviewed-source gate

A soak plan can be built only when the supplied `Gate1SourceReviewArtifact`:

- passes semantic validation;
- has a valid canonical artifact identity;
- declares `observation_eligibility: ELIGIBLE`;
- preserves Gate 0 active, Gate 1 pilot-only, and Gates 2–6 locked;
- grants no proposal, execution, capital, or activation authority.

`HOLD` and `REJECT` reviews fail before a plan exists.

## Bounded plan

A valid plan records:

- exact source-review artifact ID;
- reviewed source identity, endpoint, host allowlist, and method;
- exact producer commit;
- explicit start timestamp;
- capture count from 1 through 1,000;
- interval from 0 through 86,400 seconds;
- stop-on-first-failure behavior;
- kill-switch check before every attempted capture;
- `ADAPTER_INJECTED` network mode.

The scaffold does not contain a live transport adapter. Issue #76 must supply a separately reviewed adapter and real source artifact.

## Per-capture law

Every iteration executes in this order:

```text
check EVE_Q_GATE1_KILL_SWITCH
→ confirm explicit pilot flag
→ invoke capture adapter
→ replay snapshot hashes and authority fields
→ validate resolution receipt
→ verify source and producer lineage
→ preserve exact normalized bytes
→ append content-addressed ledger record
```

The adapter is never called after the kill switch becomes active.

## Exact replay bytes

The scaffold stores normalized payload bytes as `normalized.bin` without stripping trailing line feeds. This avoids changing valid payload bytes during replay. The source snapshot still carries the canonical normalized SHA-256.

## Failure and rollback

The first failed capture stops the campaign and writes the complete `Gate1RollbackReceipt` payload under:

```text
rollbacks/<capture-index>.json
```

The runner verifies that every declared rollback has a corresponding valid payload. A rollback artifact ID without its payload is insufficient evidence.

Supported mappings are:

- kill switch → `kill_switch`;
- telemetry boundary failure → `source_outage`;
- DNS hardening failure → `dns_policy_failure`;
- orchestration or replay failure → `operator_abort`.

Every rollback returns only to `SIMULATION_ONLY`.

## Run envelope

A scaffold run contains:

```text
plan.json
source_review.json
captures.jsonl
summary.json
captures/
  0000/
    snapshot.json
    raw.bin
    normalized.bin
    resolution_receipt.json
rollbacks/
  <capture-index>.json
```

The summary records requested, attempted, accepted, and rolled-back capture counts; ledger SHA-256; authority posture; and whether all requested captures completed.

## Non-live testing

The focused test suite runs a deterministic 25-capture synthetic campaign twice and requires byte-identical ledgers and summaries. It also proves:

- a `HOLD` review cannot produce a plan;
- capture count and interval bounds fail closed;
- kill switch is checked before adapter invocation;
- a tampered snapshot stops the campaign;
- complete rollback payloads are persisted and validated;
- exact normalized trailing bytes survive storage;
- rehashing cannot hide authority escalation.

## Boundary

```text
source eligibility != live source selection
soak plan != network permission
synthetic capture adapter != reviewed live transport
accepted observation != proposal
successful soak != Gate 1 activation
rollback receipt != command
confidence != authority
```

Every artifact remains:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_activate_gate_1": false,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false
}
```

> Build the runway controls before selecting the aircraft.
