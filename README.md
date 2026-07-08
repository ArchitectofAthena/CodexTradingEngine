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

<!-- constitutional-surfaces-index:start -->

## Constitutional Surfaces Index

CodexTradingEngine is simulation-first and safety-gated. These surfaces define the current artifact membrane:

| Surface | File | Purpose |
| --- | --- | --- |
| Artifact carrier validator | `eve_q/artifact_carrier.py` | Validates CID-backed carrier manifests without granting execution authority. |
| Artifact carrier example | `examples/artifact_carrier_manifest.example.json` | Provides a deterministic teaching artifact for safe carrier manifests. |
| Artifact carrier example docs | `docs/artifact_carrier_manifest_example.md` | Documents the carrier law: the artifact carries memory, not authority. |
| Receipt carrier attestation validator | `eve_q/receipt_carrier_attestation.py` | Binds a receipt identifier to a carrier manifest digest and CID as a review artifact. |
| Receipt carrier attestation example | `examples/receipt_carrier_attestation.example.json` | Demonstrates safe receipt-to-carrier attestation. |
| Receipt carrier attestation docs | `docs/receipt_carrier_attestation_example.md` | Documents attestation drift detection and non-execution boundaries. |
| Membrane metadata extractor and attestation bridge | `eve_q/membrane_tool.py` | Extracts carrier manifests from PNG Comment metadata, validates carrier law, and can compare receipt attestations without execution authority. |


Membrane bridge:

`python -m eve_q.membrane_tool --image <png> --attestation <attestation.json>`

Chain:

`image metadata -> carrier manifest -> receipt attestation -> validation result`
Current law:

```text
Image carries acorn.
The validator compares.
The attestation binds.
The image carries.
Receipt remembers.
Carrier points.
Hash detects drift.
TTL expires.
CI guards.
Human promotes.
```

Safety boundary:

- no autonomous capital movement
- no wallet signing
- no scheduler authority
- no reverse execution channel
- no IPFS daemon dependency for validation
- no image metadata dependency for validation
- no metadata writing

<!-- constitutional-surfaces-index:end -->
