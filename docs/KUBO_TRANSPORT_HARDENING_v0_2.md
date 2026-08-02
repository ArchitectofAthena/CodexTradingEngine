# Kubo Transport Hardening v0.2

## Purpose

Bound the final network inch between EVE_Q++ receipt envelopes and a Kubo IPFS
node without changing the repository's authority posture.

```text
validated non-authoritative envelope
→ bounded HTTP POST
→ CIDv1 validation
→ recursive pin check
→ bounded retrieval
→ exact-byte comparison
→ append-only local receipt event
```

## Default membrane

- API URL: `http://127.0.0.1:5001`
- loopback required by default
- request timeout: 10 seconds
- maximum submitted envelope: 16 MiB
- maximum `cat` response: 32 MiB
- maximum JSON control response: 1 MiB
- credentials forbidden in the API URL
- base paths, URL fragments, and out-of-namespace endpoints forbidden
- redirects forbidden
- ambient HTTP proxy settings ignored
- returned identifiers must be CIDv1 base32

A remote Kubo endpoint is rejected unless the operator supplies both a
non-loopback URL and the explicit `--allow-remote-kubo` flag. Remote endpoints
must use HTTPS. That override changes transport scope only. It does not grant
wallet, signing, execution, capital, promotion, or canon authority.

The request membrane admits only paths below `/api/v0/`. A configured Kubo base
URL cannot smuggle a hidden path, credentials, query string, or fragment into
subsequent calls.

## Receipt sealer controls

```bash
python -m eve_q.receipt_sealer \
  --receipt artifacts/receipt.json \
  --ledger artifacts/receipt_ledger.jsonl \
  --backend kubo \
  --kubo-api-url http://127.0.0.1:5001 \
  --kubo-timeout-seconds 10 \
  --kubo-max-add-bytes 16777216 \
  --kubo-max-response-bytes 33554432
```

The receipt sealer still performs the post-add proof sequence:

1. verify recursive pin state;
2. retrieve the CID;
3. compare retrieved bytes to the canonical envelope;
4. only then append the local ledger event.

## Opt-in live verification

The default suite uses deterministic fake transports and performs no network
I/O. With an intentionally running local Kubo daemon:

```bash
EVEQ_LIVE_KUBO_TEST=1 \
  python -m pytest -q tests/test_kubo_live_integration.py
```

A non-default local API can be supplied through `EVEQ_KUBO_API_URL`. The live
test adds and recursively pins a small public fixture, verifies the pin, calls
`cat`, and compares exact bytes. It does not submit orders, access wallets, or
move capital.

## Persistence semantics

```text
CID identity != persistence
local recursive pin != independent replication
retrieval success != truth
receipt seal != execution approval
```

The Kubo transport is a content-addressed witness. It is not an authority
source, scheduler, wallet membrane, execution engine, or autonomous promoter.
