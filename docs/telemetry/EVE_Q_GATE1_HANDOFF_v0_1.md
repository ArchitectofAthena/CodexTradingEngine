# EVE_Q++ Gate 1 Pilot Handoff v0.1

## Branch

`feat/eve-q-live-read-only-telemetry-v0-1`

## Immediate local validation

```bash
python -m pytest -q -o addopts='' \
  tests/test_live_read_only_telemetry_v0_1.py \
  tests/test_gate1_pilot_acceptance_v0_1.py \
  tests/test_gate1_threat_and_rollback_docs_v0_1.py
```

## Current boundary

This is pilot infrastructure only. Gate 0 remains active, Gate 1 remains pilot-only, and Gates 2–6 remain locked.
