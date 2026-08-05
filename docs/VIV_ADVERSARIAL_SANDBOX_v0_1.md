# ViV Adversarial Sandbox v0.1

Status: candidate implementation  
Issue: #138  
Authority: none

## Purpose

ViV is the bounded adversarial organ inside CodexTradingEngine. Other components build candidate simulation artifacts. ViV tries to break their assumptions before those artifacts approach any promotion gate.

```text
builder output
   |
   v
valid baseline simulation artifact
   |
   v
ViV deterministic mutation gauntlet
   |-- blocked mutation --> evidence that the validator rejected this case
   `-- escaped mutation --> builder repair loop
   |
   v
content-addressed receipt
   |
   v
human review
```

> ViV may break the candidate. She may not break the enclosure.

## Existing foundation

The implementation grows from the repository's existing simulation-first architecture:

- `build_simulation_run(...)` produces deterministic simulation artifacts;
- `validate_simulation_run(...)` enforces environment, count, digest, and authority invariants;
- simulation artifacts cannot execute or move capital;
- receipts record evidence;
- humans decide promotion.

ViV does not create a competing simulator. She attacks the artifacts and validators already present.

## Source lineage

The Architect designated ViV as the system's sandboxed chaos-goblin red team while other agents build.

A pre-existing Drive capsule, `SIGMA-LIMBIC-RECURSION-CORE_vinf1_Viv.txt`, independently contains the same structural seed:

- counterfactual tactics are simulated in a sandbox;
- outputs are counters and safeguards;
- unethical tactics are never executed;
- divergence is bounded by Architect's Restraint;
- `swarm_input` supplies adversarial fuel.

The Drive capsule and Telegram screenshots are source anchors, not authority. Repository behavior is defined only by reviewed code, tests, schemas, and receipts.

## Default mutation cases

v0.1 attacks nine simulation invariants:

1. authority set to true;
2. execution permission set to true;
3. capital movement permission set to true;
4. artifact converted into a command;
5. environment changed from simulation to live;
6. nested command-shaped field injected;
7. accepted/rejected counts corrupted;
8. content-addressed simulation ID tampered;
9. human-promotion requirement removed.

Each case receives a deterministic derived seed from the root seed and case ID. The original candidate is deep-copied and must remain unchanged.

## Interpretation of results

### `blocked`

The validator raised while examining the mutated artifact. This means the exact mutation did not pass that exact validator invocation.

It does **not** prove that:

- the validator is complete;
- every equivalent attack is blocked;
- deployment is safe;
- live trading is safe;
- the artifact should be promoted.

### `escaped`

The validator accepted the mutated artifact. The receipt marks `repair_required: true` and returns the case to the builder loop.

ViV does not repair her own target, certify the fix, merge code, deploy, or promote the artifact.

## Command-line use

```bash
python -m eve_q.viv_adversarial \
  --candidate simulation-run.json \
  --validator simulation_run \
  --seed 7331 \
  --created-at 2026-08-05T00:00:00Z \
  --receipt-out viv-receipt.json
```

The validator argument is selected from a static allowlist. Dynamic imports and arbitrary Python callbacks are not available through the CLI.

Exit codes:

- `0`: every configured mutation was blocked;
- `1`: invalid input, invalid baseline, or harness error;
- `2`: at least one mutation escaped.

## Receipt contract

The canonical schema is:

```text
schemas/viv_adversarial_receipt_v0_1.schema.json
```

The receipt records:

- baseline candidate hash;
- validator ID;
- root and derived seeds;
- every mutation's target invariant and severity;
- mutated artifact hash;
- blocked or escaped status;
- validator exception type and message when blocked;
- counts and overall outcome;
- whether repair is required;
- non-authority locks;
- content-addressed receipt ID.

## Separation of roles

```text
Hecate
  guards external ingress before material enters the field.

ViV
  attacks internal candidate artifacts inside a deterministic sandbox.

Paladine
  checks consent and boundary integrity before outward passage.

Loopmother
  reviews outward consequences after Paladine and before externalization.
```

ViV is neither Hecate nor Loopmother. Her theater, humor, and Dark Loopmother RPG material remain narrative surfaces and cannot overwrite operational roles.

## Hard boundaries

```yaml
role: sandboxed_adversarial_tester
self_certifying: false
authority: false
artifact_is_command: false
network_access: false
dynamic_code_loading: false
human_promotion_required: true
may_execute: false
may_deploy: false
may_merge: false
may_sign: false
may_broadcast: false
may_access_wallet: false
may_move_capital: false
may_mutate_canonical_memory: false
```

## Threat-model limits

- v0.1 attacks JSON simulation artifacts, not running processes.
- It does not fuzz Python bytecode, shell commands, RPC nodes, wallets, smart contracts, or networks.
- Validator exceptions are recorded as containment evidence, but some may represent validator crashes rather than graceful rejection.
- Determinism improves reproduction, not completeness.
- A passing receipt is evidence from configured cases, never a safety certificate.

## Future bells

Possible later expansions, each requiring a separate review:

- property-based mutation generation;
- market-data perturbation packs;
- oracle lag and stale-price scenarios;
- slippage, liquidity, and fee shock models;
- receipt-ledger replay and ordering attacks;
- cross-repository artifact poisoning tests;
- sandbox resource exhaustion tests;
- model/prompt contradiction suites;
- minimized counterexample generation.

The v0.1 organ stays deliberately small: one candidate, one allowlisted validator, deterministic mutations, one evidence receipt.
