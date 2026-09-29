# Omega perception threat model

Scope: passive observations, local persistence, and optional operator-configured
notifications. No orders, wallets, signing, broadcasting, capital movement, or
promotion authority. The context runner never enables notification delivery.

Baseline at `cbfdd1928ed51f60f31425a593bdae3fc641c94a`: 629 passed, 9 skipped,
66.00% overall branch-aware coverage; existing 56% gate retained. All supplied
Omega per-file percentages reproduced exactly. Pytest's configured `--cov=.` is
additive with the requested `--cov=omega_telemetry`.

| Input or surface | Failure being tested | Required behavior |
| --- | --- | --- |
| Keyword sentiment | Sarcasm, negation, hype, forged authors, coordinated wording treated as truth | Preserve a keyword observation with explicit low confidence and unverified authenticity; score is salience, not truth or direction |
| Sentiment bursts | Mirrored text, fresh IDs, one author/source, repeated ticker tokens, low samples | Count unique normalized content; expose single-source/author and coordination limits; retain threshold and cooldown |
| Source timestamps | Replayed old posts, future timestamps, missing/malformed publication times | Preserve low-confidence observations; exclude unknown or stale publication times from fresh burst counts |
| Feed transport | Redirects, private DNS/peers, changed DNS, oversized/malformed bodies | Retain existing bounded public-feed membrane; use offline transport fixtures |
| Price input | Non-finite/negative/zero/malformed prices; indefinitely cached price makes dust look large | Reject unusable values, expire local cache, reject stale price points in watcher; no stale fallback on fetch failure |
| Native quantities | Malformed record aborts a batch; one-wei threshold rounding | Isolate malformed records and use sufficient local Decimal precision |
| ERC-20 logs | Wrong event/contract/block, removed logs, missing identity, invalid quantities | Check response provenance and identity before valuing or persisting; retain per-log dedupe |
| Transfer interpretation | Self-transfers, exchange shuffles, round trips mistaken for trades/accumulation | Record transfer context and low-confidence directional inference; beneficial ownership remains unknown |
| RPC / checkpoint | Reply for another request, missing or wrong block silently advances cursor | Bind JSON-RPC version and ID; fail without advancing past missing data; allowlist remains read-only |
| Alerts | Duplicate events, threshold flapping, unique-ID floods, stale/future timestamps, injected mentions | Persistent cooldown, bounded notification rate, timestamp checks, explicit confidence display, Discord mention suppression |
| Runner / observer | Partial startup on invalid config, zero-delay loop, orphan tasks, heartbeat mistaken for fresh feed evidence | Validate before starting tasks, positive bounded intervals, clean cancellation, liveness-only health with freshness unverified |

Limits: lexical matching cannot establish truth, sarcasm, author identity, or
independence. Address labels cannot prove beneficial ownership or wash trading.
RPC observations are not independent chain consensus or proof of finality; native
transaction inclusion alone does not establish successful execution. A local
price retrieval time does not prove the upstream quote's publication time. These
limits must remain visible in event metadata and review, not become confidence
or execution authority.

Adversarial regression cases are named `test_adversarial_*` in
`tests/test_omega_perception_adversarial.py`. Normal-path and precision tests
complement those attacks; fixtures perform no external requests.
