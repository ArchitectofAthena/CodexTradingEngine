# Security Policy

## Supported surface

Security fixes target the current `main` branch and the deployable Gate 1 read-only telemetry surface.

## Reporting

Do not place credentials, wallet material, private keys, seed phrases, exploit payloads, or unredacted sensitive logs in a public issue. Use GitHub private vulnerability reporting when available, or contact the repository owner privately.

A useful report includes the affected commit, file and line, reproducible conditions, impact, and a redacted proof of concept.

## Authority boundary

Gate 1 is observation-only. It must not gain wallet access, signing, transaction construction, broadcast, execution, autonomous promotion, or capital movement. Any change that weakens that boundary is treated as a security regression.

## Audit cadence

The `Security Audit` workflow runs on pull requests, pushes to `main`, manual dispatch, and weekly on Monday. It performs:

- repository-native AST and policy scanning;
- high-confidence Bandit analysis;
- dependency vulnerability auditing;
- redacted secret-shape detection;
- GitHub Actions permission and immutable-reference review;
- container privilege and namespace review.

High or critical findings block the workflow. Medium findings remain visible in the uploaded audit artifact and require triage rather than silent suppression.

## Suppressions

A finding may be suppressed only by adding its deterministic fingerprint to `.security-audit-allowlist.json` with a review note in the pull request. Never suppress a secret finding merely to make CI green.
