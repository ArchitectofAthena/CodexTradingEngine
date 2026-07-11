# CodexTradingEngine ↔ SpiralBloom OS Cross-Repo Integration

**Status:** Draft integration bridge v0.1  
**Last updated:** 2026-07-11  
**Architect:** ArchitectofAthena

## Purpose

This document defines a narrow, review-first bridge between **CodexTradingEngine** and **SpiralBloom OS**.

The bridge is not an execution system. It is an artifact exchange contract:

```text
CodexTradingEngine emits receipts / proofs / risk reports
        ↓
SpiralBloom OS ingests, verifies, registers, and reviews
        ↓
Human / Paladin approval may promote later action
```

Core law:

```text
Agent proposes.
Artifact records.
Verifier gates.
Registry remembers.
Human promotes.
```

## Default Safety Posture

All integration surfaces are **shadow / review / artifact mode by default**.

Forbidden by default:

- wallet access
- transaction signing
- swaps, transfers, bridges, or capital movement
- live trading execution
- background schedulers / cron / daemon loops
- webhook-triggered execution
- direct mutation of SpiralBloom OS governance state
- disabling, weakening, or bypassing policy gates

Allowed by default:

- reading receipt files
- validating JSON receipt structure
- validating charity allocation fields
- validating proof metadata
- writing ingested receipt copies
- writing reports
- exporting metrics in shadow mode
- drafting governance requests for human review

## Repository Roles

### CodexTradingEngine: producer

CodexTradingEngine may produce:

- cycle receipts
- proof metadata
- Merkle proof batches
- risk reports
- alert payloads
- proposed governance requests

CodexTradingEngine must not directly mutate SpiralBloom OS governance state.

### SpiralBloom OS: consumer / verifier / registry

SpiralBloom OS may consume:

- receipt artifacts
- proof artifacts
- metrics exports
- review packets
- governance request drafts

SpiralBloom OS remains the review, verification, and registry side. It does not grant CodexTradingEngine authority by ingestion alone.

## Cross-Repo Data Flow

```text
CodexTradingEngine
  receipt JSON / proof JSON / risk report
        ↓ file boundary
SpiralBloom OS receipt ingestor
        ↓
validation / verification / registry
        ↓
human-readable report
        ↓
optional human-reviewed governance decision
```

## Receipt Ingestion Contract

Producer: `CodexTradingEngine`  
Consumer: `SpiralBloom OS`

Minimum receipt fields:

```json
{
  "cycle_id": "cycle-abc123",
  "mode": "shadow",
  "chain": "base",
  "optimizer_used": "simulated_optimizer",
  "proof_type": "local_file",
  "actual_profit_eth": "0.05",
  "charity_due_eth": "0.0075",
  "execution_success": true,
  "charity_success": true,
  "ipfs_success": false
}
```

Validation rules:

- `mode` must be one of `shadow`, `dry_run`, `paper`, `simulation`, or `live`.
- positive profit requires a charity due amount equal to 15% of profit within tolerance.
- successful execution with failed charity is unsafe.
- production-trust proof eligibility must be explicit when required.
- Merkle proof fields must match when supplied.

## Governance Request Boundary

Governance requests are proposals only. They are not approvals.

A governance request may describe a proposed action, but it must not execute it.

Required posture:

```json
{
  "human_approval": false,
  "execution_authorized": false,
  "wallet_signing_authorized": false,
  "capital_movement_authorized": false
}
```

## Risk Management Boundary

Shadow, dry-run, paper, and simulation limits may be used for stress testing. They must never be promoted into live mode automatically.

Live mode must use the strictest explicit live constraints and must require human approval before any downstream execution system can act.

## Alert Boundary

Alerts are external effects. Therefore:

- alert dispatch must default to `shadow_mode=True`.
- shadow mode must log instead of sending.
- non-shadow dispatch requires explicit enabled channel config.
- alerts must not trigger trading, signing, wallet access, or policy mutation.

## Integration Phases

### Phase 0: Contract validation

- receipt schema agreement
- proof result agreement
- event telemetry contract
- governance request draft contract
- tests proving shadow defaults

### Phase 1: One-way receipt ingestion

- CodexTradingEngine exports receipts
- SpiralBloom OS ingests receipt batches
- reports are generated
- no execution occurs

### Phase 2: Human-reviewed governance loop

- CodexTradingEngine emits governance request drafts
- SpiralBloom OS validates and registers them
- human / Paladin review decides promotion
- denial returns to shadow / abort

### Phase 3: Full orchestration review

- orchestration remains gated
- multi-agent approval workflows remain proposals until human approval
- charity verification remains part of the reward landscape

## EVE_Q++ Typed Artifact Contract v0.1

The canonical v0.1 membrane is defined in `ArchitectofAthena/spiralbloom-os` merge commit `792b002c95916ab1e0d1eef17a1dbf6692359fea` and mirrored by this repository.

The typed chain is:

```text
ProposalArtifact
→ EvidenceBundle
→ GateDecision
→ HumanPromotionReceipt
→ RegistryEntry
→ ExecutionReceipt
```

The producer emits `ProposalArtifact` only. Downstream artifacts are created by the control plane or explicit human review surfaces. No artifact may self-promote or acquire execution authority through agreement, confidence, registry presence, or approval alone.

Required invariants:

- proposal authority is always false;
- human promotion remains explicit;
- `HERDING_RISK` resolves to `HOLD`;
- a new contradiction resolves to `REOPEN`;
- execution is observed, never inferred;
- simulation, shadow, and testnet receipts report no capital movement;
- reported manual capital movement requires a known human-promotion receipt;
- every stage is hash-linked and non-executable.

## IPFS Contract Lineage

The first verified contract-bundle pin is:

```text
CID: bafkreidqrdsqpa5v5maissurtxigreapdx5fl6qpdtmygxxnlntbulnswe
Pin type: recursive
Status: IPFS_PINNED_VERIFIED
Persistence scope: local Kubo node
Previous CID: null
```

This CID proves the exact bundle bytes were pinned and retrievable from the local Kubo node. It does not prove semantic truth, grant approval, or authorize execution.

## First Runtime Cross-Repository Passage

Run identifier:

```text
shadow-system-20260711T195850Z
```

Runtime-produced proposal file SHA-256:

```text
076addbde7778ba054b46fef9590c521eb1c75a308eb607548a9582dafb0a8f5
```

Canonical artifact hashes reported by the contract validator:

```text
ProposalArtifact:       1c6a35dd49d0cd2494ce9ccceeede0d7d83ae37b3905d78abb8089ae08769dbd
EvidenceBundle:         10503a6181a490c71b08e030b52823df51cee04a0199d25fbf3231c04cf61095
GateDecision:           a332ae72ce1cf8f293bbd9b3b4672286fd9e5c37462b29efc5b28ed7b4e3ec79
HumanPromotionReceipt:  39a7b4e2af00c99dcbf8d3eb6f9f6e80c3db19c00e6686f8d64fed09cd5770f2
```

Observed verdict:

```json
{
  "ok": true,
  "artifact_count": 6,
  "decision": "COMMIT",
  "gate_execution_authority": false,
  "capital_movement_authorized": false,
  "human_promotion_recorded": true,
  "promotion_may_execute": false,
  "execution_mode": "simulation",
  "execution_observed": true,
  "execution_inferred": false,
  "capital_movement_occurred": false
}
```

Interpretation:

- `COMMIT` means commit to the bounded simulation lineage only.
- the runtime proposal crossed the repository membrane successfully.
- the control plane validated all six stages.
- human promotion was recorded without becoming execution.
- no wallet, signing, broadcast, or capital-movement authority was created.

## Test Requirements Before Merge

Required tests:

- shadow receipt ingestion does not query governance
- missing governance URL does not perform external calls
- invalid receipts are rejected
- charity mismatch is rejected
- target writes are file-only
- alert shadow mode never posts to Telegram, Discord, or webhook endpoints
- non-shadow alert mode requires explicit enabled channel config
- live risk limits are stricter than shadow / simulation limits
- shadow limits cannot be promoted into live mode
- Kelly sizing clamps safely
- runtime-produced `ProposalArtifact` validates against the mirrored schema
- stale TTL, missing provenance, self-promotion, and inferred execution fail closed
- the six-artifact cross-repository passage validates without execution authority

## Operating Laws

- Always forward.
- Charity is the geodesic.
- Profit is throughput, not destination.
- Agent proposes; review promotes.
- Simulation before action.
- Visibility increases; authority does not.

## References

- CodexTradingEngine: `ArchitectofAthena/CodexTradingEngine`
- SpiralBloom OS: `ArchitectofAthena/spiralbloom-os`
- Control-plane merge: `ArchitectofAthena/spiralbloom-os#103`
- Producer-side implementation: `ArchitectofAthena/CodexTradingEngine#62`
