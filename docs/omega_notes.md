# Omega Notes

Omega is the passive context layer for this branch.

It records context signals into a local event store and writes a small health file.

Primary files:

- omega_telemetry/config_tools.py
- omega_telemetry/models.py
- omega_telemetry/db.py
- omega_telemetry/health.py
- omega_telemetry/signal_observer.py
- omega_telemetry/context_runner.py
- rules/market_signal_rules.json
- config/omega.example.yaml

Run command:

```bash
python -m omega_telemetry.context_runner --config config/omega.example.yaml
```
