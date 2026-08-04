# EVE_Q++ Gate Descent v0.1

## Purpose

EVE_Q++ is not intended to remain permanently sealed at simulation-only capability. It is intended to earn capability through staged, reversible, evidence-backed gate descent.

The law is:

```text
lower one bounded gate
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
| 1A | `TESTNET_READ_ONLY_ALPHA` | Approved alpha testers may capture bounded public testnet observations, replay them offline, and translate them explicitly into local simulation fixtures. |
| 1B | `MAINNET_READ_ONLY_TELEMETRY` | Reviewed live mainnet observations may enter through read-only interfaces and become content-addressed snapshots. |
| 2 | `LIVE_PROPOSAL_GENERATION` | Live observations may inform non-command proposals for human review. |
| 3 | `TESTNET_MANUAL_EXTERNAL` | A human may perform a bounded external testnet action after explicit promotion. Artifacts still do not execute. |
| 4 | `CAPPED_MANUAL_EXTERNAL` | A human may perform a tightly capped live action outside the system after per-action promotion. |
| 5 | `EXECUTION_ASSISTANCE` | Future unsigned assistance, requiring a separate threat model and constitutional review. |
| 6 | `NARROW_AUTOMATION` | Future narrowly scoped automation, requiring a separate release contract. |

## Current posture

On 2026-08-04, the Architect explicitly promoted the scoped Gate 1A alpha lane tracked by issue #116.

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED PENDING #68 / #76
Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED
Gate 4–6: LOCKED
```

Gate 1A is not a substitute for the Gate 1B evidence campaign. It narrows the source domain to public testnets and keeps proposal generation, external action, and capital authority closed.

## Gate 1A invariants

Every accepted alpha run must preserve:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required_for_next_gate": true,
  "mainnet_allowed": false,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false,
  "testnet_read_only_alpha_allowed": true,
  "write_capable_secrets_present": false
}
```

Gate 1A rejects:

- mainnet sources;
- skipped gates;
- any downstream gate opened early;
- stale or inconsistent TTL;
- canonical artifact hash mismatch;
- write-capable connector mode;
- write-capable secrets or wallet material;
- missing prohibited actions;
- unsupported transport methods;
- private, loopback, link-local, reserved, or IP-literal source hosts;
- direct routing from live observation into proposal generation;
- any authority, execution, transaction, or capital-movement leakage.

## Gate 1A alpha evidence contract

A run counts toward the alpha evidence set only when:

- the exact producer commit is recorded;
- the non-live test suite passes first;
- the source is a public blockchain testnet source compatible with the read-only transport membrane;
- capture completes through the reviewed launcher;
- offline replay succeeds;
- DNS/IP-class postflight verification succeeds;
- the operator explicitly translates inspected observations into a local fixture;
- the research report preserves `EXECUTION=LOCKED`;
- one structured alpha report is filed without secrets or private data.

The alpha workflow is documented in:

```text
docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md
```

The human promotion decision is recorded in:

```text
docs/governance/EVE_Q_GATE1A_ALPHA_PROMOTION_v0_1.md
```

## Gate 1B evidence contract

Gate 1B remains locked. `READY_FOR_HUMAN_REVIEW` requires all checks below to be true:

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
- a live read-only telemetry soak;
- a rollback test;
- a threat model.

A ready proposal is still only eligible for human review. It remains non-command and non-executing.

## CLI for the original Gate 0 to Gate 1 proposal artifact

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

The v0.1 controller still validates the original Gate 0 to Gate 1 proposal object. The scoped Gate 1A decision is a human governance amendment and does not grant the controller self-promotion authority.

> The gate opens because its scope is explicit, its rollback is visible, and every larger capability remains separately locked.
