# Constitutional Release Audit

This audit records release readiness for the constitutional membrane layer.

It verifies that the current carrier, attestation, CLI, README, checkpoint, and membrane surfaces remain simulation-first, review-only, and non-executing.

## Audited Surface Stack

| Surface | File | Audit Meaning |
| --- | --- | --- |
| Artifact carrier validator | `eve_q/artifact_carrier.py` | Validates carrier manifests from Python and shell. |
| Artifact carrier example | `examples/artifact_carrier_manifest.example.json` | Deterministic teaching manifest. |
| Receipt carrier attestation validator | `eve_q/receipt_carrier_attestation.py` | Validates receipt-to-carrier bindings. |
| Receipt carrier attestation example | `examples/receipt_carrier_attestation.example.json` | Deterministic attestation example. |
| Membrane metadata extractor | `eve_q/membrane_tool.py` | Extracts image-carried manifests and validates them. |
| Membrane usage docs | `docs/membrane_tool_usage.md` | Teaches safe operator usage and the self-CID trap. |
| Constitutional checkpoint | `docs/constitutional_membrane_checkpoint.md` | Records PR #20 through PR #33 membrane history. |
| README surface index | `README.md` | Publicly names the active constitutional surfaces. |

## Release Smoke Commands

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

## Release Boundary

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

## Example Authority Requirements

The deterministic example artifacts must preserve:

- `execution_authority: none`
- `human_promotion_required: true`
- `reverse_execution_channel_opened: false`
- `ttl_mode: artifact_only`

## Self-CID Trap

An image cannot safely contain its own final CID inside its own metadata.

Embedding the CID changes the image bytes, which changes the CID again.

Safe pattern:

```text
image metadata -> carrier manifest
carrier manifest -> payload CID or receipt CID
receipt attestation -> carrier manifest hash and carrier CID
```

## Release Law

```text
The validators answer.
The CLIs report.
The docs remember.
The release audit seals the membrane.
The artifact still does not command.
```
