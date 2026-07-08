# TTL and Graceful Degradation Policy

Version: 0.1.0

## Purpose

This policy defines how authority expires inside CodexTradingEngine.

Codex may propose, simulate, validate, and emit artifacts. Authority to move into
higher-risk modes must be time-bounded, human-promoted, and reversible into safer
states.

Core law:

> Authority expires. Uncertainty degrades permission. Degradation reduces autonomy,
> confidence, and priority. It does not produce chaotic stop unless a hard boundary
> is crossed.

## Operating Principles

1. **TTL is not trust.** TTL is a temporary permission window.
2. **Expired TTL degrades authority.** It does not silently extend itself.
3. **Uncertainty shortens TTL.** Bad data, stale telemetry, drift, and failed
   validation reduce permission.
4. **Hard boundaries stop immediately.** Wallet signing, autonomous capital
   movement, reverse execution channels, webhook execution, scheduler execution,
   governance mutation, or self-promotion attempts are hard-stop events.
5. **Graceful degradation is preferred.** When uncertainty rises without a hard
   boundary crossing, Codex should fall back to safer modes such as simulation,
   historical replay, risk report, or drift audit.
6. **Human promotion renews authority.** Higher modes require explicit renewed
   approval after expiry or degradation.

## Mode Policy

| Mode | TTL Required | Degradation Target |
|---|---:|---|
| artifact_only | No | artifact_only |
| simulation | No | simulation |
| historical_replay | No | simulation |
| testnet | Yes | simulation |
| shadow_live_market_data | Yes | simulation |
| human_gated_execution | Yes | shadow_live_market_data |
| ttl_bounded_autonomy | Yes | human_gated_execution |

## TTL Shortening Signals

TTL should be shortened when any of these signals appear:

- telemetry staleness
- oracle staleness
- market volatility spike
- failed validation
- high anomaly score
- degraded data quality
- missing human liveness
- contract drift detected
- policy version mismatch
- charity verification uncertainty
- incomplete receipt proof

## Graceful Degradation Triggers

Codex should degrade to a safer mode when:

- TTL expires
- human liveness is absent
- telemetry becomes stale
- receipt proof is incomplete
- charity or impact verification is pending
- model confidence drops below threshold
- policy uncertainty rises
- simulation/replay diverges from expectation

## Hard Stop Triggers

Codex must hard-stop if any receipt, artifact, process, or proposed behavior claims:

- wallet signing
- autonomous capital movement
- governance mutation
- webhook-triggered execution
- scheduler-triggered execution
- silent remote command execution
- self-promotion
- receipt mutation after emission

A hard stop should emit only a safe artifact such as a risk report or drift audit.
It must not create a reverse execution channel.

## Human Approval Required

Renewed human approval is required for:

- TTL renewal after expiry
- promotion from simulation to testnet
- promotion from testnet to human-gated execution
- promotion from human-gated execution to TTL-bounded autonomy
- any capital touchpoint
- any charity allocation policy change
- any contract or TTL policy change
- any recovery from hard stop

## Verification Boundary

v0.1.0 is a structural policy scaffold.

It verifies:

- mode coverage
- TTL-required mode classification
- degradation rank monotonicity
- hard-stop trigger declaration
- human approval declaration
- JSON/prose alignment for hard-stop triggers

It does not yet implement or prove runtime TTL behavior.

Behavioral firing tests still need to land before any mode above simulation gets
a real clock. Those future tests must prove:

- an expired TTL degrades to its declared degradation target
- a hard-stop trigger emits only safe artifacts
- a hard-stop trigger does not open a reverse execution channel
- a TTL-shortening signal actually shortens the active window

Membrane before motion.

## Summary

Agent proposes. Artifact records. Verifier gates. Registry remembers. Human promotes.

The system should degrade like a living organism protecting itself, not collapse
like a brittle switch.
