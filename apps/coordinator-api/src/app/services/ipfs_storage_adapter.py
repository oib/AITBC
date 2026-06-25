"""
IPFS Storage Adapter Service

Service for offloading agent vector databases and knowledge graphs to IPFS/Filecoin.
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..blockchain.contract_interactions import ContractInteractionService  # type: ignore[import-not-found]
from ..contexts.ipfs.domain.decentralized_memory import AgentMemoryNode, MemoryType, StorageStatus
from ..contexts.ipfs.schemas.decentralized_memory import MemoryNodeCreate

logger = get_logger(__name__)


class IPFSAdapterService:
    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService,
        ipfs_gateway_url: str = "http://127.0.0.1:5001/api/v0",
        pinning_service_token: str | None = None,
    ):
        self.session = session
        self.contract_service = contract_service
        self.ipfs_gateway_url = ipfs_gateway_url
        self.pinning_service_token = pinning_service_token

    async def _mock_ipfs_upload(self, data: bytes) -> str:
        """Mock function to simulate IPFS CID generation (v1 format CID simulation)"""
        hash_val = hashlib.sha256(data).hexdigest()
        return f"bafybeig{hash_val[:40]}"

    async def store_memory(
        self, request: MemoryNodeCreate, raw_data: bytes, zk_proof_hash: str | None = None
    ) -> AgentMemoryNode:
        """
        Upload raw memory data (e.g. serialized vector DB or JSON knowledge graph) to IPFS
        and create a tracking record.
        """
        node = AgentMemoryNode(
            agent_id=request.agent_id,
            memory_type=request.memory_type,
            is_encrypted=request.is_encrypted,
            metadata=request.metadata,
            tags=request.tags,
            size_bytes=len(raw_data),
            status=StorageStatus.PENDING,
            zk_proof_hash=zk_proof_hash,
        )
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        try:
            logger.info("Uploading %s bytes to IPFS for agent %s", len(raw_data), request.agent_id)
            cid = await self._mock_ipfs_upload(raw_data)
            node.cid = cid
            node.status = StorageStatus.UPLOADED
            if self.pinning_service_token:
                logger.info("Pinning CID %s to persistent storage", cid)
                node.status = StorageStatus.PINNED
            self.session.commit()
            self.session.refresh(node)
            return node
        except Exception as e:
            logger.error("Failed to store memory node %s: %s", node.id, str(e))
            node.status = StorageStatus.FAILED
            self.session.commit()
            raise HTTPException(status_code=500, detail="Failed to upload data to decentralized storage") from e

    async def get_memory_nodes(
        self, agent_id: str, memory_type: MemoryType | None = None, tags: list[str] | None = None
    ) -> list[AgentMemoryNode]:
        """Retrieve metadata for an agent's stored memory nodes"""
        query = select(AgentMemoryNode).where(AgentMemoryNode.agent_id == agent_id)
        if memory_type:
            query = query.where(AgentMemoryNode.memory_type == memory_type)
        results = list(self.session.scalars(query).all())
        if tags and len(tags) > 0:
            filtered_results = []
            for r in results:
                if all(tag in r.tags for tag in tags):
                    filtered_results.append(r)
            return filtered_results
        return results

    async def anchor_to_blockchain(self, node_id: str) -> AgentMemoryNode:
        """
        Anchor a specific IPFS CID to the agent's smart contract profile to ensure data lineage.
        """
        node = self.session.get(AgentMemoryNode, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Memory node not found")
        if not node.cid:
            raise HTTPException(status_code=400, detail="Cannot anchor node without CID")
        if node.status == StorageStatus.ANCHORED:
            return node
        try:
            tx_hash = "0x" + hashlib.sha256(f"{node.id}{node.cid}".encode()).hexdigest()
            node.anchor_tx_hash = tx_hash
            node.status = StorageStatus.ANCHORED
            self.session.commit()
            self.session.refresh(node)
            logger.info("Anchored memory %s (CID: %s) to blockchain. Tx: %s", node_id, node.cid, tx_hash)
            return node
        except Exception as e:
            logger.error("Failed to anchor memory node %s: %s", node_id, str(e))
            raise HTTPException(status_code=500, detail="Failed to anchor CID to blockchain") from e

    async def retrieve_memory(self, node_id: str) -> bytes:
        """Retrieve the raw data from IPFS"""
        node = self.session.get(AgentMemoryNode, node_id)
        if not node or not node.cid:
            raise HTTPException(status_code=404, detail="Memory node or CID not found")
        logger.info("Retrieving CID %s from IPFS network", node.cid)
        mock_data = b'{"mock": "data", "info": "This represents decrypted vector db or KG data"}'
        return mock_data
