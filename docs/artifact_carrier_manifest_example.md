# Artifact Carrier Manifest Example

This example demonstrates a safe CID-backed artifact carrier manifest.

The carrier manifest is a pointer. It is not a command, scheduler, wallet, execution request, or authority source.

## Carrier Law

```text
The image carries the acorn.
The CID points to the memory.
The key is consent.
The artifact never commands.
```

## Example Manifest

The canonical example lives at:

```text
examples/artifact_carrier_manifest.example.json
```

It demonstrates:

- a CID-backed encrypted continuity-spore pointer
- artifact-only TTL mode
- human-held key custody
- no execution authority
- no reverse execution channel
- no embedded secrets
- no wallet or command fields

## Interpretation

A carrier manifest may say where an encrypted payload lives. It must not say what must execute.

Safe chain:

```text
visible artifact
-> metadata pointer
-> CID
-> encrypted payload
-> human-held key
-> human review
```

Unsafe chain:

```text
artifact
-> command
-> execution
```

That unsafe chain is forbidden.

## Validation

The example is tested by:

```text
tests/test_artifact_carrier_example.py
```

The example teaches.
The validator verifies.
The artifact still does not command.
