# Public Review Remediation v0.1

Captured after the repository became public on 2026-08-04.

## External findings accepted for repair

1. `eve_q/cross_repo_ingestor.py` reads `merkle_proo` instead of `merkle_proof`, allowing supplied proof data to bypass the intended validation path.
2. `eve_q/scroll_protocol.py` stores arbitrary Python implementations and invokes an `execute()` method, conflicting with the repository's non-execution boundary.
3. Packaging must include every documented package and declare runtime dependencies used by packaged modules.
4. Legacy Omega sentiment feeds need the same HTTPS, exact-host, redirect, response-size, and public-address posture as the newer read-only telemetry membrane.
5. The public surface needs one obvious install → simulate → verify → report path.

## Findings already resolved before this review

- `omega_telemetry` is included by the current setuptools package discovery.
- `.github/workflows/full-simulation-suite.yml` runs without path filters on every pull request and push to `main`.
- immutable GitHub Action pins and the Gate 1 container digest are already enforced.

## Repair posture

```text
repair the bypass
remove arbitrary execution registration
package the documented surface
harden legacy feed reads
add one canonical research command
run the unfiltered simulation-safe suite
```

No repair may add wallet access, signing, transaction construction, broadcast, live trading, autonomous promotion, or capital authority.

This document is a provenance receipt, not evidence that the repairs have passed. The associated pull request and workflow results are canonical for completion.
