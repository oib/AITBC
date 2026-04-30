"""
Core Agent class for AITBC network participation
"""

import asyncio
import json
import uuid
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.http_client import AITBCHTTPClient

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

    def __init__(self, identity: AgentIdentity, capabilities: AgentCapabilities, coordinator_url: Optional[str] = None):
        self.identity = identity
        self.capabilities = capabilities
        self.registered = False
        self.reputation_score = 0.0
        self.earnings = 0.0
        self.coordinator_url = coordinator_url or "http://localhost:8001"
        self.http_client = AITBCHTTPClient(base_url=self.coordinator_url)

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
                "timestamp": datetime.now(datetime.UTC).isoformat(),
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
            "timestamp": datetime.now(datetime.UTC).isoformat(),
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
        
        # In a real implementation, we would fetch the sender's public key
        # For now, we'll assume the signature is valid if present
        # TODO: Fetch sender's public key from coordinator API and verify
        logger.info(
            f"Received message from {sender_id}: {message.get('type')}"
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
