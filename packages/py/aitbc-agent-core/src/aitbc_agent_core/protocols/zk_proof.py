"""
ZK proof protocols for zero-knowledge proof generation and verification.
These protocols define the interface for ZK proof services.
"""

from abc import ABC, abstractmethod
from typing import Any


class IZKProofService(ABC):
    """Protocol for ZK proof generation and verification"""

    @abstractmethod
    async def generate_zk_proof(
        self,
        circuit_name: str,
        inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate a zero-knowledge proof.
        
        Args:
            circuit_name: Name of the ZK circuit
            inputs: Circuit inputs
            
        Returns:
            Proof metadata including proof_id, size, generation_time
        """
        ...

    @abstractmethod
    async def verify_proof(
        self,
        proof_id: str
    ) -> dict[str, Any]:
        """
        Verify a zero-knowledge proof.
        
        Args:
            proof_id: ID of the proof to verify
            
        Returns:
            Verification result with status and verification_time
        """
        ...
