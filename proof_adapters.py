from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from eveq_failsafe_receipt import CycleReceipt, is_non_production_cid


@dataclass(frozen=True)
class ProofResult:
    success: bool
    proof_type: str
    cid: Optional[str] = None
    local_path: Optional[str] = None
    production_trust_eligible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ProofAdapter(Protocol):
    proof_type: str

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        pass


class MockProofAdapter:
    proof_type = "mock"

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        cid = f"mock:{receipt.cycle_id}"
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            production_trust_eligible=False,
            metadata={"cid": cid, "reason": "mock proof is development-only"},
        )


class LocalFileProofAdapter:
    proof_type = "local_file"

    def __init__(self, output_dir: Path | str = "receipts") -> None:
        self.output_dir = Path(output_dir)

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self.output_dir / f"{receipt.cycle_id}.json"
        receipt.local_log_path = str(receipt_path)
        payload = receipt.to_json(indent=2)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        cid = f"local:{digest}"
        receipt.ipfs_cid = cid
        receipt.ipfs_success = True
        receipt_path.write_text(receipt.to_json(indent=2), encoding="utf-8")
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            local_path=str(receipt_path),
            production_trust_eligible=False,
            metadata={
                "cid": cid,
                "local_path": str(receipt_path),
                "sha256": digest,
                "reason": "local file proof is development/local-audit only",
            },
        )


class IPFSProofAdapter:
    proof_type = "ipfs"

    def __init__(self, publisher: Callable[[str], str]) -> None:
        self.publisher = publisher

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        try:
            cid = self.publisher(receipt.to_json(indent=2))
        except Exception as exc:  # pragma: no cover
            return ProofResult(
                success=False,
                proof_type=self.proof_type,
                production_trust_eligible=False,
                error=str(exc),
            )
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            production_trust_eligible=not is_non_production_cid(cid),
            metadata={"cid": cid, "publisher": "injected"},
        )


def apply_proof_to_receipt(receipt: CycleReceipt, proof: ProofResult) -> CycleReceipt:
    receipt.ipfs_success = proof.success
    receipt.ipfs_cid = proof.cid
    receipt.local_log_path = proof.local_path or receipt.local_log_path
    receipt.proof_type = proof.proof_type
    receipt.proof_production_trust_eligible = proof.production_trust_eligible
    receipt.proof_metadata = {
        **proof.metadata,
        "cid": proof.cid,
        "local_path": proof.local_path,
    }
    receipt.proof_error = proof.error
    if proof.error:
        receipt.errors.append(f"proof error: {proof.error}")
    if proof.success and not proof.production_trust_eligible:
        receipt.warnings.append(f"{proof.proof_type} proof is not production trust eligible")
    return receipt
