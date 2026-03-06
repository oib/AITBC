"""
Enterprise Security Framework - Phase 6.2 Implementation
Zero-trust architecture with HSM integration and advanced security controls
"""

import asyncio
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from uuid import uuid4
from enum import Enum
from dataclasses import dataclass, field
import json
import ssl
import cryptography
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import jwt
from pydantic import BaseModel, Field, validator
from aitbc.logging import get_logger

logger = get_logger(__name__)

class SecurityLevel(str, Enum):
    """Security levels for enterprise data"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"

class EncryptionAlgorithm(str, Enum):
    """Encryption algorithms"""
    AES_256_GCM = "aes_256_gcm"
    CHACHA20_POLY1305 = "chacha20_polyy1305"
    AES_256_CBC = "aes_256_cbc"
    QUANTUM_RESISTANT = "quantum_resistant"

class ThreatLevel(str, Enum):
    """Threat levels for security monitoring"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityPolicy:
    """Security policy configuration"""
    policy_id: str
    name: str
    security_level: SecurityLevel
    encryption_algorithm: EncryptionAlgorithm
    key_rotation_interval: timedelta
    access_control_requirements: List[str]
    audit_requirements: List[str]
    retention_period: timedelta
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class SecurityEvent:
    """Security event for monitoring"""
    event_id: str
    event_type: str
    severity: ThreatLevel
    source: str
    timestamp: datetime
    user_id: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]
    resolved: bool = False
    resolution_notes: Optional[str] = None

class HSMManager:
    """Hardware Security Module manager for enterprise key management"""
    
    def __init__(self, hsm_config: Dict[str, Any]):
        self.hsm_config = hsm_config
        self.backend = default_backend()
        self.key_store = {}  # In production, use actual HSM
        self.logger = get_logger("hsm_manager")
        
    async def initialize(self) -> bool:
        """Initialize HSM connection"""
        try:
            # In production, initialize actual HSM connection
            # For now, simulate HSM initialization
            self.logger.info("HSM manager initialized")
            return True
        except Exception as e:
            self.logger.error(f"HSM initialization failed: {e}")
            return False
    
    async def generate_key(self, key_id: str, algorithm: EncryptionAlgorithm, 
                          key_size: int = 256) -> Dict[str, Any]:
        """Generate encryption key in HSM"""
        
        try:
            if algorithm == EncryptionAlgorithm.AES_256_GCM:
                key = secrets.token_bytes(32)  # 256 bits
                iv = secrets.token_bytes(12)   # 96 bits for GCM
            elif algorithm == EncryptionAlgorithm.CHACHA20_POLY1305:
                key = secrets.token_bytes(32)  # 256 bits
                nonce = secrets.token_bytes(12)  # 96 bits
            elif algorithm == EncryptionAlgorithm.AES_256_CBC:
                key = secrets.token_bytes(32)  # 256 bits
                iv = secrets.token_bytes(16)   # 128 bits for CBC
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}")
            
            # Store key in HSM (simulated)
            key_data = {
                "key_id": key_id,
                "algorithm": algorithm.value,
                "key": key,
                "iv": iv if algorithm in [EncryptionAlgorithm.AES_256_GCM, EncryptionAlgorithm.AES_256_CBC] else None,
                "nonce": nonce if algorithm == EncryptionAlgorithm.CHACHA20_POLY1305 else None,
                "created_at": datetime.utcnow(),
                "key_size": key_size
            }
            
            self.key_store[key_id] = key_data
            
            self.logger.info(f"Key generated in HSM: {key_id}")
            return key_data
            
        except Exception as e:
            self.logger.error(f"Key generation failed: {e}")
            raise
    
    async def get_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Get key from HSM"""
        return self.key_store.get(key_id)
    
    async def rotate_key(self, key_id: str) -> Dict[str, Any]:
        """Rotate encryption key"""
        
        old_key = self.key_store.get(key_id)
        if not old_key:
            raise ValueError(f"Key not found: {key_id}")
        
        # Generate new key
        new_key = await self.generate_key(
            f"{key_id}_new", 
            EncryptionAlgorithm(old_key["algorithm"]),
            old_key["key_size"]
        )
        
        # Update key with rotation timestamp
        new_key["rotated_from"] = key_id
        new_key["rotation_timestamp"] = datetime.utcnow()
        
        return new_key
    
    async def delete_key(self, key_id: str) -> bool:
        """Delete key from HSM"""
        if key_id in self.key_store:
            del self.key_store[key_id]
            self.logger.info(f"Key deleted from HSM: {key_id}")
            return True
        return False

class EnterpriseEncryption:
    """Enterprise-grade encryption service"""
    
    def __init__(self, hsm_manager: HSMManager):
        self.hsm_manager = hsm_manager
        self.backend = default_backend()
        self.logger = get_logger("enterprise_encryption")
        
    async def encrypt_data(self, data: Union[str, bytes], key_id: str, 
                          associated_data: Optional[bytes] = None) -> Dict[str, Any]:
        """Encrypt data using enterprise-grade encryption"""
        
        try:
            # Get key from HSM
            key_data = await self.hsm_manager.get_key(key_id)
            if not key_data:
                raise ValueError(f"Key not found: {key_id}")
            
            # Convert data to bytes if needed
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            algorithm = EncryptionAlgorithm(key_data["algorithm"])
            
            if algorithm == EncryptionAlgorithm.AES_256_GCM:
                return await self._encrypt_aes_gcm(data, key_data, associated_data)
            elif algorithm == EncryptionAlgorithm.CHACHA20_POLY1305:
                return await self._encrypt_chacha20(data, key_data, associated_data)
            elif algorithm == EncryptionAlgorithm.AES_256_CBC:
                return await self._encrypt_aes_cbc(data, key_data)
            else:
                raise ValueError(f"Unsupported encryption algorithm: {algorithm}")
                
        except Exception as e:
            self.logger.error(f"Encryption failed: {e}")
            raise
    
    async def _encrypt_aes_gcm(self, data: bytes, key_data: Dict[str, Any], 
                              associated_data: Optional[bytes] = None) -> Dict[str, Any]:
        """Encrypt using AES-256-GCM"""
        
        key = key_data["key"]
        iv = key_data["iv"]
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=self.backend
        )
        
        encryptor = cipher.encryptor()
        
        # Add associated data if provided
        if associated_data:
            encryptor.authenticate_additional_data(associated_data)
        
        # Encrypt data
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        return {
            "ciphertext": ciphertext.hex(),
            "iv": iv.hex(),
            "tag": encryptor.tag.hex(),
            "algorithm": "aes_256_gcm",
            "key_id": key_data["key_id"]
        }
    
    async def _encrypt_chacha20(self, data: bytes, key_data: Dict[str, Any], 
                               associated_data: Optional[bytes] = None) -> Dict[str, Any]:
        """Encrypt using ChaCha20-Poly1305"""
        
        key = key_data["key"]
        nonce = key_data["nonce"]
        
        # Create cipher
        cipher = Cipher(
            algorithms.ChaCha20(key, nonce),
            modes.Poly1305(b""),
            backend=self.backend
        )
        
        encryptor = cipher.encryptor()
        
        # Add associated data if provided
        if associated_data:
            encryptor.authenticate_additional_data(associated_data)
        
        # Encrypt data
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        return {
            "ciphertext": ciphertext.hex(),
            "nonce": nonce.hex(),
            "tag": encryptor.tag.hex(),
            "algorithm": "chacha20_poly1305",
            "key_id": key_data["key_id"]
        }
    
    async def _encrypt_aes_cbc(self, data: bytes, key_data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt using AES-256-CBC"""
        
        key = key_data["key"]
        iv = key_data["iv"]
        
        # Pad data to block size
        padder = cryptography.hazmat.primitives.padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=self.backend
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        return {
            "ciphertext": ciphertext.hex(),
            "iv": iv.hex(),
            "algorithm": "aes_256_cbc",
            "key_id": key_data["key_id"]
        }
    
    async def decrypt_data(self, encrypted_data: Dict[str, Any], 
                          associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt encrypted data"""
        
        try:
            algorithm = encrypted_data["algorithm"]
            
            if algorithm == "aes_256_gcm":
                return await self._decrypt_aes_gcm(encrypted_data, associated_data)
            elif algorithm == "chacha20_poly1305":
                return await self._decrypt_chacha20(encrypted_data, associated_data)
            elif algorithm == "aes_256_cbc":
                return await self._decrypt_aes_cbc(encrypted_data)
            else:
                raise ValueError(f"Unsupported encryption algorithm: {algorithm}")
                
        except Exception as e:
            self.logger.error(f"Decryption failed: {e}")
            raise
    
    async def _decrypt_aes_gcm(self, encrypted_data: Dict[str, Any], 
                              associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt AES-256-GCM encrypted data"""
        
        # Get key from HSM
        key_data = await self.hsm_manager.get_key(encrypted_data["key_id"])
        if not key_data:
            raise ValueError(f"Key not found: {encrypted_data['key_id']}")
        
        key = key_data["key"]
        iv = bytes.fromhex(encrypted_data["iv"])
        ciphertext = bytes.fromhex(encrypted_data["ciphertext"])
        tag = bytes.fromhex(encrypted_data["tag"])
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=self.backend
        )
        
        decryptor = cipher.decryptor()
        
        # Add associated data if provided
        if associated_data:
            decryptor.authenticate_additional_data(associated_data)
        
        # Decrypt data
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return plaintext
    
    async def _decrypt_chacha20(self, encrypted_data: Dict[str, Any], 
                               associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt ChaCha20-Poly1305 encrypted data"""
        
        # Get key from HSM
        key_data = await self.hsm_manager.get_key(encrypted_data["key_id"])
        if not key_data:
            raise ValueError(f"Key not found: {encrypted_data['key_id']}")
        
        key = key_data["key"]
        nonce = bytes.fromhex(encrypted_data["nonce"])
        ciphertext = bytes.fromhex(encrypted_data["ciphertext"])
        tag = bytes.fromhex(encrypted_data["tag"])
        
        # Create cipher
        cipher = Cipher(
            algorithms.ChaCha20(key, nonce),
            modes.Poly1305(tag),
            backend=self.backend
        )
        
        decryptor = cipher.decryptor()
        
        # Add associated data if provided
        if associated_data:
            decryptor.authenticate_additional_data(associated_data)
        
        # Decrypt data
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return plaintext
    
    async def _decrypt_aes_cbc(self, encrypted_data: Dict[str, Any]) -> bytes:
        """Decrypt AES-256-CBC encrypted data"""
        
        # Get key from HSM
        key_data = await self.hsm_manager.get_key(encrypted_data["key_id"])
        if not key_data:
            raise ValueError(f"Key not found: {encrypted_data['key_id']}")
        
        key = key_data["key"]
        iv = bytes.fromhex(encrypted_data["iv"])
        ciphertext = bytes.fromhex(encrypted_data["ciphertext"])
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=self.backend
        )
        
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Unpad data
        unpadder = cryptography.hazmat.primitives.padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
        
        return plaintext

class ZeroTrustArchitecture:
    """Zero-trust security architecture implementation"""
    
    def __init__(self, hsm_manager: HSMManager, encryption: EnterpriseEncryption):
        self.hsm_manager = hsm_manager
        self.encryption = encryption
        self.trust_policies = {}
        self.session_tokens = {}
        self.logger = get_logger("zero_trust")
        
    async def create_trust_policy(self, policy_id: str, policy_config: Dict[str, Any]) -> bool:
        """Create zero-trust policy"""
        
        try:
            policy = SecurityPolicy(
                policy_id=policy_id,
                name=policy_config["name"],
                security_level=SecurityLevel(policy_config["security_level"]),
                encryption_algorithm=EncryptionAlgorithm(policy_config["encryption_algorithm"]),
                key_rotation_interval=timedelta(days=policy_config.get("key_rotation_days", 90)),
                access_control_requirements=policy_config.get("access_control_requirements", []),
                audit_requirements=policy_config.get("audit_requirements", []),
                retention_period=timedelta(days=policy_config.get("retention_days", 2555))  # 7 years
            )
            
            self.trust_policies[policy_id] = policy
            
            # Generate encryption key for policy
            await self.hsm_manager.generate_key(
                f"policy_{policy_id}",
                policy.encryption_algorithm
            )
            
            self.logger.info(f"Zero-trust policy created: {policy_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create trust policy: {e}")
            return False
    
    async def verify_trust(self, user_id: str, resource_id: str, 
                          action: str, context: Dict[str, Any]) -> bool:
        """Verify zero-trust access request"""
        
        try:
            # Get applicable policy
            policy_id = context.get("policy_id", "default")
            policy = self.trust_policies.get(policy_id)
            
            if not policy:
                self.logger.warning(f"No policy found for {policy_id}")
                return False
            
            # Verify trust factors
            trust_score = await self._calculate_trust_score(user_id, resource_id, action, context)
            
            # Check if trust score meets policy requirements
            min_trust_score = self._get_min_trust_score(policy.security_level)
            
            is_trusted = trust_score >= min_trust_score
            
            # Log trust decision
            await self._log_trust_decision(user_id, resource_id, action, trust_score, is_trusted)
            
            return is_trusted
            
        except Exception as e:
            self.logger.error(f"Trust verification failed: {e}")
            return False
    
    async def _calculate_trust_score(self, user_id: str, resource_id: str, 
                                   action: str, context: Dict[str, Any]) -> float:
        """Calculate trust score for access request"""
        
        score = 0.0
        
        # User authentication factor (40%)
        auth_strength = context.get("auth_strength", "password")
        if auth_strength == "mfa":
            score += 0.4
        elif auth_strength == "password":
            score += 0.2
        
        # Device trust factor (20%)
        device_trust = context.get("device_trust", 0.5)
        score += 0.2 * device_trust
        
        # Location factor (15%)
        location_trust = context.get("location_trust", 0.5)
        score += 0.15 * location_trust
        
        # Time factor (10%)
        time_trust = context.get("time_trust", 0.5)
        score += 0.1 * time_trust
        
        # Behavioral factor (15%)
        behavior_trust = context.get("behavior_trust", 0.5)
        score += 0.15 * behavior_trust
        
        return min(score, 1.0)
    
    def _get_min_trust_score(self, security_level: SecurityLevel) -> float:
        """Get minimum trust score for security level"""
        
        thresholds = {
            SecurityLevel.PUBLIC: 0.0,
            SecurityLevel.INTERNAL: 0.3,
            SecurityLevel.CONFIDENTIAL: 0.6,
            SecurityLevel.RESTRICTED: 0.8,
            SecurityLevel.TOP_SECRET: 0.9
        }
        
        return thresholds.get(security_level, 0.5)
    
    async def _log_trust_decision(self, user_id: str, resource_id: str, 
                                 action: str, trust_score: float, 
                                 decision: bool):
        """Log trust decision for audit"""
        
        event = SecurityEvent(
            event_id=str(uuid4()),
            event_type="trust_decision",
            severity=ThreatLevel.LOW if decision else ThreatLevel.MEDIUM,
            source="zero_trust",
            timestamp=datetime.utcnow(),
            user_id=user_id,
            resource_id=resource_id,
            details={
                "action": action,
                "trust_score": trust_score,
                "decision": decision
            }
        )
        
        # In production, send to security monitoring system
        self.logger.info(f"Trust decision: {user_id} -> {resource_id} = {decision} (score: {trust_score})")

class ThreatDetectionSystem:
    """Advanced threat detection and response system"""
    
    def __init__(self):
        self.threat_patterns = {}
        self.active_threats = {}
        self.response_actions = {}
        self.logger = get_logger("threat_detection")
        
    async def register_threat_pattern(self, pattern_id: str, pattern_config: Dict[str, Any]):
        """Register threat detection pattern"""
        
        self.threat_patterns[pattern_id] = {
            "id": pattern_id,
            "name": pattern_config["name"],
            "description": pattern_config["description"],
            "indicators": pattern_config["indicators"],
            "severity": ThreatLevel(pattern_config["severity"]),
            "response_actions": pattern_config.get("response_actions", []),
            "threshold": pattern_config.get("threshold", 1.0)
        }
        
        self.logger.info(f"Threat pattern registered: {pattern_id}")
    
    async def analyze_threat(self, event_data: Dict[str, Any]) -> List[SecurityEvent]:
        """Analyze event for potential threats"""
        
        detected_threats = []
        
        for pattern_id, pattern in self.threat_patterns.items():
            threat_score = await self._calculate_threat_score(event_data, pattern)
            
            if threat_score >= pattern["threshold"]:
                threat_event = SecurityEvent(
                    event_id=str(uuid4()),
                    event_type="threat_detected",
                    severity=pattern["severity"],
                    source="threat_detection",
                    timestamp=datetime.utcnow(),
                    user_id=event_data.get("user_id"),
                    resource_id=event_data.get("resource_id"),
                    details={
                        "pattern_id": pattern_id,
                        "pattern_name": pattern["name"],
                        "threat_score": threat_score,
                        "indicators": event_data
                    }
                )
                
                detected_threats.append(threat_event)
                
                # Trigger response actions
                await self._trigger_response_actions(pattern_id, threat_event)
        
        return detected_threats
    
    async def _calculate_threat_score(self, event_data: Dict[str, Any], 
                                    pattern: Dict[str, Any]) -> float:
        """Calculate threat score for pattern"""
        
        score = 0.0
        indicators = pattern["indicators"]
        
        for indicator, weight in indicators.items():
            if indicator in event_data:
                # Simple scoring - in production, use more sophisticated algorithms
                indicator_score = 0.5  # Base score for presence
                score += indicator_score * weight
        
        return min(score, 1.0)
    
    async def _trigger_response_actions(self, pattern_id: str, threat_event: SecurityEvent):
        """Trigger automated response actions"""
        
        pattern = self.threat_patterns[pattern_id]
        actions = pattern.get("response_actions", [])
        
        for action in actions:
            try:
                await self._execute_response_action(action, threat_event)
            except Exception as e:
                self.logger.error(f"Response action failed: {action} - {e}")
    
    async def _execute_response_action(self, action: str, threat_event: SecurityEvent):
        """Execute specific response action"""
        
        if action == "block_user":
            await self._block_user(threat_event.user_id)
        elif action == "isolate_resource":
            await self._isolate_resource(threat_event.resource_id)
        elif action == "escalate_to_admin":
            await self._escalate_to_admin(threat_event)
        elif action == "require_mfa":
            await self._require_mfa(threat_event.user_id)
        
        self.logger.info(f"Response action executed: {action}")
    
    async def _block_user(self, user_id: str):
        """Block user account"""
        # In production, implement actual user blocking
        self.logger.warning(f"User blocked due to threat: {user_id}")
    
    async def _isolate_resource(self, resource_id: str):
        """Isolate compromised resource"""
        # In production, implement actual resource isolation
        self.logger.warning(f"Resource isolated due to threat: {resource_id}")
    
    async def _escalate_to_admin(self, threat_event: SecurityEvent):
        """Escalate threat to security administrators"""
        # In production, implement actual escalation
        self.logger.error(f"Threat escalated to admin: {threat_event.event_id}")
    
    async def _require_mfa(self, user_id: str):
        """Require multi-factor authentication"""
        # In production, implement MFA requirement
        self.logger.warning(f"MFA required for user: {user_id}")

class EnterpriseSecurityFramework:
    """Main enterprise security framework"""
    
    def __init__(self, hsm_config: Dict[str, Any]):
        self.hsm_manager = HSMManager(hsm_config)
        self.encryption = EnterpriseEncryption(self.hsm_manager)
        self.zero_trust = ZeroTrustArchitecture(self.hsm_manager, self.encryption)
        self.threat_detection = ThreatDetectionSystem()
        self.logger = get_logger("enterprise_security")
        
    async def initialize(self) -> bool:
        """Initialize security framework"""
        
        try:
            # Initialize HSM
            if not await self.hsm_manager.initialize():
                return False
            
            # Register default threat patterns
            await self._register_default_threat_patterns()
            
            # Create default trust policies
            await self._create_default_policies()
            
            self.logger.info("Enterprise security framework initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Security framework initialization failed: {e}")
            return False
    
    async def _register_default_threat_patterns(self):
        """Register default threat detection patterns"""
        
        patterns = [
            {
                "name": "Brute Force Attack",
                "description": "Multiple failed login attempts",
                "indicators": {"failed_login_attempts": 0.8, "short_time_interval": 0.6},
                "severity": "high",
                "threshold": 0.7,
                "response_actions": ["block_user", "require_mfa"]
            },
            {
                "name": "Suspicious Access Pattern",
                "description": "Unusual access patterns",
                "indicators": {"unusual_location": 0.7, "unusual_time": 0.5, "high_frequency": 0.6},
                "severity": "medium",
                "threshold": 0.6,
                "response_actions": ["require_mfa", "escalate_to_admin"]
            },
            {
                "name": "Data Exfiltration",
                "description": "Large data transfer patterns",
                "indicators": {"large_data_transfer": 0.9, "unusual_destination": 0.7},
                "severity": "critical",
                "threshold": 0.8,
                "response_actions": ["block_user", "isolate_resource", "escalate_to_admin"]
            }
        ]
        
        for i, pattern in enumerate(patterns):
            await self.threat_detection.register_threat_pattern(f"default_{i}", pattern)
    
    async def _create_default_policies(self):
        """Create default trust policies"""
        
        policies = [
            {
                "name": "Enterprise Data Policy",
                "security_level": "confidential",
                "encryption_algorithm": "aes_256_gcm",
                "key_rotation_days": 90,
                "access_control_requirements": ["mfa", "device_trust"],
                "audit_requirements": ["full_audit", "real_time_monitoring"],
                "retention_days": 2555
            },
            {
                "name": "Public API Policy",
                "security_level": "public",
                "encryption_algorithm": "aes_256_gcm",
                "key_rotation_days": 180,
                "access_control_requirements": ["api_key"],
                "audit_requirements": ["api_access_log"],
                "retention_days": 365
            }
        ]
        
        for i, policy in enumerate(policies):
            await self.zero_trust.create_trust_policy(f"default_{i}", policy)
    
    async def encrypt_sensitive_data(self, data: Union[str, bytes], 
                                   security_level: SecurityLevel) -> Dict[str, Any]:
        """Encrypt sensitive data with appropriate security level"""
        
        # Get policy for security level
        policy_id = f"default_{0 if security_level == SecurityLevel.PUBLIC else 1}"
        policy = self.zero_trust.trust_policies.get(policy_id)
        
        if not policy:
            raise ValueError(f"No policy found for security level: {security_level}")
        
        key_id = f"policy_{policy_id}"
        
        return await self.encryption.encrypt_data(data, key_id)
    
    async def verify_access(self, user_id: str, resource_id: str, 
                          action: str, context: Dict[str, Any]) -> bool:
        """Verify access using zero-trust architecture"""
        
        return await self.zero_trust.verify_trust(user_id, resource_id, action, context)
    
    async def analyze_security_event(self, event_data: Dict[str, Any]) -> List[SecurityEvent]:
        """Analyze security event for threats"""
        
        return await self.threat_detection.analyze_threat(event_data)
    
    async def rotate_encryption_keys(self, policy_id: Optional[str] = None) -> Dict[str, Any]:
        """Rotate encryption keys"""
        
        if policy_id:
            # Rotate specific policy key
            old_key_id = f"policy_{policy_id}"
            new_key = await self.hsm_manager.rotate_key(old_key_id)
            return {"rotated_key": new_key}
        else:
            # Rotate all keys
            rotated_keys = {}
            for policy_id in self.zero_trust.trust_policies.keys():
                old_key_id = f"policy_{policy_id}"
                new_key = await self.hsm_manager.rotate_key(old_key_id)
                rotated_keys[policy_id] = new_key
            
            return {"rotated_keys": rotated_keys}

# Global security framework instance
security_framework = None

async def get_security_framework() -> EnterpriseSecurityFramework:
    """Get or create global security framework"""
    
    global security_framework
    if security_framework is None:
        hsm_config = {
            "provider": "software",  # In production, use actual HSM
            "endpoint": "localhost:8080"
        }
        
        security_framework = EnterpriseSecurityFramework(hsm_config)
        await security_framework.initialize()
    
    return security_framework

# Alias for CLI compatibility
EnterpriseSecurityManager = EnterpriseSecurityFramework
