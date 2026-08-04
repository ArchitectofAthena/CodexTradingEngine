# Contributing to CodexTradingEngine

Thank you for testing the engine. The most valuable contribution is a small, reproducible finding that improves the simulation, verification, packaging, or boundary behavior.

## Start with the public path

Follow `QUICKSTART.md`, then run:

```bash
codex-research \
  --cycle-id contributor-check \
  --producer-commit 0000000000000000000000000000000000000000 \
  --output-dir artifacts/contributor-check
```

For the complete simulation-safe suite:

```bash
python -m pytest \
  -o addopts='' \
  --strict-markers \
  -m 'not live' \
  tests/
```

## Good reports

Please include:

- the exact commit or branch;
- operating system and Python version;
- the exact command;
- the smallest synthetic route or receipt fixture that reproduces the behavior;
- expected and observed results;
- whether the finding concerns pipeline mechanics, modeled economics, provenance, network boundaries, packaging, or execution-lock enforcement.

Attach `research-report.json` only after checking that it contains no private information.

## Pull requests

Keep each pull request focused. A repair should normally include:

1. a failing regression test;
2. the smallest reversible code change;
3. updated documentation when public behavior changes;
4. a clear statement of authority impact;
5. passing current workflows.

Do not weaken tests, remove evidence, or suppress findings merely to obtain a green check.

## Non-authority boundary

Contributions must not add or enable:

- wallet or seed access;
- private-key handling;
- signing;
- order or transaction construction;
- broadcast or submission;
- live trading;
- autonomous promotion;
- capital movement.

Simulation and proposal artifacts remain non-authoritative. Any future change to those boundaries requires an explicit, separately reviewed architecture decision.

## Security findings

Follow `SECURITY.md`. Never place exploit details, secrets, wallet material, credentials, or unredacted sensitive logs in a public issue.

## Research claims

Separate:

```text
observation
interpretation
hypothesis
simulation result
verified property
```

A benchmark improvement should include the classical baseline, fixture, metric, environment, and reproducible command. A modeled profit is not a promise of real-world profit.

## Conduct

Be direct about code and generous toward people. Disagreement, failed experiments, and negative results are useful evidence when they remain reproducible and specific.
