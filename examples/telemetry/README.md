# Gate 1 source specifications

Source specifications are explicit allowlist entries for the live read-only telemetry pilot.

The checked-in template is intentionally non-live. Copy it outside the repository, replace the URL and host with a reviewed public or demonstrably read-only source, and keep credentials out of the file.

The pilot requires:

```bash
export EVE_Q_GATE1_PILOT=1
```

The emergency rollback switch is:

```bash
export EVE_Q_GATE1_KILL_SWITCH=1
```

Do not commit generated snapshots or credentials. Runtime bundles belong under `$HOME/spiralbloom-runs/` or another explicitly managed artifact directory.
