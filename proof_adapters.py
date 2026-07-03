"""Proof adapters for receipt publishing and validation.

This module provides pluggable proof adapters for storing and verifying cycle receipts
across different backends (local files, IPFS, mock).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from eveq_failsafe_receipt import CycleReceipt, is_non_production_cid


@dataclass(frozen=True)
class ProofResult:
    """Result of a proof publication attempt.
    
    Attributes:
        success: Whether the proof was successfully created.
        proof_type: The type of proof (e.g., 'mock', 'local_file', 'ipfs').
        cid: Content identifier (may be local hash or IPFS CID).
        local_path: Path to locally stored proof file.
        production_trust_eligible: Whether this proof can be used in production.
        metadata: Additional metadata about the proof.
        error: Error message if proof creation failed.
    """
    success: bool
    proof_type: str
    cid: Optional[str] = None
    local_path: Optional[str] = None
    production_trust_eligible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ProofAdapter(ABC):
    """Abstract base class for proof adapters.
    
    Proof adapters handle publishing and storing cycle receipts in various backends.
    """

    proof_type: str

    @abstractmethod
    def publish(self, receipt: CycleReceipt) -> ProofResult:
        """Publish a receipt and return the proof result.
        
        Args:
            receipt: The cycle receipt to publish.
            
        Returns:
            ProofResult containing the publication outcome and proof details.
        """
        pass


class MockProofAdapter(ProofAdapter):
    """Mock proof adapter for development and testing.
    
    Example:
        >>> adapter = MockProofAdapter()
        >>> receipt = CycleReceipt.shadow(cycle_id="test-1", ...)
        >>> result = adapter.publish(receipt)
        >>> assert result.proof_type == "mock"
    """

    proof_type = "mock"

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        """Generate a mock proof for development.
        
        Args:
            receipt: The cycle receipt to mock-publish.
            
        Returns:
            ProofResult with mock CID and development-only flag.
        """
        cid = f"mock:{receipt.cycle_id}"
        return ProofResult(
            success=True,
            proof_type=self.proof_type,
            cid=cid,
            production_trust_eligible=False,
            metadata={"cid": cid, "reason": "mock proof is development-only"},
        )


class LocalFileProofAdapter(ProofAdapter):
    """Proof adapter that stores receipts as local JSON files.
    
    Example:
        >>> adapter = LocalFileProofAdapter(output_dir="./receipts")
        >>> receipt = CycleReceipt.shadow(cycle_id="cycle-1", ...)
        >>> result = adapter.publish(receipt)
        >>> assert Path(result.local_path).exists()
    """

    proof_type = "local_file"

    def __init__(self, output_dir: Path | str = "receipts") -> None:
        """Initialize the local file adapter.
        
        Args:
            output_dir: Directory to store receipt JSON files.
        """
        self.output_dir = Path(output_dir)

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        """Publish receipt to local filesystem.
        
        Args:
            receipt: The cycle receipt to store.
            
        Returns:
            ProofResult with local file path and SHA256 digest.
        """
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


class IPFSProofAdapter(ProofAdapter):
    """Proof adapter that publishes receipts to IPFS.
    
    Example:
        >>> def mock_publisher(json_str: str) -> str:
        ...     return "QmExample123..."
        >>> adapter = IPFSProofAdapter(publisher=mock_publisher)
        >>> receipt = CycleReceipt.shadow(cycle_id="ipfs-1", ...)
        >>> result = adapter.publish(receipt)
        >>> assert result.cid.startswith("Qm")
    """

    proof_type = "ipfs"

    def __init__(self, publisher: Callable[[str], str]) -> None:
        """Initialize IPFS adapter with a publisher function.
        
        Args:
            publisher: Async or sync callable that takes JSON string and returns CID.
        """
        self.publisher = publisher

    def publish(self, receipt: CycleReceipt) -> ProofResult:
        """Publish receipt to IPFS.
        
        Args:
            receipt: The cycle receipt to publish.
            
        Returns:
            ProofResult with IPFS CID and production eligibility flag.
        """
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
    """Apply a proof result to a receipt.
    
    Args:
        receipt: The cycle receipt to update.
        proof: The proof result to apply.
        
    Returns:
        The updated receipt (modified in-place and returned).
        
    Example:
        >>> receipt = CycleReceipt.shadow(...)
        >>> adapter = MockProofAdapter()
        >>> proof = adapter.publish(receipt)
        >>> updated = apply_proof_to_receipt(receipt, proof)
        >>> assert updated.proof_type == "mock"
    """
    receipt.ipfs_success = proof.success
    receipt.ipfs_cid = proof.cid
    receipt.local_log_path = proof.local_path or receipt.local_log_path
    receipt.proof_type = proof.proof_type
    receipt.proof_production_trust_eligible = proof.production_trust_eligible
    return receipt
