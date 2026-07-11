# EVE_Q++ Gate 1 Hardening Status v0.1

## Implemented in this branch

- DNS resolution preflight for reviewed hostnames;
- rejection of IP-literal source URLs;
- HTTPS port 443 restriction;
- rejection of private, loopback, link-local, multicast, reserved, unspecified, and invalid IP addresses;
- fail-closed rejection of mixed public/private resolution sets;
- canonical resolution receipts;
- post-capture DNS re-resolution and address-set drift detection;
- canonical rollback receipts for kill switch, source outage, DNS policy failure, and operator abort;
- launcher integration that records rollback evidence before returning to Gate 0;
- Python 3.11/3.13 CI coverage.

## Still required before Gate 1 human review

- reviewed public/read-only source set;
- transport-level IP pinning while preserving TLS hostname verification;
- bounded source-outage campaign;
- conflicting-source and weak-provenance campaign;
- bounded live-read-only soak;
- final content-addressed threat model, rollback test, and soak result;
- explicit human promotion.

## Gate posture

```text
Gate 0 SIMULATION_ONLY: ACTIVE
Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT HARDENING UNDER REVIEW
Gate 2–6: LOCKED
```

No gate is activated by this branch.
