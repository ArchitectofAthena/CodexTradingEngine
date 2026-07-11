# EVE_Q++ Live Read-Only Telemetry Membrane v0.1

## Purpose

This pilot gathers content-addressed live observations while preserving Gate 0 as the active operating gate.

```text
Gate 0 SIMULATION_ONLY: ACTIVE
Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT_ONLY
Gate 2–6: LOCKED
```

A pilot snapshot is evidence. It is not a proposal, command, promotion, execution receipt, or capital authorization.

## Transport boundary

The membrane accepts only:

- HTTPS;
- `GET` and `HEAD`;
- exact allowlisted hosts;
- bounded timeouts;
- bounded response sizes;
- UTF-8 JSON, `+json`, or UTF-8 `text/plain` payloads;
- redirects whose final destination remains HTTPS and exactly allowlisted.

It rejects:

- HTTP;
- embedded URL credentials;
- `POST`, `PUT`, `PATCH`, `DELETE`, and other write methods;
- non-allowlisted hosts;
- redirects outside the allowlist;
- malformed JSON or text;
- unsupported content types;
- oversized payloads;
- stale replay when freshness is required;
- raw or normalized hash mismatch;
- write-capable secrets detected by targeted environment-name preflight;
- any authority, proposal-generation, execution, or capital leakage.

## Explicit pilot enable and rollback

Network capture requires:

```bash
export EVE_Q_GATE1_PILOT=1
```

The kill switch overrides pilot enablement:

```bash
export EVE_Q_GATE1_KILL_SWITCH=1
```

With the kill switch active, capture fails closed and the system remains at Gate 0.

The preflight reports only dangerous environment variable names, never values.

## Snapshot bundle

Each capture produces:

```text
snapshot.json
raw.bin
normalized.json
```

`snapshot.json` records:

- source ID, kind, requested URI, final URI, method, and allowlisted host;
- retrieval, observation, expiry, HTTP status, content type, and content length;
- raw-byte and normalized-payload SHA-256 hashes;
- normalization format and parser version;
- producer repository and exact commit;
- Gate 0 active, Gate 1 pilot-only, and Gates 2–6 locked;
- explicit non-command and non-authority posture.

JSON normalization uses canonical UTF-8 JSON with sorted keys and compact separators. Text normalization converts CRLF and CR line endings to LF.

## Source specification

Copy the template:

```bash
cp \
  examples/telemetry/source_spec_template_v0_1.json \
  /tmp/eve-q-read-only-source.json
```

Edit it so `url` is a read-only HTTPS endpoint and `allowed_hosts` contains the exact hostname.

## Capture

```bash
set -euo pipefail

cd "$HOME/CodexTradingEngine"

export EVE_Q_GATE1_PILOT=1
unset EVE_Q_GATE1_KILL_SWITCH || true

RUN_ID="gate1-pilot-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$HOME/spiralbloom-runs/$RUN_ID"

python -m eve_q.live_read_only_telemetry \
  --capture /tmp/eve-q-read-only-source.json \
  --output-dir "$OUT" \
  --producer-commit "$(git rev-parse HEAD)"
```

No API credential is required for public feeds. Any credential used in a future pilot must be demonstrably read-only and named accordingly.

## Offline replay

```bash
python -m eve_q.live_read_only_telemetry \
  --replay "$OUT"
```

Require current freshness:

```bash
python -m eve_q.live_read_only_telemetry \
  --replay "$OUT" \
  --require-fresh
```

## Pilot law

Live snapshots may be inspected, replayed, and audited. They may not be supplied to live proposal generation in this release.

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false
}
```

> Observation enters first. Authority does not hitchhike on the data.
