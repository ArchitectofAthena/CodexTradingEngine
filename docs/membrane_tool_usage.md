# Membrane Tool Usage

The membrane tool extracts a carrier manifest from PNG metadata and validates it against the artifact carrier law.

It is intentionally read-only.

## Safety Boundary

- extract only
- parse only
- validate only
- no metadata writing
- no IPFS daemon dependency
- no network access
- no wallet access
- no scheduler
- no capital movement

## Validate A Membrane Image

```bash
python -m eve_q.membrane_tool \
  --image ~/spiral_membrane_sealed.png
```

Expected shape:

```json
{"valid": true, "errors": []}
```

The actual output also includes the extracted manifest and metadata field name.

## Extract Manifest Only

```bash
python -m eve_q.membrane_tool \
  --image ~/spiral_membrane_sealed.png \
  --manifest-only
```

This prints only the JSON manifest embedded in the PNG Comment metadata field.

## Validate A Carrier Manifest Directly

```bash
python -m eve_q.artifact_carrier \
  --manifest examples/artifact_carrier_manifest.example.json
```

## Validate Receipt-To-Carrier Attestation

```bash
python -m eve_q.receipt_carrier_attestation \
  --carrier examples/artifact_carrier_manifest.example.json \
  --attestation examples/receipt_carrier_attestation.example.json
```

## The Self-CID Trap

An IPFS CID is derived from the full file contents.

That means an image cannot safely contain its own final CID inside its own metadata.

If the final CID is embedded back into the image, the image bytes change, which changes the CID again.

Therefore the safe pattern is:

```text
image metadata -> carrier manifest
carrier manifest -> payload CID or receipt CID
receipt attestation -> carrier manifest hash and carrier CID
```

The embedded manifest should point to a payload, receipt, or encrypted spore pointer.

It should not try to self-seal the image by containing the image's own final CID.

## Law

```text
The image carries the acorn.
The extractor reads.
The validator judges.
The operator remembers the self-CID trap.
The artifact still does not command.
```
