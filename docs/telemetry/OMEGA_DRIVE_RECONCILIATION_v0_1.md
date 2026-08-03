# Omega Drive Reconciliation v0.1

## Purpose

Reconcile the archived Omega Telemetry Stack in Google Drive with the existing `omega_telemetry` package without replacing reviewed Codex behavior wholesale.

The archive is treated as source evidence, not automatic authority. The implementation remains operator-invoked, observation-only, and shadow-first.

## Source root

- Google Drive folder id: `1GOBE7dMJPZX4ffLiUWJmJYt56O-96sKp`
- Source role: archived crypto telemetry candidate
- Reviewed direct components: models, SQLite persistence, pricing, sentiment rules, whale watcher, alert adapter, health writer, configuration loader, and async runner

## Archived source fingerprints

These SHA-256 values were calculated from the retrieved Drive files before adaptation:

| File | Drive file id | SHA-256 |
| --- | --- | --- |
| `models.py` | `1SBseuUowLJDP5v2RpLHnTvy7gQ2vl5NG` | `9cbaa70cfdbc4be6c44fbde1be41c5cbbc95a42628b646801cb403218228d707` |
| `sentiment_tracker.py` | `1j0uioDQorwRED7qqC2Va5Ay47qVQaJ7a` | `aa00baa7c4eaed4190add750cf9ad7d6f3e70b0f8893ffbd6e0ebb5be43d5576` |
| `whale_watcher.py` | `1RqVmSlvR6rdqzthYaDJGsUbGek1zMxyg` | `16bacd7c3155344062782f7bf8503716e07908493509f416e38fca71dc30bebb` |
| `watch_main.py` | `1UMueLEiboz4Gk03mBUEEk3mM1J7YKKpu` | `60c7631bd6d54475a38e688376c2b0f8efcd2482a3b6d481c95b667a79dbe5a2` |
| `alert_module.py` | `1ZgEA59Mrb0kMfhwX3JFq9iqKSM27DsAa` | `acfbae52f1d671c2e4be84c14fd0f6aa9a92a91fc2c9c08ad01d4de307c11b6c` |
| `db.py` | `1rD0C5LzGSvOdZKnfhxa6K6J-dOSmgNxZ` | `ea2f51d3c7501a01c5f84e7ade3827d241a4eee19859e5b781311f0cd31cb166` |
| `pricing.py` | `11RCJkCQRgVa3Cbtqg2RoVvb3KdwcV6uw` | `d17620ab7554d2fdc4ba2e1c38b86e29fbc1c233ff6a29c8292b0a2384e36b05` |
| `config_loader.py` | `1SP6BU6PyClSdkvsCO1smepTqCMsMxRsy` | `792de3d4ae2c662ceaa270643c4a51c9d2e33e455984f2947895b4bb3a21484d` |
| `health.py` | `1aKxSc_dzs9W9mkys2TlxC858ysPWLjfP` | `d2ae20b330cd0c719415e3c836a11caee3af3fa3e014b89164e067f77fb2cc55` |

## Findings

The existing Codex package had already incorporated several archive components, but the integration was incomplete:

1. `sentiment_tracker.py` constructed archived `SentimentEvent` fields that current `models.py` no longer defined.
2. The tracker called a database method that did not exist in the current `TelemetryDB` API.
3. Some event summaries were constructed as mappings even though persistence expects text.
4. Python process-randomized `hash()` was used in a persistent dedupe key.
5. `whale_watcher.py` and the archived orchestration path were absent.
6. `omega_telemetry*` was excluded from installed package discovery.

## Reconciliation

This change:

- restores complete `SentimentEvent` and `WhaleEvent` contracts;
- preserves `ChainSignalEvent` compatibility;
- switches sentiment dedupe to stable SHA-256 identifiers;
- uses the real `TelemetryDB.is_duplicate` interface;
- restores a passive EVM whale watcher from the archive;
- restricts JSON-RPC to `eth_blockNumber`, `eth_getBlockByNumber`, and `eth_getLogs`;
- rejects non-HTTP RPC URLs and credential-bearing RPC URLs;
- bounds catch-up work with `max_blocks_per_poll`;
- integrates whale observation into the existing `context_runner` rather than adding a competing runner;
- adds `omega_telemetry*` to package discovery and exposes the `omega-context` command;
- leaves whale and sentiment sources disabled in the example configuration.

## Authority boundary

```json
{
  "authority": false,
  "shadow_mode": true,
  "may_execute": false,
  "may_execute_trades": false,
  "may_sign": false,
  "may_broadcast": false,
  "may_move_capital": false
}
```

No wallet adapter, private key, signer, order API, transaction constructor, transaction broadcaster, autonomous gate promotion, or capital path is introduced.

## Activation ladder

1. Unit tests and static audit.
2. Disabled installed-package smoke.
3. Fixture-backed local polling.
4. Operator-approved read-only RPC on testnet.
5. Bounded shadow observation with reviewed labels and thresholds.

Live alert dispatch and any execution layer remain outside this reconciliation.
