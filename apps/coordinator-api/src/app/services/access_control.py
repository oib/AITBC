"""
Access control service for confidential transactions
"""

from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta
from enum import Enum
import json
import re

from ..schemas import ConfidentialAccessRequest, ConfidentialAccessLog
from ..config import settings
from ..logging import get_logger

logger = get_logger(__name__)


class AccessPurpose(str, Enum):
    """Standard access purposes"""
    SETTLEMENT = "settlement"
    AUDIT = "audit"
    COMPLIANCE = "compliance"
    DISPUTE = "dispute"
    SUPPORT = "support"
    REPORTING = "reporting"


class AccessLevel(str, Enum):
    """Access levels for confidential data"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ParticipantRole(str, Enum):
    """Roles for transaction participants"""
    CLIENT = "client"
    MINER = "miner"
    COORDINATOR = "coordinator"
    AUDITOR = "auditor"
    REGULATOR = "regulator"


class PolicyStore:
    """Storage for access control policies"""
    
    def __init__(self):
        self._policies: Dict[str, Dict] = {}
        self._role_permissions: Dict[ParticipantRole, Set[str]] = {
            ParticipantRole.CLIENT: {"read_own", "settlement_own"},
            ParticipantRole.MINER: {"read_assigned", "settlement_assigned"},
            ParticipantRole.COORDINATOR: {"read_all", "admin_all"},
            ParticipantRole.AUDITOR: {"read_all", "audit_all"},
            ParticipantRole.REGULATOR: {"read_all", "compliance_all"}
        }
        self._load_default_policies()
    
    def _load_default_policies(self):
        """Load default access policies"""
        # Client can access their own transactions
        self._policies["client_own_data"] = {
            "participants": ["client"],
            "conditions": {
                "transaction_client_id": "{requester}",
                "purpose": ["settlement", "dispute", "support"]
            },
            "access_level": AccessLevel.READ,
            "time_restrictions": None
        }
        
        # Miner can access assigned transactions
        self._policies["miner_assigned_data"] = {
            "participants": ["miner"],
            "conditions": {
                "transaction_miner_id": "{requester}",
                "purpose": ["settlement"]
            },
            "access_level": AccessLevel.READ,
            "time_restrictions": None
        }
        
        # Coordinator has full access
        self._policies["coordinator_full"] = {
            "participants": ["coordinator"],
            "conditions": {},
            "access_level": AccessLevel.ADMIN,
            "time_restrictions": None
        }
        
        # Auditor access for compliance
        self._policies["auditor_compliance"] = {
            "participants": ["auditor", "regulator"],
            "conditions": {
                "purpose": ["audit", "compliance"]
            },
            "access_level": AccessLevel.READ,
            "time_restrictions": {
                "business_hours_only": True,
                "retention_days": 2555  # 7 years
            }
        }
    
    def get_policy(self, policy_id: str) -> Optional[Dict]:
        """Get access policy by ID"""
        return self._policies.get(policy_id)
    
    def list_policies(self) -> List[str]:
        """List all policy IDs"""
        return list(self._policies.keys())
    
    def add_policy(self, policy_id: str, policy: Dict):
        """Add new access policy"""
        self._policies[policy_id] = policy
    
    def get_role_permissions(self, role: ParticipantRole) -> Set[str]:
        """Get permissions for a role"""
        return self._role_permissions.get(role, set())


class AccessController:
    """Controls access to confidential transaction data"""
    
    def __init__(self, policy_store: PolicyStore):
        self.policy_store = policy_store
        self._access_cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(minutes=5)
    
    def verify_access(self, request: ConfidentialAccessRequest) -> bool:
        """Verify if requester has access rights"""
        try:
            # Check cache first
            cache_key = self._get_cache_key(request)
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result["allowed"]
            
            # Get participant info
            participant_info = self._get_participant_info(request.requester)
            if not participant_info:
                logger.warning(f"Unknown participant: {request.requester}")
                return False
            
            # Check role-based permissions
            role = participant_info.get("role")
            if not self._check_role_permissions(role, request):
                return False
            
            # Check transaction-specific policies
            transaction = self._get_transaction(request.transaction_id)
            if not transaction:
                logger.warning(f"Transaction not found: {request.transaction_id}")
                return False
            
            # Apply access policies
            allowed = self._apply_policies(request, participant_info, transaction)
            
            # Cache result
            self._cache_result(cache_key, allowed)
            
            return allowed
            
        except Exception as e:
            logger.error(f"Access verification failed: {e}")
            return False
    
    def _check_role_permissions(self, role: str, request: ConfidentialAccessRequest) -> bool:
        """Check if role grants access for this purpose"""
        try:
            participant_role = ParticipantRole(role.lower())
            permissions = self.policy_store.get_role_permissions(participant_role)
            
            # Check purpose-based permissions
            if request.purpose == "settlement":
                return "settlement" in permissions or "settlement_own" in permissions
            elif request.purpose == "audit":
                return "audit" in permissions or "audit_all" in permissions
            elif request.purpose == "compliance":
                return "compliance" in permissions or "compliance_all" in permissions
            elif request.purpose == "dispute":
                return "dispute" in permissions or "read_own" in permissions
            elif request.purpose == "support":
                return "support" in permissions or "read_all" in permissions
            else:
                return "read" in permissions or "read_all" in permissions
                
        except ValueError:
            logger.warning(f"Invalid role: {role}")
            return False
    
    def _apply_policies(
        self,
        request: ConfidentialAccessRequest,
        participant_info: Dict,
        transaction: Dict
    ) -> bool:
        """Apply access policies to request"""
        # Check if participant is in transaction participants list
        if request.requester not in transaction.get("participants", []):
            # Only coordinators, auditors, and regulators can access non-participant data
            role = participant_info.get("role", "").lower()
            if role not in ["coordinator", "auditor", "regulator"]:
                return False
        
        # Check time-based restrictions
        if not self._check_time_restrictions(request.purpose, participant_info.get("role")):
            return False
        
        # Check business hours for auditors
        if participant_info.get("role") == "auditor" and not self._is_business_hours():
            return False
        
        # Check retention periods
        if not self._check_retention_period(transaction, participant_info.get("role")):
            return False
        
        return True
    
    def _check_time_restrictions(self, purpose: str, role: Optional[str]) -> bool:
        """Check time-based access restrictions"""
        # No restrictions for settlement and dispute
        if purpose in ["settlement", "dispute"]:
            return True
        
        # Audit and compliance only during business hours for non-coordinators
        if purpose in ["audit", "compliance"] and role not in ["coordinator"]:
            return self._is_business_hours()
        
        return True
    
    def _is_business_hours(self) -> bool:
        """Check if current time is within business hours"""
        now = datetime.utcnow()
        
        # Monday-Friday, 9 AM - 5 PM UTC
        if now.weekday() >= 5:  # Weekend
            return False
        
        if 9 <= now.hour < 17:
            return True
        
        return False
    
    def _check_retention_period(self, transaction: Dict, role: Optional[str]) -> bool:
        """Check if data is within retention period for role"""
        transaction_date = transaction.get("timestamp", datetime.utcnow())
        
        # Different retention periods for different roles
        if role == "regulator":
            retention_days = 2555  # 7 years
        elif role == "auditor":
            retention_days = 1825  # 5 years
        elif role == "coordinator":
            retention_days = 3650  # 10 years
        else:
            retention_days = 365  # 1 year
        
        expiry_date = transaction_date + timedelta(days=retention_days)
        
        return datetime.utcnow() <= expiry_date
    
    def _get_participant_info(self, participant_id: str) -> Optional[Dict]:
        """Get participant information"""
        # In production, query from database
        # For now, return mock data
        if participant_id.startswith("client-"):
            return {"id": participant_id, "role": "client", "active": True}
        elif participant_id.startswith("miner-"):
            return {"id": participant_id, "role": "miner", "active": True}
        elif participant_id.startswith("coordinator-"):
            return {"id": participant_id, "role": "coordinator", "active": True}
        elif participant_id.startswith("auditor-"):
            return {"id": participant_id, "role": "auditor", "active": True}
        elif participant_id.startswith("regulator-"):
            return {"id": participant_id, "role": "regulator", "active": True}
        else:
            return None
    
    def _get_transaction(self, transaction_id: str) -> Optional[Dict]:
        """Get transaction information"""
        # In production, query from database
        # For now, return mock data
        return {
            "transaction_id": transaction_id,
            "participants": ["client-456", "miner-789"],
            "timestamp": datetime.utcnow(),
            "status": "completed"
        }
    
    def _get_cache_key(self, request: ConfidentialAccessRequest) -> str:
        """Generate cache key for access request"""
        return f"{request.requester}:{request.transaction_id}:{request.purpose}"
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict]:
        """Get cached access result"""
        if cache_key in self._access_cache:
            cached = self._access_cache[cache_key]
            if datetime.utcnow() - cached["timestamp"] < self._cache_ttl:
                return cached
            else:
                del self._access_cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, allowed: bool):
        """Cache access result"""
        self._access_cache[cache_key] = {
            "allowed": allowed,
            "timestamp": datetime.utcnow()
        }
    
    def create_access_policy(
        self,
        name: str,
        participants: List[str],
        conditions: Dict[str, Any],
        access_level: AccessLevel
    ) -> str:
        """Create a new access policy"""
        policy_id = f"policy_{datetime.utcnow().timestamp()}"
        
        policy = {
            "participants": participants,
            "conditions": conditions,
            "access_level": access_level,
            "time_restrictions": conditions.get("time_restrictions"),
            "created_at": datetime.utcnow().isoformat()
        }
        
        self.policy_store.add_policy(policy_id, policy)
        logger.info(f"Created access policy: {policy_id}")
        
        return policy_id
    
    def revoke_access(self, participant_id: str, transaction_id: Optional[str] = None):
        """Revoke access for participant"""
        # In production, update database
        # For now, clear cache
        keys_to_remove = []
        for key in self._access_cache:
            if key.startswith(f"{participant_id}:"):
                if transaction_id is None or key.split(":")[1] == transaction_id:
                    keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._access_cache[key]
        
        logger.info(f"Revoked access for participant: {participant_id}")
    
    def get_access_summary(self, participant_id: str) -> Dict:
        """Get summary of participant's access rights"""
        participant_info = self._get_participant_info(participant_id)
        if not participant_info:
            return {"error": "Participant not found"}
        
        role = participant_info.get("role")
        permissions = self.policy_store.get_role_permissions(ParticipantRole(role))
        
        return {
            "participant_id": participant_id,
            "role": role,
            "permissions": list(permissions),
            "active": participant_info.get("active", False)
        }
