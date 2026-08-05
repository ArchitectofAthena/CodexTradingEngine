# CodexTradingEngine Telemetry-to-Draft-Fixture Adapter v0.1

## Purpose

The adapter translates one validated Gate 1A public-testnet snapshot into a deterministic local modeling draft.

It preserves five separate layers:

1. observed telemetry;
2. deterministic transformations;
3. operator-supplied assumptions;
4. missing economic inputs;
5. exact-hash operator review.

None of those layers creates Gate 2 authority. The adapter performs no network request and cannot propose, sign, submit, execute, or move capital.

## Preconditions

A build requires:

- a complete Gate 1A bundle containing `snapshot.json`, `raw.bin`, and `normalized.json`;
- a matching source entry in `registry/alpha_testnet_sources_v0_1.json` with `ELIGIBLE` disposition;
- an explicit mapping document;
- a separate operator-assumptions document.

The canonical registry now contains one time-bounded eligible source:

```text
ethereum-sepolia-blockscout-stats-v0-1
Review expires 2026-09-04T01:12:00Z
```

Its exact source-specific inputs are:

```text
registry/source_specs/ethereum_sepolia_blockscout_stats_v0_1.json
examples/alpha/sepolia_blockscout_stats_mapping_v0_1.json
examples/alpha/sepolia_blockscout_stats_assumptions_v0_1.json
```

The mapping preserves one provider-reported gas-price observation. Route economics remain separately labeled test-only assumptions.

## Mapping contract

Generic template:

```text
examples/alpha/telemetry_mapping_template_v0_1.json
```

Schema:

```text
schemas/telemetry_fixture_mapping_v0_1.schema.json
```

Every observed field names:

- the exact JSON Pointer into the immutable snapshot;
- the source unit;
- the target unit;
- either an identity transform or an explicit decimal scale factor.

The adapter records the original value and any transformed value separately. An operator assumption cannot overwrite an observed target field.

## Assumptions contract

Generic template:

```text
examples/alpha/modeling_assumptions_template_v0_1.json
```

Each assumption requires:

- field name;
- value;
- unit;
- written basis.

The adapter never supplies hidden defaults. It explicitly reports missing values for:

- gas cost;
- fees;
- liquidity;
- latency;
- slippage;
- bridge cost;
- safety margin.

## Build an unreviewed Sepolia draft

After one explicit capture has produced a bundle:

```bash
codex-telemetry-draft build \
  --bundle "$HOME/codex-alpha-runs/<RUN_ID>/snapshot" \
  --mapping examples/alpha/sepolia_blockscout_stats_mapping_v0_1.json \
  --assumptions examples/alpha/sepolia_blockscout_stats_assumptions_v0_1.json \
  --output-dir artifacts/<RUN_ID>-draft
```

For deterministic freshness testing, an explicit evaluation time may be supplied:

```bash
codex-telemetry-draft build \
  --bundle "$HOME/codex-alpha-runs/<RUN_ID>/snapshot" \
  --mapping examples/alpha/sepolia_blockscout_stats_mapping_v0_1.json \
  --assumptions examples/alpha/sepolia_blockscout_stats_assumptions_v0_1.json \
  --output-dir artifacts/<RUN_ID>-draft \
  --now <UTC-DATE-TIME>
```

The output directory contains:

```text
draft.json
draft-summary.json
draft-summary.txt
```

The first state is always:

```text
REVIEW: DRAFT_UNREVIEWED
LOCAL SIMULATION ELIGIBLE: false
AUTHORITY: false
EXECUTION: LOCKED
```

## Review the exact draft hash

Read the summary and inspect the underlying draft material. Then record one explicit decision:

```bash
codex-telemetry-draft review \
  --draft artifacts/<RUN_ID>-draft/draft.json \
  --expected-draft-hash <64-character-draft-hash> \
  --decision REVIEWED_FOR_LOCAL_SIMULATION \
  --reviewer "Architect" \
  --reviewed-at <UTC-DATE-TIME> \
  --note "Exact draft reviewed for local simulation only." \
  --output-dir artifacts/<RUN_ID>-reviewed
```

Other decisions are:

```text
RETURN_FOR_EVIDENCE
REJECTED
```

`REVIEWED_FOR_LOCAL_SIMULATION` is refused when any required economic assumption remains missing. The review hash must exactly match the immutable draft material.

A successful review changes only local simulation eligibility. It does not authorize `codex-research` invocation automatically and does not create a live proposal.

## First live rehearsal result

The reviewed Sepolia source completed the entire bounded path in GitHub Actions:

```text
DNS/IP preflight: PASS
one HTTPS GET: PASS
offline replay: PASS
post-capture resolution verification: PASS
draft translation: PASS
exact-hash local-simulation review: PASS
one-run local simulation: PASS
execution: LOCKED
capital: LOCKED
```

This result proves the workflow completed once under its recorded bounds. It does not establish production reliability, recurring profitability, or permission for autonomous capture.

## Fail-closed conditions

The adapter stops when:

- snapshot schema validation fails;
- raw, normalized, or artifact hashes do not match;
- normalized bytes differ from `normalized_payload`;
- the snapshot is stale;
- source IDs differ;
- the source is `HOLD` or `REJECT`;
- the exact host or allowed method differs from the reviewed registry entry;
- a mainnet identifier appears;
- wallet, signing, transaction, execution, or capital fields are enabled;
- a JSON Pointer is absent;
- an assumption tries to overwrite an observed field;
- the operator review names the wrong draft hash.

## Termux

The same installed editable package works in Termux:

```bash
source .venv/bin/activate
codex-alpha-doctor
codex-telemetry-draft --help
```

Keep capture bundles and draft artifacts in private local storage unless they contain only public information suitable for disclosure.

## Boundary

```text
snapshot = observation
mapping = deterministic translation
assumption = operator model
review = local eligibility
none = authority
```

Gate 1B, Gate 2, Gate 3, and Gates 4 through 6 remain locked.
