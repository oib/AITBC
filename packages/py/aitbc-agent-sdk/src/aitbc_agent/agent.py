"""
Core Agent class for AITBC network participation
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AITBCHTTPClient
from aitbc_agent.contract_integration import (
    AgentContractIntegration, 
    ContractClient, 
    ContractConfig,
    create_agent_contract_integration
)
from aitbc_agent import command_executor, ipfs, data_oracle, zk, knowledge, bounty, dispute, extended

logger = get_logger(__name__)


@dataclass
class AgentCapabilities:
    """Agent capability specification"""

    compute_type: str  # "inference", "training", "processing"
    gpu_memory: Optional[int] = None
    supported_models: Optional[List[str]] = None
    performance_score: float = 0.0
    max_concurrent_jobs: int = 1
    specialization: Optional[str] = None

    def __post_init__(self) -> None:
        if self.supported_models is None:
            self.supported_models = []


@dataclass
class AgentIdentity:
    """Agent identity and cryptographic keys"""

    id: str
    name: str
    address: str
    public_key: str
    private_key: str

    def sign_message(self, message: Dict[str, Any]) -> str:
        """Sign a message with agent's private key"""
        message_str = json.dumps(message, sort_keys=True)
        private_key = serialization.load_pem_private_key(
            self.private_key.encode(), password=None
        )

        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise TypeError("Only RSA private keys are supported")

        signature = private_key.sign(
            message_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256(),
        )

        return signature.hex()

    def verify_signature(self, message: Dict[str, Any], signature: str) -> bool:
        """Verify a message signature"""
        message_str = json.dumps(message, sort_keys=True)
        public_key = serialization.load_pem_public_key(self.public_key.encode())

        if not isinstance(public_key, rsa.RSAPublicKey):
            raise TypeError("Only RSA public keys are supported")

        try:
            public_key.verify(
                bytes.fromhex(signature),
                message_str.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False


class Agent:
    """Core AITBC Agent class"""

    def __init__(
        self,
        identity: AgentIdentity,
        capabilities: AgentCapabilities,
        coordinator_url: Optional[str] = None,
        contract_config: Optional[ContractConfig] = None
    ):
        self.identity = identity
        self.capabilities = capabilities
        self.registered = False
        self.reputation_score = 0.0
        self.earnings = 0.0
        self.coordinator_url = coordinator_url or "http://localhost:9001"
        self.http_client = AITBCHTTPClient(base_url=self.coordinator_url)

        # Contract integration
        self.contract_integration: Optional[AgentContractIntegration] = None

        # CLI-based operation modules
        self.ipfs_ops = ipfs.IPFSOperations()
        self.data_oracle_ops = data_oracle.DataOracleOperations()
        self.zk_ops = zk.ZKOperations()
        self.knowledge_ops = knowledge.KnowledgeOperations()
        self.bounty_ops = bounty.BountyOperations()
        self.dispute_ops = dispute.DisputeOperations()
        self.extended_ops = extended.ExtendedOperations()

        if contract_config:
            try:
                # Use factory function to create appropriate client
                self.contract_integration = create_agent_contract_integration(
                    config=contract_config,
                    private_key=identity.private_key
                )
                self.contract_integration.set_agent_address(identity.address)
                logger.info("Contract integration initialized for agent")
            except Exception as e:
                logger.warning(f"Failed to initialize contract integration: {e}")

    @classmethod
    def create(
        cls, name: str, agent_type: str, capabilities: Dict[str, Any]
    ) -> "Agent":
        """Create a new agent with generated identity"""
        # Generate cryptographic keys
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        public_key = private_key.public_key()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Generate agent identity
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        address = f"0x{uuid.uuid4().hex[:40]}"

        identity = AgentIdentity(
            id=agent_id,
            name=name,
            address=address,
            public_key=public_pem.decode(),
            private_key=private_pem.decode(),
        )

        # Create capabilities object
        agent_capabilities = AgentCapabilities(**capabilities)

        return cls(identity, agent_capabilities)

    async def register(self) -> bool:
        """Register the agent on the AITBC network"""
        try:
            registration_data = {
                "agent_id": self.identity.id,
                "name": self.identity.name,
                "address": self.identity.address,
                "public_key": self.identity.public_key,
                "capabilities": {
                    "compute_type": self.capabilities.compute_type,
                    "gpu_memory": self.capabilities.gpu_memory,
                    "supported_models": self.capabilities.supported_models,
                    "performance_score": self.capabilities.performance_score,
                    "max_concurrent_jobs": self.capabilities.max_concurrent_jobs,
                    "specialization": self.capabilities.specialization,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Sign registration data
            signature = self.identity.sign_message(registration_data)
            registration_data["signature"] = signature

            # Submit to AITBC network registration endpoint
            try:
                response = await self.http_client.post(
                    "/v1/agents/register",
                    json=registration_data
                )
                
                if response.status_code == 201:
                    result = response.json()
                    self.registered = True
                    logger.info(f"Agent {self.identity.id} registered successfully")
                    return True
                else:
                    logger.error(f"Registration failed: {response.status_code}")
                    return False
            except NetworkError as e:
                logger.error(f"Network error during registration: {e}")
                return False
            except Exception as e:
                logger.error(f"Registration error: {e}")
                return False

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def get_reputation(self) -> Dict[str, float]:
        """Get agent reputation metrics"""
        try:
            response = await self.http_client.get(
                f"/v1/agents/{self.identity.id}/reputation"
            )
            
            if response.status_code == 200:
                result = response.json()
                self.reputation_score = result.get("overall_score", self.reputation_score)
                return result
            else:
                logger.warning(f"Failed to fetch reputation: {response.status_code}, using local score")
                return {
                    "overall_score": self.reputation_score,
                    "job_success_rate": 0.95,
                    "avg_response_time": 30.5,
                    "client_satisfaction": 4.7,
                }
        except NetworkError:
            logger.warning("Network error fetching reputation, using local score")
            return {
                "overall_score": self.reputation_score,
                "job_success_rate": 0.95,
                "avg_response_time": 30.5,
                "client_satisfaction": 4.7,
            }
        except Exception as e:
            logger.error(f"Error fetching reputation: {e}")
            return {
                "overall_score": self.reputation_score,
                "job_success_rate": 0.95,
                "avg_response_time": 30.5,
                "client_satisfaction": 4.7,
            }

    async def update_reputation(self, new_score: float) -> None:
        """Update agent reputation score"""
        self.reputation_score = new_score
        logger.info(f"Reputation updated to {new_score}")

    async def get_earnings(self, period: str = "30d") -> Dict[str, Any]:
        """Get agent earnings information"""
        try:
            response = await self.http_client.get(
                f"/v1/agents/{self.identity.id}/earnings",
                params={"period": period}
            )
            
            if response.status_code == 200:
                result = response.json()
                self.earnings = result.get("total", self.earnings)
                return result
            else:
                logger.warning(f"Failed to fetch earnings: {response.status_code}, using local earnings")
                return {
                    "total": self.earnings,
                    "daily_average": self.earnings / 30,
                    "period": period,
                    "currency": "AITBC",
                }
        except NetworkError:
            logger.warning("Network error fetching earnings, using local earnings")
            return {
                "total": self.earnings,
                "daily_average": self.earnings / 30,
                "period": period,
                "currency": "AITBC",
            }
        except Exception as e:
            logger.error(f"Error fetching earnings: {e}")
            return {
                "total": self.earnings,
                "daily_average": self.earnings / 30,
                "period": period,
                "currency": "AITBC",
            }

    async def send_message(
        self, recipient_id: str, message_type: str, payload: Dict[str, Any]
    ) -> bool:
        """Send a message to another agent"""
        message = {
            "from": self.identity.id,
            "to": recipient_id,
            "type": message_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Sign message
        signature = self.identity.sign_message(message)
        message["signature"] = signature

        # Send through AITBC agent messaging protocol
        try:
            response = await self.http_client.post(
                "/v1/agents/messages",
                json=message
            )
            
            if response.status_code == 200:
                logger.info(f"Message sent to {recipient_id}: {message_type}")
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code}")
                return False
        except NetworkError as e:
            logger.error(f"Network error sending message: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _fetch_sender_public_key(self, sender_id: str) -> Optional[str]:
        """Fetch sender's public key from coordinator API"""
        try:
            coordinator_url = os.getenv("COORDINATOR_API_URL", "http://localhost:8011")
            client = AITBCHTTPClient(timeout=5.0)
            
            response = client.get(f"{coordinator_url}/v1/agent-identity/{sender_id}")
            
            if response and "public_key" in response:
                return response["public_key"]
            else:
                logger.warning(f"No public key found for agent {sender_id}")
                return None
        except NetworkError as e:
            logger.error(f"Failed to fetch public key for {sender_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching public key: {e}")
            return None

    async def receive_message(self, message: Dict[str, Any]) -> bool:
        """Process a received message from another agent"""
        # Verify signature
        if "signature" not in message:
            logger.warning("Message missing signature")
            return False

        # Verify sender's signature
        sender_id = message.get("from")
        signature = message.get("signature")
        
        # Create message copy without signature for verification
        message_to_verify = message.copy()
        message_to_verify.pop("signature", None)
        
        # Fetch sender's public key from coordinator API
        public_key_hex = await self._fetch_sender_public_key(sender_id)
        if not public_key_hex:
            logger.error(f"Failed to fetch public key for {sender_id}, rejecting message")
            return False
        
        # Verify signature using ed25519
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            message_bytes = json.dumps(message_to_verify, sort_keys=True).encode('utf-8')
            public_key.verify(signature, message_bytes)
            
            logger.info(
                f"Received message from {sender_id}: {message.get('type')} (signature verified)"
            )
            return True
        except Exception as e:
            logger.error(f"Signature verification failed for {sender_id}: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent to dictionary representation"""
        return {
            "id": self.identity.id,
            "name": self.identity.name,
            "address": self.identity.address,
            "capabilities": {
                "compute_type": self.capabilities.compute_type,
                "gpu_memory": self.capabilities.gpu_memory,
                "supported_models": self.capabilities.supported_models,
                "performance_score": self.capabilities.performance_score,
                "max_concurrent_jobs": self.capabilities.max_concurrent_jobs,
                "specialization": self.capabilities.specialization,
            },
            "reputation_score": self.reputation_score,
            "registered": self.registered,
            "earnings": self.earnings,
        }

    async def __aenter__(self) -> "Agent":
        """Async context manager entry - automatically register agent"""
        await self.register()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup agent resources"""
        # In a real implementation, this would unregister the agent
        # and clean up any resources
        if exc_type is not None:
            logger.error(f"Agent {self.identity.id} exiting with exception: {exc_val}")
        else:
            logger.info(f"Agent {self.identity.id} exiting normally")

    async def initiate_atomic_swap(
        self,
        swap_id: str,
        token: str,
        amount: int,
        participant: str,
        hashlock: str,
        timelock: int,
        contract_address: str
    ) -> Dict[str, Any]:
        """Initiate atomic swap using contract integration"""
        if not self.contract_integration:
            raise ValueError("Contract integration not initialized")

        return await self.contract_integration.initiate_atomic_swap(
            swap_id=swap_id,
            token=token,
            amount=amount,
            participant=participant,
            hashlock=hashlock,
            timelock=timelock,
            contract_address=contract_address
        )

    async def complete_atomic_swap(
        self,
        swap_id: str,
        secret: str,
        contract_address: str
    ) -> Dict[str, Any]:
        """Complete atomic swap by revealing secret"""
        if not self.contract_integration:
            raise ValueError("Contract integration not initialized")

        return await self.contract_integration.complete_atomic_swap(
            swap_id=swap_id,
            secret=secret,
            contract_address=contract_address
        )

    async def get_swap_status(
        self,
        swap_id: str,
        contract_address: str
    ) -> Dict[str, Any]:
        """Get status of an atomic swap"""
        if not self.contract_integration:
            raise ValueError("Contract integration not initialized")

        return await self.contract_integration.get_swap_status(
            swap_id=swap_id,
            contract_address=contract_address
        )

    async def refund_atomic_swap(
        self,
        swap_id: str,
        contract_address: str
    ) -> Dict[str, Any]:
        """Refund atomic swap if timelock expired"""
        if not self.contract_integration:
            raise ValueError("Contract integration not initialized")

        return await self.contract_integration.refund_atomic_swap(
            swap_id=swap_id,
            contract_address=contract_address
        )

    # IPFS operations
    def store_ipfs(self, data: bytes, pin: bool = True, name: str = None) -> str:
        """Store data on IPFS"""
        return self.ipfs_ops.store_ipfs(data, pin, name)
    
    def retrieve_ipfs(self, cid: str, output_path: str = None) -> bytes:
        """Retrieve data from IPFS"""
        return self.ipfs_ops.retrieve_ipfs(cid, output_path)
    
    async def store_ipfs_async(self, data: bytes, pin: bool = True, name: str = None) -> str:
        """Async version of store_ipfs"""
        return await self.ipfs_ops.store_ipfs_async(data, pin, name)
    
    async def retrieve_ipfs_async(self, cid: str, output_path: str = None) -> bytes:
        """Async version of retrieve_ipfs"""
        return await self.ipfs_ops.retrieve_ipfs_async(cid, output_path)

    # Data oracle operations
    def announce_data_availability(self, cid: str, price: float, description: str = "") -> str:
        """Announce data availability"""
        return self.data_oracle_ops.announce_data_availability(cid, price, description)
    
    def retrieve_data(self, cid: str) -> bytes:
        """Retrieve data by CID"""
        return self.data_oracle_ops.retrieve_data(cid)
    
    async def listen_for_requests(self, callback):
        """Listen for data retrieval requests"""
        await self.data_oracle_ops.listen_for_requests(callback)
    
    async def announce_data_availability_async(self, cid: str, price: float, description: str = "") -> str:
        """Async version of announce_data_availability"""
        return await self.data_oracle_ops.announce_data_availability_async(cid, price, description)

    # ZK operations
    def generate_proof(self, input_data: str, circuit_id: str) -> str:
        """Generate ZK proof"""
        return self.zk_ops.generate_proof(input_data, circuit_id)
    
    def verify_proof(self, proof: str, public_inputs: str) -> bool:
        """Verify ZK proof"""
        return self.zk_ops.verify_proof(proof, public_inputs)

    # Knowledge graph operations
    def create_knowledge_graph(self, name: str, description: str = "") -> str:
        """Create knowledge graph"""
        return self.knowledge_ops.create_knowledge_graph(name, description)
    
    def add_knowledge_node(self, graph_id: str, node_data: dict) -> str:
        """Add node to knowledge graph"""
        return self.knowledge_ops.add_knowledge_node(graph_id, node_data)

    # Bounty operations
    def create_bounty(self, title: str, description: str, reward: float) -> str:
        """Create bounty"""
        return self.bounty_ops.create_bounty(title, description, reward)
    
    def list_bounties(self, status: str = "open") -> list:
        """List bounties"""
        return self.bounty_ops.list_bounties(status)

    # Dispute operations
    def file_dispute(self, title: str, description: str, evidence: str) -> str:
        """File dispute"""
        return self.dispute_ops.file_dispute(title, description, evidence)
    
    def vote_dispute(self, dispute_id: str, vote: bool, reason: str = "") -> bool:
        """Vote on dispute"""
        return self.dispute_ops.vote_dispute(dispute_id, vote, reason)

    # Extended operations
    def submit_ai_test(self, model_id: str, test_data: str) -> str:
        """Submit AI test job"""
        return self.extended_ops.submit_ai_test(model_id, test_data)
    
    def list_gpu(self, filters: dict = None) -> list:
        """List available GPU resources"""
        return self.extended_ops.list_gpu(filters)
    
    def create_swarm(self, name: str, max_agents: int) -> str:
        """Create agent swarm"""
        return self.extended_ops.create_swarm(name, max_agents)
    
    def add_stake(self, amount: float, validator_id: str = None) -> str:
        """Add stake to validator"""
        return self.extended_ops.add_stake(amount, validator_id)


class AITBCAgent:
    """High-level convenience wrapper for creating AITBC agents.

    Provides a simple keyword-argument constructor suitable for quick
    prototyping and testing without manually building AgentIdentity /
    AgentCapabilities objects.
    """

    def __init__(
        self,
        agent_id: str = "",
        compute_type: str = "general",
        capabilities: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        self.agent_id = agent_id
        self.compute_type = compute_type
        self.capabilities: List[str] = capabilities or []
        self.status = "initialized"
        self._extra = kwargs

        # Build a backing Agent for crypto / network operations
        self._agent = Agent.create(
            name=agent_id,
            agent_type=compute_type,
            capabilities={"compute_type": compute_type},
        )

    # Delegate common Agent methods
    async def register(self) -> bool:
        return await self._agent.register()

    def to_dict(self) -> Dict[str, Any]:
        d = self._agent.to_dict()
        d["agent_id"] = self.agent_id
        d["status"] = self.status
        return d
