"""
Core Agent class for AITBC network participation
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)


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

    def __init__(self, identity: AgentIdentity, capabilities: AgentCapabilities):
        self.identity = identity
        self.capabilities = capabilities
        self.registered = False
        self.reputation_score = 0.0
        self.earnings = 0.0

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
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Sign registration data
            signature = self.identity.sign_message(registration_data)
            registration_data["signature"] = signature

            # TODO: Submit to AITBC network registration endpoint
            # For now, simulate successful registration
            await asyncio.sleep(1)  # Simulate network call

            self.registered = True
            logger.info(f"Agent {self.identity.id} registered successfully")
            return True

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def get_reputation(self) -> Dict[str, float]:
        """Get agent reputation metrics"""
        # TODO: Fetch from reputation system
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
        # TODO: Fetch from blockchain/payment system
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
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Sign message
        signature = self.identity.sign_message(message)
        message["signature"] = signature

        # TODO: Send through AITBC agent messaging protocol
        logger.info(f"Message sent to {recipient_id}: {message_type}")
        return True

    async def receive_message(self, message: Dict[str, Any]) -> bool:
        """Process a received message from another agent"""
        # Verify signature
        if "signature" not in message:
            return False

        # TODO: Verify sender's signature
        # For now, just process the message
        logger.info(
            f"Received message from {message.get('from')}: {message.get('type')}"
        )
        return True

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
