"""Merkle tree proof validation for batch receipt verification.

This module provides Merkle tree construction and verification for cryptographic
proof of receipt batches, enabling scalable multi-receipt validation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class MerkleProof:
    """A Merkle tree proof for a specific leaf.
    
    Attributes:
        leaf_hash: Hash of the leaf being verified.
        path: List of sibling hashes from leaf to root.
        indices: Bit flags indicating left (0) or right (1) position of siblings.
        root_hash: Expected root hash for verification.
    """
    leaf_hash: str
    path: List[str]
    indices: int
    root_hash: str

    def verify(self) -> bool:
        """Verify the proof by computing the root hash.
        
        Returns:
            True if computed root matches expected root.
        """
        current = self.leaf_hash
        for i, sibling in enumerate(self.path):
            if (self.indices >> i) & 1:
                # Right sibling: hash(sibling || current)
                current = hashlib.sha256(
                    bytes.fromhex(sibling) + bytes.fromhex(current)
                ).hexdigest()
            else:
                # Left sibling: hash(current || sibling)
                current = hashlib.sha256(
                    bytes.fromhex(current) + bytes.fromhex(sibling)
                ).hexdigest()
        return current == self.root_hash


class MerkleTree:
    """A Merkle tree for batch receipt verification.
    
    Example:
        >>> receipts = [receipt1, receipt2, receipt3]
        >>> hashes = [receipt.ipfs_cid for receipt in receipts]
        >>> tree = MerkleTree(hashes)
        >>> proof = tree.proof(0)
        >>> assert proof.verify()
    """

    def __init__(self, leaves: List[str]) -> None:
        """Initialize Merkle tree from leaf hashes.
        
        Args:
            leaves: List of leaf hashes (typically receipt CIDs or cycle IDs).
        """
        self.leaves = leaves
        self.tree = self._build_tree(leaves)

    @staticmethod
    def _hash_pair(left: str, right: str) -> str:
        """Hash two values together.
        
        Args:
            left: Left hash.
            right: Right hash.
            
        Returns:
            SHA256 hash of concatenation.
        """
        return hashlib.sha256(
            bytes.fromhex(left) + bytes.fromhex(right)
        ).hexdigest()

    @staticmethod
    def _hash_leaf(value: str) -> str:
        """Hash a leaf value with domain separation.
        
        Args:
            value: Leaf value (e.g., cycle ID, CID).
            
        Returns:
            SHA256 hash with leaf prefix to prevent second preimage attacks.
        """
        return hashlib.sha256(
            b"LEAF" + bytes.fromhex(value) if len(value) % 2 == 0 else value.encode()
        ).hexdigest()

    def _build_tree(self, leaves: List[str]) -> List[List[str]]:
        """Build the Merkle tree.
        
        Args:
            leaves: Leaf hashes.
            
        Returns:
            Tree as list of levels, with root at end.
        """
        if not leaves:
            return [[]]

        # Hash all leaves
        current_level = [self._hash_leaf(leaf) for leaf in leaves]
        tree = [current_level]

        # Build tree bottom-up
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                if i + 1 < len(current_level):
                    parent = self._hash_pair(current_level[i], current_level[i + 1])
                else:
                    # Odd leaf: promote to next level
                    parent = current_level[i]
                next_level.append(parent)
            current_level = next_level
            tree.append(current_level)

        return tree

    @property
    def root(self) -> str:
        """Get the Merkle root hash.
        
        Returns:
            Root hash of the tree.
        """
        if not self.tree or not self.tree[-1]:
            return hashlib.sha256(b"").hexdigest()
        return self.tree[-1][0]

    def proof(self, leaf_index: int) -> MerkleProof:
        """Generate a Merkle proof for a leaf.
        
        Args:
            leaf_index: Index of the leaf to prove.
            
        Returns:
            MerkleProof containing path and verification data.
            
        Raises:
            IndexError: If leaf_index is out of bounds.
        """
        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError(f"Leaf index {leaf_index} out of range [0, {len(self.leaves)})")

        path: List[str] = []
        indices = 0
        current_index = leaf_index

        for level in range(len(self.tree) - 1):
            level_len = len(self.tree[level])
            sibling_index = current_index ^ 1
            is_right = current_index & 1

            if sibling_index < level_len:
                path.append(self.tree[level][sibling_index])
                if is_right:
                    indices |= 1 << len(path) - 1

            current_index = current_index // 2

        leaf_hash = self._hash_leaf(self.leaves[leaf_index])
        return MerkleProof(
            leaf_hash=leaf_hash,
            path=path,
            indices=indices,
            root_hash=self.root,
        )

    def verify_batch(self, indices: List[int]) -> bool:
        """Verify multiple leaves against root.
        
        Args:
            indices: List of leaf indices to verify.
            
        Returns:
            True if all proofs verify against root.
        """
        return all(self.proof(idx).verify() for idx in indices)
