# Gate 1 Read-Only Deployment

Gate 1 is the only gate released by this deployment profile.

```text
Gate 0: ACTIVE
Gate 1: OPEN_READ_ONLY
Gates 2-6: LOCKED
```

The container performs one explicit, operator-invoked HTTPS `GET` or `HEAD`, writes one immutable snapshot bundle, and exits. It cannot generate live proposals, sign, submit, broadcast, access wallets, or move capital.

## Build and inspect posture

```bash
docker build -f Dockerfile.gate1 -t codex-gate1:local .
docker run --rm codex-gate1:local status
```

The status document must report:

- `gate_1: OPEN_READ_ONLY`
- `gate_2_through_6: LOCKED`
- `authority: false`
- `may_execute: false`
- `may_move_capital: false`

## Run one capture

From the repository root:

```bash
mkdir -p deploy/artifacts
export CODEX_PRODUCER_COMMIT="$(git rev-parse HEAD)"
export CODEX_CAPTURE_ID="capture-$(date -u +%Y%m%dT%H%M%SZ)"
docker compose -f deploy/gate1-compose.yml run --rm gate1-capture
```

The source file is mounted read-only. The output bundle is committed atomically with private file modes. An existing output directory is never overwritten.

## Network boundary

The runtime:

- requires HTTPS on port 443;
- requires an exact hostname allowlist match;
- resolves the host before connecting;
- rejects loopback, private, link-local, reserved, multicast, and mixed public/private results;
- pins the TLS connection to a validated public IP while retaining hostname certificate verification;
- follows at most three redirects, each revalidated against the same allowlist;
- permits only `GET` and `HEAD`;
- caps timeout and response bytes;
- excludes cookies and other unsafe headers from `HEAD` artifacts.

## Credential boundary

Do not inject wallet, signing, trading, order, seed, mnemonic, or private-key credentials. Gate 1 fails closed when write-capable secret-shaped environment names are present. Cosmetic prefixes such as `PUBLIC_` or `READ_ONLY_` do not neutralize a signing or private-key variable.

## Kill switch and rollback

Immediate stop:

```bash
export EVE_Q_GATE1_KILL_SWITCH=1
```

Because each capture is a one-shot job with `restart: "no"`, there is no autonomous worker to drain. Delete an unreviewed capture bundle, revert this release commit, or redeploy the previous simulation-only image. Gates 2-6 remain locked throughout rollback.

## Promotion boundary

A successful Gate 1 artifact is evidence only. It cannot promote itself into proposal generation, transaction construction, execution, or capital authority. Any future Gate 2 discussion requires a separate review, separate tests, and an explicit human decision.
