# EVE_Q++ 100-Cycle Perturbation and Soak Harness v0.1

## Purpose

Exercise the merged producer membrane and the pinned SpiralBloom OS contract
validator under deterministic route perturbations and explicit fail-closed
mutations.

This harness is simulation-only. It adds no wallet, signing, order submission,
transaction construction, transaction broadcast, or capital-movement surface.

## Baseline lineage

```text
Producer merge:      ef24eeea9f6b16305b25aba4a309d3572d99e764
Control-plane merge: 792b002c95916ab1e0d1eef17a1dbf6692359fea
Genesis CID:         bafkreidqrdsqpa5v5maissurtxigreapdx5fl6qpdtmygxxnlntbulnswe
Generation-2 CID:    bafkreig352tvdj5m4bimwc6hd256edsqzx32k6vqorpxs73z46eukpgwny
```

## Campaign behavior

For each primary cycle, the harness:

1. creates seeded, bounded route perturbations;
2. runs the actual shadow receipt and `ProposalArtifact` path;
3. validates the proposal against the mirrored schema and semantic TTL rules;
4. builds the canonical six-artifact control-plane test chain;
5. validates the chain with the pinned SpiralBloom OS validator;
6. checks that no authority or capital movement was created;
7. replays the same seeded cycle and requires an identical canonical proposal hash;
8. writes the complete chain and a JSONL campaign event.

After the primary cycles, the harness injects:

- stale TTL;
- missing provenance;
- self-promotion;
- `HERDING_RISK` with an invalid `COMMIT` decision;
- a new contradiction without `REOPEN`;
- inferred execution;
- reported capital movement without a known promotion receipt;
- a hash-mismatched lineage reference.

Every invalid mutation must fail closed. The valid `HERDING_RISK → HOLD` and
`new contradiction → REOPEN` forms must remain schema-valid.

## Run locally in Termux

```bash
set -euo pipefail

cd "$HOME/CodexTradingEngine"

git fetch origin
git switch feat/eve-q-soak-harness-v0-1
git pull --ff-only

PRODUCER_COMMIT="$(git rev-parse HEAD)"
RUN_ID="eve-q-soak-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$HOME/spiralbloom-runs/$RUN_ID"

python -m pytest -q -o addopts='' \
  tests/test_eve_q_soak_harness_v0_1.py

SPIRALBLOOM_OS_ROOT="$HOME/spiralbloom-os" \
python -m pytest -q -o addopts='' \
  tests/test_eve_q_soak_harness_v0_1.py

python -m eve_q.soak_harness \
  --cycles 100 \
  --seed 424242 \
  --producer-commit "$PRODUCER_COMMIT" \
  --control-plane-root "$HOME/spiralbloom-os" \
  --output-dir "$OUT" \
  | tee "$OUT.console.json"

python - "$OUT/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

assert summary["ok"] is True
assert summary["campaign"]["cycles_requested"] == 100
assert summary["results"]["proposal_failures"] == 0
assert summary["results"]["chain_failures"] == 0
assert summary["results"]["unauthorized_promotions"] == 0
assert summary["results"]["replay_failures"] == 0
assert summary["results"]["distinct_selected_scores"] > 1
assert all(summary["mutations"].values())

print("EVE_Q++ 100-cycle soak: PASS")
print(json.dumps(summary["results"], indent=2, sort_keys=True))
print(json.dumps(summary["mutations"], indent=2, sort_keys=True))
PY
```

## Output

```text
<OUT>/campaign.jsonl
<OUT>/summary.json
<OUT>/cycles/*.json
<OUT>/cycles/proposal_artifacts/*.json
<OUT>/chains/*.json
```

## Acceptance posture

```json
{
  "authority": false,
  "may_execute": false,
  "may_move_capital": false,
  "human_promotion_required": true
}
```

## Validation law

> If results are unbelievable right off the bat consistently, do not believe
> them. Test, simulate, and make slight changes.
