# EVE_Q++ Gate 1 Telemetry Threat Model Draft v0.1

## Scope

This draft covers the `LIVE_READ_ONLY_TELEMETRY` pilot membrane. It does not authorize Gate 1 activation and does not cover proposal generation or execution.

## Protected invariants

- Gate 0 remains active during the pilot.
- Gate 1 remains pilot-only until explicit human promotion.
- Gates 2–6 remain locked.
- Live observations cannot become commands.
- No wallet, signing, order, transaction, broadcast, or capital interface exists.
- Snapshot bytes, normalized payloads, provenance, and freshness are auditable.
- Rollback to simulation-only is immediate and testable.

## Threats and controls

| Threat | Control | Residual work |
|---|---|---|
| Write-capable transport | HTTPS `GET`/`HEAD` allowlist; all other methods rejected | Verify no imported SDK adds hidden write methods |
| Host confusion or SSRF | Exact hostname allowlist; HTTPS required; embedded credentials rejected | Add DNS/IP-class validation before live soak |
| Redirect escape | Redirect destination must remain exactly allowlisted | Test redirect chains and loops |
| Secret leakage | Targeted environment-name preflight reports names only | Expand provider-specific write-secret patterns as sources are selected |
| Oversized payload | Per-source hard byte cap | Add decompression-size accounting if compressed responses are enabled |
| Malformed payload | Strict UTF-8 JSON/text normalization | Add source-specific schema validation |
| Stale observations | Explicit retrieval time, expiry, TTL, and replay freshness check | Define per-source TTL policy |
| Byte tampering | Raw and normalized SHA-256 hashes plus canonical artifact ID | Bind bundles into an audit-root CID |
| Parser drift | Parser version recorded | Add migration and dual-parser comparison policy |
| Source outage | Fail closed; kill switch returns to Gate 0 | Run bounded outage campaign |
| Correlated misinformation | Source identity retained; agreement grants no authority | Add independence groups and contradiction analysis |
| Live-data authority leakage | `may_generate_live_proposal=false`, `may_execute=false`, `may_move_capital=false` | Add repository-wide no-import/no-call boundary tests |
| Accidental activation | Explicit `EVE_Q_GATE1_PILOT=1` required | Add operator checklist and signed human promotion receipt later |

## Known limitations

The first implementation is source-agnostic and uses exact host allowlisting. It does not yet validate resolved IP ranges, TLS certificate pinning, compressed-body expansion, source-specific JSON schemas, multi-source independence, or long-duration live availability.

These limitations must be addressed or explicitly accepted before a Gate 1 proposal becomes `READY_FOR_HUMAN_REVIEW`.

## Current verdict

```text
Gate 1 activation: NOT AUTHORIZED
Pilot code and synthetic boundary testing: ALLOWED
Live bounded observation campaign: PENDING HUMAN-SELECTED SOURCES
```
