# EVE_Q++ Cross-Repository Contract Pinning v0.1

## Purpose

Pin one deterministic, self-contained JSON bundle containing the six mirrored
EVE_Q++ contract schemas, their exact file hashes, their canonical JSON hashes,
and the commits from both repositories.

The pinned bundle is provenance. It is not approval and carries no execution or
capital authority.

## Bundle contents

The bundle must include:

- `ProposalArtifact` schema;
- `EvidenceBundle` schema;
- `GateDecision` schema;
- `HumanPromotionReceipt` schema;
- `RegistryEntry` schema;
- `ExecutionReceipt` schema;
- raw-file SHA-256 for each schema;
- canonical-JSON SHA-256 for each schema;
- producer and control-plane commit SHAs;
- prior bundle CID when extending an existing lineage;
- explicit non-authority fields.

The helper fails closed when any required schema is absent or invalid JSON.

## Restart local Kubo in Termux

```bash
export IPFS_PATH="$HOME/.ipfs"
termux-wake-lock

ipfs shutdown 2>/dev/null || true
pkill -f 'ipfs daemon' 2>/dev/null || true

nohup ipfs daemon \
  > "$HOME/ipfs_daemon.log" 2>&1 \
  < /dev/null &

echo $! > "$HOME/ipfs_daemon.pid"
sleep 5

curl -sS -X POST \
  http://127.0.0.1:5001/api/v0/version \
  | python -m json.tool

tail -n 30 "$HOME/ipfs_daemon.log"
```

Expected local surfaces:

- RPC API: `http://127.0.0.1:5001`
- gateway: `http://127.0.0.1:8080`

Keep both loopback-only.

## Pin and verify the contract bundle

Run after all six mirrored schemas exist on the producer branch:

```bash
cd ~/CodexTradingEngine

git checkout feat/eve-q-contract-producer-v0-1
git pull --ff-only

mkdir -p artifacts/contracts

PRODUCER_COMMIT="$(git rev-parse HEAD)"
CONTROL_PLANE_COMMIT="981aa240ff5bd73fb4562c4e351789aa9cfb307c"

python -m eve_q.contract_bundle \
  --schema-root schemas \
  --ledger artifacts/contracts/eve_q_contract_ipfs_ledger_v0_1.jsonl \
  --backend kubo \
  --kubo-api-url http://127.0.0.1:5001 \
  --producer-commit "$PRODUCER_COMMIT" \
  --control-plane-commit "$CONTROL_PLANE_COMMIT" \
  | tee artifacts/contracts/eve_q_contract_pin_result_v0_1.json
```

The command performs:

```text
build deterministic bundle
→ wrap in non-authoritative receipt envelope
→ add and recursively pin through local Kubo
→ verify pin state
→ retrieve bytes by CID
→ compare exact bytes
→ append ledger event
```

## Verify a returned CID manually

```bash
CID="PASTE_RETURNED_CID"

curl -sS -X POST \
  "http://127.0.0.1:5001/api/v0/pin/ls?arg=$CID&type=recursive" \
  | python -m json.tool

curl -sS -X POST \
  "http://127.0.0.1:5001/api/v0/cat?arg=$CID" \
  | python -m json.tool \
  | head -n 80
```

## Chained update

When pinning a later compatible revision, preserve lineage:

```bash
python -m eve_q.contract_bundle \
  --schema-root schemas \
  --ledger artifacts/contracts/eve_q_contract_ipfs_ledger_v0_1.jsonl \
  --backend kubo \
  --producer-commit "$(git rev-parse HEAD)" \
  --control-plane-commit "CONTROL_PLANE_COMMIT_SHA" \
  --previous-cid "PREVIOUS_CONTRACT_BUNDLE_CID"
```

## Root law

> The CID proves the bytes were pinned and retrieved.  
> It does not prove the claims are true.  
> It does not authorize execution.  
> Human promotion remains explicit.
