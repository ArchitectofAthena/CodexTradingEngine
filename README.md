# CodexTradingEngine

**Simulation-first crypto telemetry and safety research engine for Termux/Python.**

CodexTradingEngine emits proposals, artifact receipts, risk reports, TTL evaluations, CID-backed carrier manifests, and charity allocation artifacts. It does **not** autonomously move capital.

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

## Status

This repository is an early-stage safety and telemetry research project.

It is not a live autonomous trading engine.
It is not a wallet.
It is not a transaction signer.
It is not financial advice.

Human review and explicit human promotion remain required for any real-world capital touchpoint.
