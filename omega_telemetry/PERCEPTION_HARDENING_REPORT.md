# Omega perception hardening validation

Date: 2026-09-28. Base: `cbfdd1928ed51f60f31425a593bdae3fc641c94a`.
Branch: `test/omega-perception-hardening-2026-09-28`.

## Result

Baseline reproduced exactly: **629 passed, 9 skipped, 66.00% overall coverage**.
Every supplied Omega percentage matched current main. Final full suite:
**824 passed, 9 skipped, 69.80% overall coverage** (+3.80 percentage points).
The existing **56% coverage gate remains unchanged and passes**.

Omega aggregate branch-aware coverage increased from **45.00% to 99.46%**
(+54.46 percentage points; 464/1031 to 1282/1289 covered statements and branches).
These are coverage measurements, not estimates of adversarial robustness.

Added 195 test cases, including 77 named `test_adversarial_*`. Before production
changes, the initial 53 adversarial cases yielded **51 failures and 2 passes**;
the original suite remained green (631 passed total, 9 skipped). All final cases
pass without xfail, new skips, lowered thresholds, or coverage exclusions.

| File | Before | After | Change |
| --- | ---: | ---: | ---: |
| `__init__.py` | 100.00% | 100.00% | +0.00 pp |
| `alert_module.py` | 0.00% | 100.00% | +100.00 pp |
| `config_loader.py` | 0.00% | 100.00% | +100.00 pp |
| `config_tools.py` | 38.46% | 100.00% | +61.54 pp |
| `context_runner.py` | 0.00% | 98.28% | +98.28 pp |
| `db.py` | 84.21% | 100.00% | +15.79 pp |
| `health.py` | 66.67% | 100.00% | +33.33 pp |
| `models.py` | 98.04% | 100.00% | +1.96 pp |
| `pricing.py` | 25.00% | 100.00% | +75.00 pp |
| `sentiment_tracker.py` | 57.78% | 99.32% | +41.54 pp |
| `signal_observer.py` | 0.00% | 100.00% | +100.00 pp |
| `whale_watcher.py` | 46.61% | 99.39% | +52.78 pp |

## Behavior changes

- Keyword matches retain their salience score and carry low confidence,
  authenticity limits, publication time, and explicit non-authority metadata.
  Bursts count unique normalized content, exclude stale/unknown publication
  times, preserve cooldown, and expose single-source/author and coordination limits.
- Price values must be positive finite Decimals. Local cache expires after 60
  seconds; failures never fall back to expired quotes. Watchers reject stale,
  invalid, future, or wrong-symbol price points. JSON decimal parsing and local
  arithmetic precision preserve one-wei and token-unit threshold distinctions.
- ERC-20 observations validate event signature, address topics, requested
  contract/block, removal status, quantities, transaction hash and log index.
  Per-log dedupe is preserved. Malformed individual records do not hide valid
  following records. Invalid block/log envelopes cannot advance the cursor.
- RPC replies must match the request ID and JSON-RPC version, with redirects
  disabled. The read-only method allowlist remains unchanged.
- Transfers explicitly retain unknown directional meaning and beneficial
  ownership. Self-transfers and exchange shuffles are flagged. Native execution
  success, block freshness and finality remain unverified.
- Alerts retain shadow mode by default. Delivery history enforces a 10-minute
  dedupe cooldown and a default 20-event/60-second budget; stale/future events
  are suppressed. Successful distinct events count once across channels.
  Calls to one dispatcher are serialized; history survives restart. Discord
  mentions are disabled and remote response bodies/exception URLs are no longer
  copied into the delivery audit.
- Config roots and timing bounds fail explicitly. Runner construction completes
  before workers start; cancellation/failure cleans up sibling tasks. Health
  reports liveness with feed freshness unverified. Signal ticks explicitly
  record liveness only and no market evidence.

## Verification

The baseline and final runs used Python 3.12.14, pytest 9.1.1, pytest-cov 7.1.0,
coverage 7.16.2 and repository-declared runtime dependencies. The final command
was equivalent to:

```bash
python -m pytest --cov=omega_telemetry --cov-report=term-missing \
  --cov-report=json:/tmp/omega-final.json \
  --cov-report=html:/tmp/omega-final-html --junitxml=/tmp/omega-final-junit.xml
```

The repository's configured `--cov=.` remains additive: the same full-suite run
measures overall coverage and every Omega file with branch coverage enabled.
No pytest or coverage configuration was changed. The unchanged 9 skips cover
7 Rust-binary integration cases, 1 cross-repository soak and 1 opt-in Kubo test;
the required binaries/external environment were not supplied or enabled.

Ruff, Black check and `git diff --check` pass for the changed source/test scope.
Strict mypy found a source variable-type collision which was corrected. A clean
strict mypy result remains blocked by the existing untyped YAML/feedparser
imports; no ignore, exclusion, or dependency-file change was introduced to hide
that limitation.

Only `omega_telemetry/` and the five new Omega test/helper files are changed.
No capital gate, workflow, dependency manifest, signing, wallet, transaction,
execution, or deployment code changed. Nothing was merged or deployed.
The observation runner cannot activate notification channels or capital actions.

## Review limits

A lexical matcher cannot verify truth, sarcasm, author identity or independent
sources. Exact content deduplication does not detect coordinated paraphrases.
Missing publication times now prevent burst participation; adapters should retain
reviewed publication metadata. Local quote retrieval freshness cannot certify
upstream quote freshness. Transfers cannot prove purchases, beneficial ownership,
wash trading, native transaction success, finality or fresh chain state. Those
inferences stay low-confidence and non-authoritative.

The notification budget is for successfully recorded deliveries and assumes one
active dispatcher per database; it is not a distributed atomic rate limiter or
an upstream request retry budget. Notification channels were exercised only
through offline mocks. The remaining uncovered paths are the CLI module guard,
an unreachable source-type fallback after constructor validation, an optional
absent-peer transport branch, and defensive direct-persistence rejection.

The actionable follow-up is reviewed source timestamp/provenance enrichment and
feed freshness monitoring, followed by independent-source corroboration. Human
review and promotion remain required; this proposal grants no execution authority.

## Evidence digests

These SHA-256 values identify the local run evidence used for this report.

- `omega-baseline.json`: `fef9cdf5b019c8ee3b9ce48c317c890fc7eb08f63bf25a4f995a20c8e285d7d8`
- `omega-red.log`: `34536c53761f0de4b1372206f490df4753d47a7431396883c251684d07aef494`
- `omega-final.json`: `0ec2a5ff09831808df5dfb058160e0f4dfb55299453177617f53891786cfdb0c`
- `omega-final-junit.xml`: `e4663abd0008c2bb08c679bc264b7e6fb92423ea698e72dab97f49393c4005fa`
