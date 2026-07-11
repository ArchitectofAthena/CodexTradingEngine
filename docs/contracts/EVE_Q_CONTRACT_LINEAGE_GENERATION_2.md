# EVE_Q++ Contract Lineage Generation 2

**Recorded:** 2026-07-11  
**Repository:** `ArchitectofAthena/CodexTradingEngine`  
**Contract version:** `eve_q_cross_repo_v0.1`

## Lineage

```text
Genesis CID
bafkreidqrdsqpa5v5maissurtxigreapdx5fl6qpdtmygxxnlntbulnswe

        ↓ previous_cid

Generation-2 CID
bafkreig352tvdj5m4bimwc6hd256edsqzx32k6vqorpxs73z46eukpgwny
```

## Verified generation-2 envelope

```text
CID: bafkreig352tvdj5m4bimwc6hd256edsqzx32k6vqorpxs73z46eukpgwny
Pin type: recursive
Status: IPFS_PINNED_VERIFIED
Local SHA-256: f2a50e16cbed2ea06d561f2273ff1602ea649ab267d85ef543182b06341c5d8e
Previous CID: bafkreidqrdsqpa5v5maissurtxigreapdx5fl6qpdtmygxxnlntbulnswe
Producer merge commit: ef24eeea9f6b16305b25aba4a309d3572d99e764
Control-plane merge commit: 792b002c95916ab1e0d1eef17a1dbf6692359fea
Schema count: 6
Persistence scope: local Kubo node
```

## Constitutional posture

The retrieved envelope preserved:

```json
{
  "artifact_is_command": false,
  "execution_authority": "none",
  "human_promotion_required": true,
  "may_execute": false,
  "may_move_capital": false
}
```

The receipt inside the envelope also preserves:

- `authority: false`;
- `previous_contract_bundle_cid` equal to the genesis CID;
- the exact merged producer and control-plane commit SHAs;
- six mirrored schemas with file and canonical JSON hashes.

## Interpretation

The generation-2 CID proves that the merged producer and control-plane contract bundle was pinned recursively and retrieved from the local Kubo node with an explicit backward link to the genesis CID.

It does not prove semantic truth, authorize execution, grant wallet access, permit signing, or authorize capital movement.

## Verification command

A shell pipe and a Python heredoc both consume standard input, so they must not be combined as `ipfs cat "$CID" | python - <<'PY'`. Use a temporary file or pass the CID as an argument.

```bash
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_JSON"' EXIT

ipfs cat "$GENERATION_2_CID" > "$TMP_JSON"

python - "$TMP_JSON" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8"))

genesis = "bafkreidqrdsqpa5v5maissurtxigreapdx5fl6qpdtmygxxnlntbulnswe"
producer = "ef24eeea9f6b16305b25aba4a309d3572d99e764"
control_plane = "792b002c95916ab1e0d1eef17a1dbf6692359fea"

assert document["previous_cid"] == genesis
assert document["artifact_is_command"] is False
assert document["execution_authority"] == "none"
assert document["may_execute"] is False
assert document["may_move_capital"] is False
assert document["human_promotion_required"] is True
assert document["receipt"]["previous_contract_bundle_cid"] == genesis
assert document["receipt"]["producer_commit"] == producer
assert document["receipt"]["control_plane_commit"] == control_plane
assert document["receipt"]["schema_count"] == 6

print("Generation-2 lineage: PASS")
print("Previous CID:", document["previous_cid"])
print("Producer commit:", document["receipt"]["producer_commit"])
print("Control-plane commit:", document["receipt"]["control_plane_commit"])
PY
```

## Root law

> The CID proves the bytes and lineage. It does not create authority.
