# Tiered Deployment Gates

## Scope

This policy belongs to **CodexTradingEngine**. It does not configure, import, or modify Spiral Bloom OS.

The gate layer evaluates evidence and emits reviewable decisions with `authority: false`. It does not sign transactions, submit RPC calls, borrow flash liquidity, or move capital.

## Deployment ladder

| Tier | Name | Intended environment |
| --- | --- | --- |
| 0 | Local simulation | Deterministic replay, simulation, and shadow evaluation |
| 1 | Testnet | Network integration without real capital |
| 2 | Low-cost network | Approved alt-L1/L2 deployment with limited real-funds exposure |
| 3 | Ethereum mainnet | Highest-cost deployment, locked behind reserve and surplus-cash-flow requirements |

A transition may advance exactly one tier. Time alone, win rate alone, and isolated successful trades are never sufficient.

## Configuration

Thresholds live in `config/deployment_tiers.json` and are parsed into `TierPolicy`. The checked-in values are conservative starting defaults, not claims that a network or strategy is safe or profitable.

Operators should version policy changes and review them independently from strategy changes.

## Metrics

`MetricsAggregator` tracks:

- sample size and observation period;
- opportunity-detection accuracy and false-positive rate;
- execution success rate;
- expected realized net profit;
- drawdown and consecutive failures;
- maximum failed-attempt cost;
- maximum daily gas burn;
- prediction hit rate;
- restart and network-interruption recovery evidence.

Net economics must include the flash-loan premium, DEX fees, gas, priority or validator fees, slippage, and expected reverted-transaction cost.

## Live-entry rule

An opportunity is rejected unless:

```text
expected_gross_profit > estimated_total_costs + configured_safety_margin
```

The rule is strict. Equality is rejected. A high win rate cannot compensate for negative expected value or fat-tail losses.

## Risk controls

`RiskGovernor` enforces:

- daily loss ceiling;
- daily gas-burn ceiling;
- attempts-per-hour ceiling;
- consecutive-failure ceiling;
- circuit breaker;
- emergency global kill switch;
- per-network enable flag;
- per-strategy enable flag;
- explicit approval for live submission.

Every accepted and rejected opportunity should be written to `JsonlAuditLog` with the full economic estimate and rejection reasons.

## Network capability gate

Tier 2 and Tier 3 require a positive capability assessment covering:

- actual flash-liquidity support;
- sufficient liquidity depth;
- DEX availability;
- supported fee model;
- network reliability;
- slippage-model support;
- operational tooling;
- explicitly accepted bridge exposure.

A missing capability result fails closed.

## Graduation

Graduation requires every policy threshold to pass. The evaluator does not average failed requirements into a composite score.

Tier 3 additionally requires:

1. sustained profitable performance;
2. the configured reserve fund;
3. the configured ongoing surplus cash flow;
4. explicit human approval.

`GraduationStateStore` records decisions atomically. It advances persistent state only when the decision is eligible and an approving human identity is supplied.

## Approval boundary

Testnet eligibility may be evaluated automatically, but no transition involving real funds may occur without explicit approval. The result remains an eligibility artifact, not execution authority.

The constitutional sequence remains:

```text
Agent proposes.
Artifact records.
Verifier gates.
Registry remembers.
Human promotes.
```

## Test coverage

`tests/test_deployment_gates.py` covers:

- economic rejection despite apparent wins;
- cost aggregation;
- false-positive and success-rate aggregation;
- Ethereum reserve/surplus requirements;
- explicit live approval;
- human-only circuit-breaker reset.

Run:

```bash
pytest tests/test_deployment_gates.py
```
