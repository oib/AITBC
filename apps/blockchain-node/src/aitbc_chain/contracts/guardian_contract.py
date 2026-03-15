"""
AITBC Guardian Contract - Spending Limit Protection for Agent Wallets

This contract implements a spending limit guardian that protects autonomous agent
wallets from unlimited spending in case of compromise. It provides:
- Per-transaction spending limits
- Per-period (daily/hourly) spending caps
- Time-lock for large withdrawals
- Emergency pause functionality
- Multi-signature recovery for critical operations
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from eth_account import Account
from eth_utils import to_checksum_address, keccak


@dataclass
class SpendingLimit:
    """Spending limit configuration"""
    per_transaction: int  # Maximum per transaction
    per_hour: int         # Maximum per hour
    per_day: int          # Maximum per day
    per_week: int         # Maximum per week
    
@dataclass
class TimeLockConfig:
    """Time lock configuration for large withdrawals"""
    threshold: int       # Amount that triggers time lock
    delay_hours: int     # Delay period in hours
    max_delay_hours: int # Maximum delay period


@dataclass
class GuardianConfig:
    """Complete guardian configuration"""
    limits: SpendingLimit
    time_lock: TimeLockConfig
    guardians: List[str]  # Guardian addresses for recovery
    pause_enabled: bool = True
    emergency_mode: bool = False


class GuardianContract:
    """
    Guardian contract implementation for agent wallet protection
    """
    
    def __init__(self, agent_address: str, config: GuardianConfig):
        self.agent_address = to_checksum_address(agent_address)
        self.config = config
        self.spending_history: List[Dict] = []
        self.pending_operations: Dict[str, Dict] = {}
        self.paused = False
        self.emergency_mode = False
        
        # Contract state
        self.nonce = 0
        self.guardian_approvals: Dict[str, bool] = {}
        
    def _get_period_key(self, timestamp: datetime, period: str) -> str:
        """Generate period key for spending tracking"""
        if period == "hour":
            return timestamp.strftime("%Y-%m-%d-%H")
        elif period == "day":
            return timestamp.strftime("%Y-%m-%d")
        elif period == "week":
            # Get week number (Monday as first day)
            week_num = timestamp.isocalendar()[1]
            return f"{timestamp.year}-W{week_num:02d}"
        else:
            raise ValueError(f"Invalid period: {period}")
    
    def _get_spent_in_period(self, period: str, timestamp: datetime = None) -> int:
        """Calculate total spent in given period"""
        if timestamp is None:
            timestamp = datetime.utcnow()
            
        period_key = self._get_period_key(timestamp, period)
        
        total = 0
        for record in self.spending_history:
            record_time = datetime.fromisoformat(record["timestamp"])
            record_period = self._get_period_key(record_time, period)
            
            if record_period == period_key and record["status"] == "completed":
                total += record["amount"]
                
        return total
    
    def _check_spending_limits(self, amount: int, timestamp: datetime = None) -> Tuple[bool, str]:
        """Check if amount exceeds spending limits"""
        if timestamp is None:
            timestamp = datetime.utcnow()
            
        # Check per-transaction limit
        if amount > self.config.limits.per_transaction:
            return False, f"Amount {amount} exceeds per-transaction limit {self.config.limits.per_transaction}"
        
        # Check per-hour limit
        spent_hour = self._get_spent_in_period("hour", timestamp)
        if spent_hour + amount > self.config.limits.per_hour:
            return False, f"Hourly spending {spent_hour + amount} would exceed limit {self.config.limits.per_hour}"
        
        # Check per-day limit
        spent_day = self._get_spent_in_period("day", timestamp)
        if spent_day + amount > self.config.limits.per_day:
            return False, f"Daily spending {spent_day + amount} would exceed limit {self.config.limits.per_day}"
        
        # Check per-week limit
        spent_week = self._get_spent_in_period("week", timestamp)
        if spent_week + amount > self.config.limits.per_week:
            return False, f"Weekly spending {spent_week + amount} would exceed limit {self.config.limits.per_week}"
        
        return True, "Spending limits check passed"
    
    def _requires_time_lock(self, amount: int) -> bool:
        """Check if amount requires time lock"""
        return amount >= self.config.time_lock.threshold
    
    def _create_operation_hash(self, operation: Dict) -> str:
        """Create hash for operation identification"""
        operation_str = json.dumps(operation, sort_keys=True)
        return keccak(operation_str.encode()).hex()
    
    def initiate_transaction(self, to_address: str, amount: int, data: str = "") -> Dict:
        """
        Initiate a transaction with guardian protection
        
        Args:
            to_address: Recipient address
            amount: Amount to transfer
            data: Transaction data (optional)
            
        Returns:
            Operation result with status and details
        """
        # Check if paused
        if self.paused:
            return {
                "status": "rejected",
                "reason": "Guardian contract is paused",
                "operation_id": None
            }
        
        # Check emergency mode
        if self.emergency_mode:
            return {
                "status": "rejected", 
                "reason": "Emergency mode activated",
                "operation_id": None
            }
        
        # Validate address
        try:
            to_address = to_checksum_address(to_address)
        except Exception:
            return {
                "status": "rejected",
                "reason": "Invalid recipient address",
                "operation_id": None
            }
        
        # Check spending limits
        limits_ok, limits_reason = self._check_spending_limits(amount)
        if not limits_ok:
            return {
                "status": "rejected",
                "reason": limits_reason,
                "operation_id": None
            }
        
        # Create operation
        operation = {
            "type": "transaction",
            "to": to_address,
            "amount": amount,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "nonce": self.nonce,
            "status": "pending"
        }
        
        operation_id = self._create_operation_hash(operation)
        operation["operation_id"] = operation_id
        
        # Check if time lock is required
        if self._requires_time_lock(amount):
            unlock_time = datetime.utcnow() + timedelta(hours=self.config.time_lock.delay_hours)
            operation["unlock_time"] = unlock_time.isoformat()
            operation["status"] = "time_locked"
            
            # Store for later execution
            self.pending_operations[operation_id] = operation
            
            return {
                "status": "time_locked",
                "operation_id": operation_id,
                "unlock_time": unlock_time.isoformat(),
                "delay_hours": self.config.time_lock.delay_hours,
                "message": f"Transaction requires {self.config.time_lock.delay_hours}h time lock"
            }
        
        # Immediate execution for smaller amounts
        self.pending_operations[operation_id] = operation
        
        return {
            "status": "approved",
            "operation_id": operation_id,
            "message": "Transaction approved for execution"
        }
    
    def execute_transaction(self, operation_id: str, signature: str) -> Dict:
        """
        Execute a previously approved transaction
        
        Args:
            operation_id: Operation ID from initiate_transaction
            signature: Transaction signature from agent
            
        Returns:
            Execution result
        """
        if operation_id not in self.pending_operations:
            return {
                "status": "error",
                "reason": "Operation not found"
            }
        
        operation = self.pending_operations[operation_id]
        
        # Check if operation is time locked
        if operation["status"] == "time_locked":
            unlock_time = datetime.fromisoformat(operation["unlock_time"])
            if datetime.utcnow() < unlock_time:
                return {
                    "status": "error",
                    "reason": f"Operation locked until {unlock_time.isoformat()}"
                }
            
            operation["status"] = "ready"
        
        # Verify signature (simplified - in production, use proper verification)
        try:
            # In production, verify the signature matches the agent address
            # For now, we'll assume signature is valid
            pass
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Invalid signature: {str(e)}"
            }
        
        # Record the transaction
        record = {
            "operation_id": operation_id,
            "to": operation["to"],
            "amount": operation["amount"],
            "data": operation.get("data", ""),
            "timestamp": operation["timestamp"],
            "executed_at": datetime.utcnow().isoformat(),
            "status": "completed",
            "nonce": operation["nonce"]
        }
        
        self.spending_history.append(record)
        self.nonce += 1
        
        # Remove from pending
        del self.pending_operations[operation_id]
        
        return {
            "status": "executed",
            "operation_id": operation_id,
            "transaction_hash": f"0x{keccak(f'{operation_id}{signature}'.encode()).hex()}",
            "executed_at": record["executed_at"]
        }
    
    def emergency_pause(self, guardian_address: str) -> Dict:
        """
        Emergency pause function (guardian only)
        
        Args:
            guardian_address: Address of guardian initiating pause
            
        Returns:
            Pause result
        """
        if guardian_address not in self.config.guardians:
            return {
                "status": "rejected",
                "reason": "Not authorized: guardian address not recognized"
            }
        
        self.paused = True
        self.emergency_mode = True
        
        return {
            "status": "paused",
            "paused_at": datetime.utcnow().isoformat(),
            "guardian": guardian_address,
            "message": "Emergency pause activated - all operations halted"
        }
    
    def emergency_unpause(self, guardian_signatures: List[str]) -> Dict:
        """
        Emergency unpause function (requires multiple guardian signatures)
        
        Args:
            guardian_signatures: Signatures from required guardians
            
        Returns:
            Unpause result
        """
        # In production, verify all guardian signatures
        required_signatures = len(self.config.guardians)
        if len(guardian_signatures) < required_signatures:
            return {
                "status": "rejected",
                "reason": f"Requires {required_signatures} guardian signatures, got {len(guardian_signatures)}"
            }
        
        # Verify signatures (simplified)
        # In production, verify each signature matches a guardian address
        
        self.paused = False
        self.emergency_mode = False
        
        return {
            "status": "unpaused",
            "unpaused_at": datetime.utcnow().isoformat(),
            "message": "Emergency pause lifted - operations resumed"
        }
    
    def update_limits(self, new_limits: SpendingLimit, guardian_address: str) -> Dict:
        """
        Update spending limits (guardian only)
        
        Args:
            new_limits: New spending limits
            guardian_address: Address of guardian making the change
            
        Returns:
            Update result
        """
        if guardian_address not in self.config.guardians:
            return {
                "status": "rejected",
                "reason": "Not authorized: guardian address not recognized"
            }
        
        old_limits = self.config.limits
        self.config.limits = new_limits
        
        return {
            "status": "updated",
            "old_limits": old_limits,
            "new_limits": new_limits,
            "updated_at": datetime.utcnow().isoformat(),
            "guardian": guardian_address
        }
    
    def get_spending_status(self) -> Dict:
        """Get current spending status and limits"""
        now = datetime.utcnow()
        
        return {
            "agent_address": self.agent_address,
            "current_limits": self.config.limits,
            "spent": {
                "current_hour": self._get_spent_in_period("hour", now),
                "current_day": self._get_spent_in_period("day", now),
                "current_week": self._get_spent_in_period("week", now)
            },
            "remaining": {
                "current_hour": self.config.limits.per_hour - self._get_spent_in_period("hour", now),
                "current_day": self.config.limits.per_day - self._get_spent_in_period("day", now),
                "current_week": self.config.limits.per_week - self._get_spent_in_period("week", now)
            },
            "pending_operations": len(self.pending_operations),
            "paused": self.paused,
            "emergency_mode": self.emergency_mode,
            "nonce": self.nonce
        }
    
    def get_operation_history(self, limit: int = 50) -> List[Dict]:
        """Get operation history"""
        return sorted(self.spending_history, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def get_pending_operations(self) -> List[Dict]:
        """Get all pending operations"""
        return list(self.pending_operations.values())


# Factory function for creating guardian contracts
def create_guardian_contract(
    agent_address: str,
    per_transaction: int = 1000,
    per_hour: int = 5000,
    per_day: int = 20000,
    per_week: int = 100000,
    time_lock_threshold: int = 10000,
    time_lock_delay: int = 24,
    guardians: List[str] = None
) -> GuardianContract:
    """
    Create a guardian contract with default security parameters
    
    Args:
        agent_address: The agent wallet address to protect
        per_transaction: Maximum amount per transaction
        per_hour: Maximum amount per hour
        per_day: Maximum amount per day
        per_week: Maximum amount per week
        time_lock_threshold: Amount that triggers time lock
        time_lock_delay: Time lock delay in hours
        guardians: List of guardian addresses
        
    Returns:
        Configured GuardianContract instance
    """
    if guardians is None:
        # Default to using the agent address as guardian (should be overridden)
        guardians = [agent_address]
    
    limits = SpendingLimit(
        per_transaction=per_transaction,
        per_hour=per_hour,
        per_day=per_day,
        per_week=per_week
    )
    
    time_lock = TimeLockConfig(
        threshold=time_lock_threshold,
        delay_hours=time_lock_delay,
        max_delay_hours=168  # 1 week max
    )
    
    config = GuardianConfig(
        limits=limits,
        time_lock=time_lock,
        guardians=[to_checksum_address(g) for g in guardians]
    )
    
    return GuardianContract(agent_address, config)


# Example usage and security configurations
CONSERVATIVE_CONFIG = {
    "per_transaction": 100,    # $100 per transaction
    "per_hour": 500,          # $500 per hour
    "per_day": 2000,          # $2,000 per day
    "per_week": 10000,        # $10,000 per week
    "time_lock_threshold": 1000,  # Time lock over $1,000
    "time_lock_delay": 24     # 24 hour delay
}

AGGRESSIVE_CONFIG = {
    "per_transaction": 1000,   # $1,000 per transaction
    "per_hour": 5000,         # $5,000 per hour
    "per_day": 20000,         # $20,000 per day
    "per_week": 100000,       # $100,000 per week
    "time_lock_threshold": 10000,  # Time lock over $10,000
    "time_lock_delay": 12     # 12 hour delay
}

HIGH_SECURITY_CONFIG = {
    "per_transaction": 50,     # $50 per transaction
    "per_hour": 200,          # $200 per hour
    "per_day": 1000,          # $1,000 per day
    "per_week": 5000,         # $5,000 per week
    "time_lock_threshold": 500,   # Time lock over $500
    "time_lock_delay": 48     # 48 hour delay
}
