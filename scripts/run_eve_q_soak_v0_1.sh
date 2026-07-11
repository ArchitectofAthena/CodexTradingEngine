#!/usr/bin/env bash
set -euo pipefail

CYCLES="${CYCLES:-100}"
SEED="${SEED:-424242}"
CONTROL_PLANE_ROOT="${CONTROL_PLANE_ROOT:-$HOME/spiralbloom-os}"
RUN_ID="${RUN_ID:-eve-q-soak-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${OUT:-$HOME/spiralbloom-runs/$RUN_ID}"
PRODUCER_COMMIT="${PRODUCER_COMMIT:-$(git rev-parse HEAD)}"

mkdir -p "$OUT"

python -m eve_q.soak_harness \
  --cycles "$CYCLES" \
  --seed "$SEED" \
  --producer-commit "$PRODUCER_COMMIT" \
  --control-plane-root "$CONTROL_PLANE_ROOT" \
  --output-dir "$OUT" \
  | tee "$OUT.console.json"

python - "$OUT/summary.json" "$CYCLES" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
expected_cycles = int(sys.argv[2])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

assert summary["ok"] is True
assert summary["campaign"]["cycles_requested"] == expected_cycles
assert summary["results"]["proposal_failures"] == 0
assert summary["results"]["chain_failures"] == 0
assert summary["results"]["unauthorized_promotions"] == 0
assert summary["results"]["replay_failures"] == 0
assert summary["results"]["distinct_selected_scores"] > 1
assert all(summary["mutations"].values())

print("EVE_Q++ soak campaign: PASS")
print("Summary:", summary_path)
print("Ledger:", summary["artifacts"]["ledger"])
PY
