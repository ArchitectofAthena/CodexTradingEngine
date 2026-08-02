# EVE_Q++ Cross-Repository Snapshot Export v0.1

## Purpose

Export an already validated Gate 1 read-only telemetry snapshot bundle into the
exact handoff envelope accepted by SpiralBloom-OS.

```text
validated snapshot bundle
→ deterministic envelope
→ canonical envelope ID
→ SpiralBloom intake
```

The exporter does not capture data. It performs no network call and does not
change capability gates.

## Surfaces

```text
eve_q/cross_repo_snapshot_export.py
schemas/cross_repo_snapshot_envelope_v0_1.schema.json
tests/test_cross_repo_snapshot_export_v0_1.py
```

The schema is mirrored byte-for-byte from the SpiralBloom receiving contract.

## Exported identity

The envelope binds:

- exact Codex producer repository, component, and commit SHA;
- snapshot artifact ID and snapshot contract version;
- SHA-256 of canonical snapshot JSON;
- source ID and source kind;
- raw and normalized payload hashes;
- parser version;
- observation, capture, expiry, and TTL fields;
- Gate 0 active, Gate 1 pilot-only, Gates 2–6 locked;
- command, authority, proposal, execution, and capital permissions false.

The envelope ID is the SHA-256 of canonical JSON with `envelope_id` omitted.

## CLI

```bash
python -m eve_q.cross_repo_snapshot_export path/to/bundle
python -m eve_q.cross_repo_snapshot_export path/to/bundle \
  --output path/to/cross_repo_envelope.json
```

The source bundle must contain:

```text
snapshot.json
raw.bin
normalized.json
```

Offline replay validation runs before export. Hash mismatch, stale structure,
unsafe flags, parser drift, producer drift, or gate leakage produces `HOLD`.
Freshness expiry is evaluated by SpiralBloom at intake time, so historical
bundles may still be exported as identifiable evidence.

## Boundary

```text
export != capture
snapshot != proposal
telemetry != economic edge
compatibility != promotion
Gate 1 pilot != Gate 1 activation
```

No wallet, signing, order, transaction, broadcast, live proposal, execution,
or capital authority is introduced.
