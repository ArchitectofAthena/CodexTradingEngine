# Constitutional Membrane Checkpoint

This checkpoint records the current artifact membrane created across PR #20 through PR #33.

The membrane is a validation and review layer. It does not execute commands, move capital, sign wallets, schedule actions, or publish content.

## Sealed Surface Stack

| PR | Surface | Meaning |
| --- | --- | --- |
| #20 | Artifact carrier validator | Validates CID-backed carrier manifests without execution authority. |
| #21 | Public README safety posture | Aligns public language with simulation-first safety boundaries. |
| #22 | Artifact carrier example | Provides a deterministic teaching manifest. |
| #23 | Artifact carrier CI guardianship | Ensures example surfaces trigger CI. |
| #24 | Receipt carrier attestation validator | Binds receipt identifiers to carrier manifest digests and CIDs. |
| #25 | Receipt carrier attestation example | Provides a deterministic attestation example. |
| #26 | README constitutional surface index | Names the active constitutional surfaces. |
| #27 | Receipt carrier attestation CLI | Validates carrier-attestation bindings from shell. |
| #28 | Artifact carrier manifest CLI | Validates carrier manifests from shell. |
| #29 | Membrane metadata extractor | Extracts carrier manifests from PNG Comment metadata and validates them. |
| #30 | README membrane tool index | Names the membrane extractor publicly. |
| #31 | Membrane tool usage docs | Teaches operator usage and the self-CID trap. |
| #32 | Membrane attestation bridge | Validates extracted image-carried manifests against receipt attestations. |
| #33 | README membrane bridge index | Names the bridge in the public map. |

## Current Verified Chain

```text
image metadata
-> carrier manifest
-> carrier law validation
-> receipt attestation validation
-> combined CLI result
-> human review
```

## Live Smoke-Test Commands

```bash
python -m eve_q.artifact_carrier \
  --manifest examples/artifact_carrier_manifest.example.json

python -m eve_q.receipt_carrier_attestation \
  --carrier examples/artifact_carrier_manifest.example.json \
  --attestation examples/receipt_carrier_attestation.example.json

python -m eve_q.membrane_tool \
  --image ~/spiral_membrane_sealed.png \
  --attestation examples/receipt_carrier_attestation.example.json
```

Expected result: all commands report `valid: true`.

## Self-CID Trap

An IPFS CID is derived from the full file contents.

An image cannot safely contain its own final CID inside its own metadata because embedding the CID changes the image bytes, which changes the CID again.

Safe pattern:

```text
image metadata -> carrier manifest
carrier manifest -> payload CID or receipt CID
receipt attestation -> carrier manifest hash and carrier CID
```

The embedded manifest should point to a payload, receipt, or encrypted spore pointer. It should not try to self-seal the image by containing the image's own final CID.

## Explicit Non-Authority Boundary

- no autonomous capital movement
- no wallet signing
- no scheduler authority
- no reverse execution channel
- no metadata writing
- no IPFS daemon dependency
- no network access
- no shell execution from metadata
- no subprocess execution from metadata
- no command execution from metadata

## Checkpoint Law

```text
The bridge is built.
The map is guarded.
The checkpoint remembers what changed.
The artifact still does not command.
```
