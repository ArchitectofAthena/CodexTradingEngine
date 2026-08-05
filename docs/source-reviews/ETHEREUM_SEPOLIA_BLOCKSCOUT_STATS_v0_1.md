# Ethereum Sepolia Blockscout Stats Source Review v0.1

## Decision

```text
Source: ethereum-sepolia-blockscout-stats-v0-1
Disposition: ELIGIBLE
Scope: Gate 1A public-testnet read-only alpha
Reviewed: 2026-08-05T01:12:00Z
Review expires: 2026-09-04T01:12:00Z
Authority: false
```

Eligibility is time-bounded and applies only to the exact host, endpoint, method, limits, and interpretation recorded here.

## Exact source

```text
Network: Ethereum Sepolia
Chain ID: 11155111
Operator: Blockscout
Host: eth-sepolia.blockscout.com
URL: https://eth-sepolia.blockscout.com/api/v2/stats
Method: GET
Endpoint class: per-instance Blockscout REST API v2 stats counters
Credential: none
```

## External evidence reviewed

1. Ethereum.org testnet guidance
   - https://ethereum.org/developers/docs/networks/
   - Ethereum.org identifies Sepolia as the recommended default testnet for application development.

2. Canonical Sepolia network configuration
   - https://github.com/eth-clients/sepolia
   - The cross-client configuration records chain ID and network ID `11155111`.

3. Blockscout per-instance REST API documentation
   - https://docs.blockscout.com/devs/apis/rest
   - Blockscout describes per-instance REST methods as publicly accessible and documents each instance's API documentation surface.

4. Stats endpoint contract
   - https://docs.blockscout.com/api-reference/get-stats-counters
   - Blockscout documents `GET /api/v2/stats` and an `application/json` response containing chain counters and gas-price fields.

5. Request limits
   - https://docs.blockscout.com/devs/apis/requests-and-limits
   - Blockscout documents a default unauthenticated per-IP limit of 300 requests per minute.

## Gate 1A bounds

```text
Requests per explicit run: 1
Automatic recurrence: forbidden
Allowed method: GET only
Exact host: eth-sepolia.blockscout.com
Allowed port: 443 only
Timeout: 10 seconds
Response cap: 131072 bytes
Freshness TTL: 120 seconds
Wallet required: false
Signing required: false
Transaction submission: false
Capital movement: false
```

The repository transport also performs DNS/IP preflight, public-address enforcement, exact-host redirect enforcement, offline replay, raw and normalized hash verification, post-capture resolution verification, and rollback-receipt emission on supported failure.

## Interpretation boundary

This endpoint is not an executable market-data feed.

Permitted use:

- public Sepolia chain counters;
- provider-reported gas statistics;
- bounded workflow and provenance testing;
- local simulation context after explicit translation and exact-hash review.

Forbidden interpretation:

- treating `coin_price` or `market_cap` as an executable quote;
- treating any response field as a mainnet value;
- asserting recurring profit from one observation;
- using the source to create a Gate 2 proposal;
- signing, submitting, executing, or moving capital.

The first mapping records one provider-reported average gas-price observation. Route profitability, gas cost, fees, liquidity, latency, slippage, bridge cost, and safety margin remain explicit test-only operator assumptions.

## Concentration and provider-drift risk

This is one provider and one explorer instance. It does not establish independent corroboration.

Blockscout has announced that per-instance API endpoints are expected to be deprecated in favor of its PRO API. Therefore this source returns to `HOLD` when any of the following occurs:

- review expiry is reached;
- host or endpoint changes;
- network or chain identity changes;
- response contract changes materially;
- authentication becomes required;
- terms or request limits change;
- redirects leave the exact host;
- payload exceeds the response cap;
- replay or hash verification fails;
- the endpoint becomes unavailable or stale;
- any wallet, signing, transaction, execution, or capital surface appears.

## Re-review deadline

```text
2026-09-04T01:12:00Z
```

A new evidence receipt and registry update are required after that point. Silence, continued availability, or a passing historical capture does not extend eligibility.

## Authority receipt

```text
authority: false
artifact_is_command: false
network_capture_allowed: only through explicit Gate 1A invocation
may_generate_live_proposal: false
may_sign: false
may_submit_transaction: false
may_execute: false
may_move_capital: false
```

> Eligibility means this exact observation path has earned one bounded look. It does not mean the source owns the truth or the engine owns the next action.
