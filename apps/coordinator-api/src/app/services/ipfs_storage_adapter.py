"""
IPFS Storage Adapter Service

Service for offloading agent vector databases and knowledge graphs to IPFS/Filecoin.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException
from sqlmodel import Session, select

from ..blockchain.contract_interactions import ContractInteractionService
from ..domain.decentralized_memory import AgentMemoryNode, MemoryType, StorageStatus
from ..schemas.decentralized_memory import MemoryNodeCreate

# In a real environment, this would use a library like ipfshttpclient or a service like Pinata/Web3.Storage
# For this implementation, we will mock the interactions to demonstrate the architecture.

logger = logging.getLogger(__name__)


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
        # Using sha256 to simulate content hashing
        hash_val = hashlib.sha256(data).hexdigest()
        # Mocking a CIDv1 base32 string format (bafy...)
        return f"bafybeig{hash_val[:40]}"

    async def store_memory(
        self, request: MemoryNodeCreate, raw_data: bytes, zk_proof_hash: str | None = None
    ) -> AgentMemoryNode:
        """
        Upload raw memory data (e.g. serialized vector DB or JSON knowledge graph) to IPFS
        and create a tracking record.
        """
        # 1. Create initial record
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
            # 2. Upload to IPFS (Mocked)
            logger.info(f"Uploading {len(raw_data)} bytes to IPFS for agent {request.agent_id}")
            cid = await self._mock_ipfs_upload(raw_data)

            node.cid = cid
            node.status = StorageStatus.UPLOADED

            # 3. Pin to Filecoin/Pinning service (Mocked)
            if self.pinning_service_token:
                logger.info(f"Pinning CID {cid} to persistent storage")
                node.status = StorageStatus.PINNED

            self.session.commit()
            self.session.refresh(node)
            return node

        except Exception as e:
            logger.error(f"Failed to store memory node {node.id}: {str(e)}")
            node.status = StorageStatus.FAILED
            self.session.commit()
            raise HTTPException(status_code=500, detail="Failed to upload data to decentralized storage")

    async def get_memory_nodes(
        self, agent_id: str, memory_type: MemoryType | None = None, tags: list[str] | None = None
    ) -> list[AgentMemoryNode]:
        """Retrieve metadata for an agent's stored memory nodes"""
        query = select(AgentMemoryNode).where(AgentMemoryNode.agent_id == agent_id)

        if memory_type:
            query = query.where(AgentMemoryNode.memory_type == memory_type)

        # Execute query and filter by tags in Python (since SQLite JSON JSON_CONTAINS is complex via pure SQLAlchemy without specific dialects)
        results = self.session.execute(query).all()

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
            # Mocking the smart contract call to AgentMemory.sol
            # tx_hash = await self.contract_service.anchor_agent_memory(node.agent_id, node.cid, node.zk_proof_hash)
            tx_hash = "0x" + hashlib.sha256(f"{node.id}{node.cid}".encode()).hexdigest()

            node.anchor_tx_hash = tx_hash
            node.status = StorageStatus.ANCHORED
            self.session.commit()
            self.session.refresh(node)

            logger.info(f"Anchored memory {node_id} (CID: {node.cid}) to blockchain. Tx: {tx_hash}")
            return node

        except Exception as e:
            logger.error(f"Failed to anchor memory node {node_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to anchor CID to blockchain")

    async def retrieve_memory(self, node_id: str) -> bytes:
        """Retrieve the raw data from IPFS"""
        node = self.session.get(AgentMemoryNode, node_id)
        if not node or not node.cid:
            raise HTTPException(status_code=404, detail="Memory node or CID not found")

        # Mocking retrieval
        logger.info(f"Retrieving CID {node.cid} from IPFS network")
        mock_data = b'{"mock": "data", "info": "This represents decrypted vector db or KG data"}'
        return mock_data
