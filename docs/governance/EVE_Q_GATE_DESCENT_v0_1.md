# EVE_Q++ Gate Descent v0.1

## Purpose

EVE_Q++ is not intended to remain permanently sealed at simulation-only capability. It is intended to earn capability through staged, reversible, evidence-backed gate descent.

The law is:

```text
lower one gate
→ keep every downstream gate closed
→ observe
→ perturb
→ audit
→ prove rollback
→ earn the next gate
```

Passing one gate never grants authority at another gate.

## Capability ladder

| Gate | Name | Meaning |
|---:|---|---|
| 0 | `SIMULATION_ONLY` | Deterministic simulation, proposals, evidence, registry, receipts; no live authority. |
| 1 | `LIVE_READ_ONLY_TELEMETRY` | Live observations may enter through read-only interfaces and become content-addressed snapshots. |
| 2 | `LIVE_PROPOSAL_GENERATION` | Live observations may inform non-command proposals for human review. |
| 3 | `TESTNET_MANUAL_EXTERNAL` | A human may perform a bounded external testnet action after explicit promotion. Artifacts still do not execute. |
| 4 | `CAPPED_MANUAL_EXTERNAL` | A human may perform a tightly capped live action outside the system after per-action promotion. |
| 5 | `EXECUTION_ASSISTANCE` | Future unsigned assistance, requiring a separate threat model and constitutional review. |
| 6 | `NARROW_AUTOMATION` | Future narrowly scoped automation, requiring a separate release contract. |

## v0.1 scope

This release encodes only the proposed transition:

```text
Gate 0: ACTIVE
Gate 1: REQUESTED
Gate 2–6: LOCKED
```

The controller does **not** lower Gate 1. It creates and validates a non-authoritative `GateDescentProposal` that can become eligible for human review only after its evidence requirements are satisfied.

## Required invariants

Every proposal must preserve:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_execute": false,
  "may_move_capital": false,
  "connector_mode": "read_only",
  "write_capable_secrets_present": false
}
```

The controller rejects:

- skipped gates;
- more than one requested gate;
- any downstream gate opened early;
- stale or inconsistent TTL;
- canonical artifact hash mismatch;
- write-capable connector mode;
- write-capable secrets;
- missing prohibited actions;
- premature promotion eligibility;
- a ready state with incomplete checks;
- a ready state without the required evidence classes;
- a ready state without a tested rollback to Gate 0;
- any authority, execution, or capital-movement leakage.

## Gate 1 evidence contract

`READY_FOR_HUMAN_REVIEW` requires all checks below to be true:

- adjacent gate only;
- all downstream gates locked;
- read-only interfaces only;
- zero write-capable secrets;
- live inputs content-addressed;
- replayable snapshots retained;
- stale-input rejection proven;
- malformed-input rejection proven;
- source-outage behavior proven;
- rollback to simulation proven;
- bounded live-read-only soak passed;
- no execution surface introduced.

It also requires content-addressed evidence for:

- the existing simulation baseline soak;
- a new live-read-only telemetry soak;
- a rollback test;
- a threat model.

A ready proposal is still only eligible for **human review**. It remains non-command and non-executing.

## CLI

Create a draft:

```bash
python -m eve_q.gate_descent \
  --write-draft artifacts/governance/gate_descent_g0_to_g1.json \
  --created-at 2026-07-11T21:00:00Z \
  --expires-at 2026-07-12T21:00:00Z
```

Validate a proposal:

```bash
python -m eve_q.gate_descent \
  --validate artifacts/governance/gate_descent_g0_to_g1.json \
  --now 2026-07-11T21:05:00Z
```

## Current posture

Gate 0 remains active. Gate 1 is a requested future capability, not an enabled one.

> The gate opens because evidence and rollback have earned it, not because the previous gate succeeded.
