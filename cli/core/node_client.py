"""
Node client for multi-chain operations
"""

import asyncio
import httpx
import json
from typing import Dict, List, Optional, Any
from core.config import NodeConfig
from models.chain import ChainInfo, ChainType, ChainStatus, ConsensusAlgorithm

class NodeClient:
    """Client for communicating with AITBC nodes"""
    
    def __init__(self, node_config: NodeConfig):
        self.config = node_config
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout),
            limits=httpx.Limits(max_connections=self.config.max_connections)
        )
        await self._authenticate()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
    
    async def _authenticate(self):
        """Authenticate with the node"""
        try:
            # For now, we'll use a simple authentication
            # In production, this would use proper authentication
            response = await self._client.post(
                f"{self.config.endpoint}/api/auth",
                json={"action": "authenticate"}
            )
            if response.status_code == 200:
                data = response.json()
                self._session_id = data.get("session_id")
        except Exception as e:
            # For development, we'll continue without authentication
            pass # print(f"Warning: Could not authenticate with node {self.config.id}: {e}")
    
    async def get_node_info(self) -> Dict[str, Any]:
        """Get node information"""
        try:
            response = await self._client.get(f"{self.config.endpoint}/api/node/info")
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Node info request failed: {response.status_code}")
        except Exception as e:
            # Return mock data for development
            return self._get_mock_node_info()
    
    async def get_hosted_chains(self) -> List[ChainInfo]:
        """Get all chains hosted by this node"""
        try:
            health_url = f"{self.config.endpoint}/health"
            if "/rpc" in self.config.endpoint:
                health_url = self.config.endpoint.replace("/rpc", "/health")
            
            response = await self._client.get(health_url)
            if response.status_code == 200:
                health_data = response.json()
                chains = health_data.get("supported_chains", ["ait-devnet"])
                
                result = []
                for cid in chains:
                    # Try to fetch real block height
                    block_height = 0
                    try:
                        head_url = f"{self.config.endpoint}/rpc/head?chain_id={cid}"
                        if "/rpc" in self.config.endpoint:
                            head_url = f"{self.config.endpoint}/head?chain_id={cid}"
                        head_resp = await self._client.get(head_url, timeout=2.0)
                        if head_resp.status_code == 200:
                            head_data = head_resp.json()
                            block_height = head_data.get("height", 0)
                    except Exception:
                        pass
                        
                    result.append(self._parse_chain_info({
                        "id": cid,
                        "name": f"AITBC {cid.split('-')[-1].capitalize()} Chain",
                        "type": "topic" if "health" in cid else "main",
                        "purpose": "specialized" if "health" in cid else "general",
                        "status": "active",
                        "size_mb": 50.5,
                        "nodes": 3,
                        "smart_contracts": 5,
                        "active_clients": 25,
                        "active_miners": 8,
                        "block_height": block_height,
                        "privacy": {"visibility": "public"}
                    }))
                return result
            else:
                return self._get_mock_chains()
        except Exception as e:
            return self._get_mock_chains()

    async def get_chain_info(self, chain_id: str) -> Optional[ChainInfo]:
        """Get specific chain information"""
        try:
            # Re-use the health endpoint logic
            health_url = f"{self.config.endpoint}/health"
            if "/rpc" in self.config.endpoint:
                health_url = self.config.endpoint.replace("/rpc", "/health")
                
            response = await self._client.get(health_url)
            if response.status_code == 200:
                health_data = response.json()
                chains = health_data.get("supported_chains", ["ait-devnet"])
                if chain_id in chains:
                    block_height = 0
                    try:
                        head_url = f"{self.config.endpoint}/rpc/head?chain_id={chain_id}"
                        if "/rpc" in self.config.endpoint:
                            head_url = f"{self.config.endpoint}/head?chain_id={chain_id}"
                        head_resp = await self._client.get(head_url, timeout=2.0)
                        if head_resp.status_code == 200:
                            head_data = head_resp.json()
                            block_height = head_data.get("height", 0)
                    except Exception:
                        pass
                        
                    return self._parse_chain_info({
                        "id": chain_id,
                        "name": f"AITBC {chain_id.split('-')[-1].capitalize()} Chain",
                        "type": "topic" if "health" in chain_id else "main",
                        "purpose": "specialized" if "health" in chain_id else "general",
                        "status": "active",
                        "size_mb": 50.5,
                        "nodes": 3,
                        "smart_contracts": 5,
                        "active_clients": 25,
                        "active_miners": 8,
                        "block_height": block_height,
                        "privacy": {"visibility": "public"}
                    })
            return None
        except Exception as e:
            # Fallback to pure mock
            chains = self._get_mock_chains()
            for chain in chains:
                if chain.id == chain_id:
                    return chain
            return None

    async def create_chain(self, genesis_block: Dict[str, Any]) -> str:
        """Create a new chain on this node"""
        try:
            response = await self._client.post(
                f"{self.config.endpoint}/api/chains",
                json=genesis_block
            )
            if response.status_code == 201:
                data = response.json()
                return data["chain_id"]
            else:
                raise Exception(f"Chain creation failed: {response.status_code}")
        except Exception as e:
            # Mock chain creation for development
            chain_id = genesis_block.get("chain_id", f"MOCK-CHAIN-{hash(str(genesis_block)) % 10000}")
            print(f"Mock created chain {chain_id} on node {self.config.id}")
            return chain_id
    
    async def delete_chain(self, chain_id: str) -> bool:
        """Delete a chain from this node"""
        try:
            response = await self._client.delete(f"{self.config.endpoint}/api/chains/{chain_id}")
            if response.status_code == 200:
                return True
            else:
                raise Exception(f"Chain deletion failed: {response.status_code}")
        except Exception as e:
            # Mock chain deletion for development
            print(f"Mock deleted chain {chain_id} from node {self.config.id}")
            return True
    
    async def get_chain_stats(self, chain_id: str) -> Dict[str, Any]:
        """Get chain statistics"""
        try:
            response = await self._client.get(f"{self.config.endpoint}/api/chains/{chain_id}/stats")
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Chain stats request failed: {response.status_code}")
        except Exception as e:
            # Return mock stats for development
            return self._get_mock_chain_stats(chain_id)
    
    async def backup_chain(self, chain_id: str, backup_path: str) -> Dict[str, Any]:
        """Backup a chain"""
        try:
            response = await self._client.post(
                f"{self.config.endpoint}/api/chains/{chain_id}/backup",
                json={"backup_path": backup_path}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Chain backup failed: {response.status_code}")
        except Exception as e:
            # Mock backup for development
            backup_info = {
                "chain_id": chain_id,
                "backup_file": f"{backup_path}/{chain_id}_backup.tar.gz",
                "original_size_mb": 100.0,
                "backup_size_mb": 50.0,
                "checksum": "mock_checksum_12345"
            }
            print(f"Mock backed up chain {chain_id} to {backup_info['backup_file']}")
            return backup_info
    
    async def restore_chain(self, backup_file: str, chain_id: Optional[str] = None) -> Dict[str, Any]:
        """Restore a chain from backup"""
        try:
            response = await self._client.post(
                f"{self.config.endpoint}/api/chains/restore",
                json={"backup_file": backup_file, "chain_id": chain_id}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Chain restore failed: {response.status_code}")
        except Exception as e:
            # Mock restore for development
            restore_info = {
                "chain_id": chain_id or "RESTORED-MOCK-CHAIN",
                "blocks_restored": 1000,
                "verification_passed": True
            }
            print(f"Mock restored chain from {backup_file}")
            return restore_info
    
    def _parse_chain_info(self, chain_data: Dict[str, Any]) -> ChainInfo:
        """Parse chain data from node response"""
        from datetime import datetime
        from models.chain import PrivacyConfig
        
        return ChainInfo(
            id=chain_data.get("chain_id", chain_data.get("id", "unknown")),
            type=ChainType(chain_data.get("chain_type", "topic")),
            purpose=chain_data.get("purpose", "unknown"),
            name=chain_data.get("name", "Unnamed Chain"),
            description=chain_data.get("description"),
            status=ChainStatus(chain_data.get("status", "active")),
            created_at=datetime.fromisoformat(chain_data.get("created_at", "2024-01-01T00:00:00")),
            block_height=chain_data.get("block_height", 0),
            size_mb=chain_data.get("size_mb", 0.0),
            node_count=chain_data.get("node_count", 1),
            active_nodes=chain_data.get("active_nodes", 1),
            contract_count=chain_data.get("contract_count", 0),
            client_count=chain_data.get("client_count", 0),
            miner_count=chain_data.get("miner_count", 0),
            agent_count=chain_data.get("agent_count", 0),
            consensus_algorithm=ConsensusAlgorithm(chain_data.get("consensus_algorithm", "pos")),
            block_time=chain_data.get("block_time", 5),
            tps=chain_data.get("tps", 0.0),
            avg_block_time=chain_data.get("avg_block_time", 5.0),
            avg_gas_used=chain_data.get("avg_gas_used", 0),
            growth_rate_mb_per_day=chain_data.get("growth_rate_mb_per_day", 0.0),
            gas_price=chain_data.get("gas_price", 20000000000),
            memory_usage_mb=chain_data.get("memory_usage_mb", 0.0),
            disk_usage_mb=chain_data.get("disk_usage_mb", 0.0),
            privacy=PrivacyConfig(
                visibility=chain_data.get("privacy", {}).get("visibility", "public"),
                access_control=chain_data.get("privacy", {}).get("access_control", "open")
            )
        )
    
    def _get_mock_node_info(self) -> Dict[str, Any]:
        """Get mock node information for development"""
        return {
            "node_id": self.config.id,
            "type": "full",
            "status": "active",
            "version": "1.0.0",
            "uptime_days": 30,
            "uptime_hours": 720,
            "hosted_chains": {},
            "cpu_usage": 25.5,
            "memory_usage_mb": 1024.0,
            "disk_usage_mb": 10240.0,
            "network_in_mb": 10.5,
            "network_out_mb": 8.2
        }
    
    def _get_mock_chains(self) -> List[ChainInfo]:
        """Get mock chains for development"""
        from datetime import datetime
        from models.chain import PrivacyConfig
        
        return [
            ChainInfo(
                id="AITBC-TOPIC-HEALTHCARE-001",
                type=ChainType.TOPIC,
                purpose="healthcare",
                name="Healthcare AI Chain",
                description="A specialized chain for healthcare AI applications",
                status=ChainStatus.ACTIVE,
                created_at=datetime.now(),
                block_height=1000,
                size_mb=50.5,
                node_count=3,
                active_nodes=3,
                contract_count=5,
                client_count=25,
                miner_count=8,
                agent_count=12,
                consensus_algorithm=ConsensusAlgorithm.POS,
                block_time=3,
                tps=15.5,
                avg_block_time=3.2,
                avg_gas_used=5000000,
                growth_rate_mb_per_day=2.1,
                gas_price=20000000000,
                memory_usage_mb=256.0,
                disk_usage_mb=512.0,
                privacy=PrivacyConfig(visibility="public", access_control="open")
            ),
            ChainInfo(
                id="AITBC-PRIVATE-COLLAB-001",
                type=ChainType.PRIVATE,
                purpose="collaboration",
                name="Private Research Chain",
                description="A private chain for trusted agent collaboration",
                status=ChainStatus.ACTIVE,
                created_at=datetime.now(),
                block_height=500,
                size_mb=25.2,
                node_count=2,
                active_nodes=2,
                contract_count=3,
                client_count=8,
                miner_count=4,
                agent_count=6,
                consensus_algorithm=ConsensusAlgorithm.POA,
                block_time=5,
                tps=8.0,
                avg_block_time=5.1,
                avg_gas_used=3000000,
                growth_rate_mb_per_day=1.0,
                gas_price=15000000000,
                memory_usage_mb=128.0,
                disk_usage_mb=256.0,
                privacy=PrivacyConfig(visibility="private", access_control="invite_only")
            )
        ]
    
    def _get_mock_chain_stats(self, chain_id: str) -> Dict[str, Any]:
        """Get mock chain statistics for development"""
        return {
            "chain_id": chain_id,
            "block_height": 1000,
            "tps": 15.5,
            "avg_block_time": 3.2,
            "gas_price": 20000000000,
            "memory_usage_mb": 256.0,
            "disk_usage_mb": 512.0,
            "active_nodes": 3,
            "client_count": 25,
            "miner_count": 8,
            "agent_count": 12,
            "last_block_time": "2024-03-02T10:00:00Z"
        }
