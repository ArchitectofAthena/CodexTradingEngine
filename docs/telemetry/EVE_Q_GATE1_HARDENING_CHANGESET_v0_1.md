# Gate 1 Hardening Changeset v0.1

Core implementation files:

- `eve_q/gate1_hardening.py`
- `schemas/gate1_resolution_receipt_v0_1.schema.json`
- `schemas/gate1_rollback_receipt_v0_1.schema.json`
- `scripts/run_gate1_read_only_capture_v0_1.sh`
- `tests/test_gate1_hardening_v0_1.py`

The changeset adds DNS/IP-class preflight, postflight drift detection, and canonical rollback receipts without activating Gate 1.
