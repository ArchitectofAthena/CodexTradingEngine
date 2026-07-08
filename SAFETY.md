# Safety Boundary

CodexTradingEngine is a simulation-first, artifact-first safety research repository.

## Repository Boundary

This repository may define:

- policies
- simulations
- receipts
- risk reports
- drift audits
- charity allocation proposals
- testnet results
- validation artifacts

This repository must not silently perform:

- wallet signing
- transaction signing
- capital movement
- autonomous execution
- webhook-triggered execution
- scheduler-triggered execution
- governance mutation
- self-promotion
- reverse execution into SpiralBloom OS

## Authority Model

Agent proposes. Artifact records. Verifier gates. Registry remembers. Human promotes.

Authority expires. Uncertainty degrades permission. Human approval renews authority.

## SpiralBloom Bridge

SpiralBloom may review Codex artifacts.

Codex may emit proposals.

Codex may not silently command SpiralBloom execution.

SpiralBloom may not silently command Codex execution.

The bridge is artifact-driven, review-first, and human-promoted.

## Runtime Boundary

Policy artifacts in this repository do not create runtime authority.

A policy file is not permission to trade.

A receipt is not permission to execute.

A passing test is not permission to move capital.

Human approval remains required for any real capital touchpoint.
