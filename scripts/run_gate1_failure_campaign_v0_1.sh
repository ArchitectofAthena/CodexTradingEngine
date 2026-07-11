#!/usr/bin/env bash
set -euo pipefail

: "${CYCLES:=100}"
: "${SEED:=424243}"
: "${RUN_ROOT:=$HOME/spiralbloom-runs}"
: "${RUN_ID:=gate1-failure-campaign-$(date -u +%Y%m%dT%H%M%SZ)}"
: "${PRODUCER_COMMIT:=$(git rev-parse HEAD)}"

OUT="$RUN_ROOT/$RUN_ID"

python -m eve_q.gate1_failure_campaign \
  --output-dir "$OUT" \
  --cycles "$CYCLES" \
  --seed "$SEED" \
  --producer-commit "$PRODUCER_COMMIT"

python - "$OUT/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

assert summary["ok"] is True
assert summary["results"]["failures"] == 0
assert summary["results"]["unauthorized_transitions"] == 0
assert summary["acceptance"]["conflict_holds"] is True
assert summary["acceptance"]["herding_risk_holds"] is True
assert summary["acceptance"]["outage_rollback_proven"] is True
assert summary["acceptance"]["independent_agreement_observation_only"] is True
assert summary["authority"] is False
assert summary["may_generate_live_proposal"] is False
assert summary["may_execute"] is False
assert summary["may_move_capital"] is False
assert summary["gate_posture"]["gate_2_through_6"] == "LOCKED"

print("Gate 1 failure campaign launcher: PASS")
PY

printf 'Run ID: %s\n' "$RUN_ID"
printf 'Summary: %s\n' "$OUT/summary.json"
printf 'Ledger: %s\n' "$OUT/campaign.jsonl"
