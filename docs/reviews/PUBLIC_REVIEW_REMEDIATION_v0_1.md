# Public Review Remediation v0.1

Captured after the repository became public on 2026-08-04.

## External findings accepted for repair

1. `eve_q/cross_repo_ingestor.py` read `merkle_proo` instead of `merkle_proof`, allowing supplied proof data to bypass the intended validation path.
2. `eve_q/scroll_protocol.py` stored arbitrary Python implementations and invoked an `execute()` method, conflicting with the repository's non-execution boundary.
3. Packaging needed every documented package and every runtime dependency used by packaged modules.
4. Legacy Omega sentiment feeds needed the same HTTPS, exact-host, redirect, response-size, and public-address posture as the newer read-only telemetry membrane.
5. The public surface needed one obvious install → simulate → verify → report path.

## Findings already resolved before this review

- `omega_telemetry` was already included by setuptools package discovery.
- `.github/workflows/full-simulation-suite.yml` already ran without path filters on every pull request and push to `main`.
- immutable GitHub Action pins and the Gate 1 container digest were already enforced.

## Implemented repair map

### Receipt ingestion

- corrected the canonical field to `merkle_proof`;
- rejects the legacy misspelling instead of silently accepting it;
- rejects partial proof envelopes, root mismatches, malformed path/index pairs, and the legacy `skip_verification` sentinel;
- constrains receipt identifiers before forming target paths;
- rejects symlinks, non-files, and oversized receipts;
- restricts the optional governance callback to explicit loopback HTTP with redirects disabled;
- fails closed when a non-shadow governance query does not approve.

### Scroll protocol

- removed arbitrary implementation registration;
- removed callable strategy execution and composite `execute()` behavior;
- admits immutable JSON-compatible rules only;
- rejects execution, wallet, signing, broadcast, transaction, and capital capability keys;
- emits proposal artifacts with locked authority fields;
- preserves versioning, validation, deprecation, compatibility, and composition as declarative operations.

### Packaging and public path

- packages `eve_q`, `omega_telemetry`, and `models`;
- packages required root modules used by the shadow research path;
- declares `jsonschema` and `pydantic` as runtime dependencies;
- adds `codex-research` as the canonical simulation-safe CLI;
- adds `QUICKSTART.md` and a local candidate-route fixture;
- builds a wheel and smoke-tests imports plus the CLI in a clean virtual environment on Python 3.11 and 3.13.

### Omega feed membrane

- requires HTTPS and exact-host allowlisting;
- rejects embedded credentials and non-public IP literals;
- applies timeout and body-size bounds;
- disables redirects;
- performs public-address DNS preflight and postflight checks;
- rejects DNS drift and unexpected or non-public connected peers;
- keeps sentiment telemetry disabled by default.

## Repair posture

```text
repair the bypass
remove arbitrary execution registration
package the documented surface
harden legacy feed reads
add one canonical research command
run the unfiltered simulation-safe suite
```

No repair adds wallet access, signing, transaction construction, broadcast, live trading, autonomous promotion, or capital authority.

This document records intended and implemented changes. The associated pull request, diff, and workflow results remain canonical for completion.
