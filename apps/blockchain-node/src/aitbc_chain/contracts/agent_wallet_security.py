"""
AITBC Agent Wallet Security Implementation

This module implements the security layer for autonomous agent wallets,
integrating the guardian contract to prevent unlimited spending in case
of agent compromise.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
import json
from eth_account import Account
from eth_utils import to_checksum_address

from .guardian_contract import (
    GuardianContract, 
    SpendingLimit, 
    TimeLockConfig, 
    GuardianConfig,
    create_guardian_contract,
    CONSERVATIVE_CONFIG,
    AGGRESSIVE_CONFIG,
    HIGH_SECURITY_CONFIG
)


@dataclass
class AgentSecurityProfile:
    """Security profile for an agent"""
    agent_address: str
    security_level: str  # "conservative", "aggressive", "high_security"
    guardian_addresses: List[str]
    custom_limits: Optional[Dict] = None
    enabled: bool = True
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(datetime.UTC)


class AgentWalletSecurity:
    """
    Security manager for autonomous agent wallets
    """
    
    def __init__(self):
        self.agent_profiles: Dict[str, AgentSecurityProfile] = {}
        self.guardian_contracts: Dict[str, GuardianContract] = {}
        self.security_events: List[Dict] = []
        
        # Default configurations
        self.configurations = {
            "conservative": CONSERVATIVE_CONFIG,
            "aggressive": AGGRESSIVE_CONFIG,
            "high_security": HIGH_SECURITY_CONFIG
        }
    
    def register_agent(self, 
                      agent_address: str, 
                      security_level: str = "conservative",
                      guardian_addresses: List[str] = None,
                      custom_limits: Dict = None) -> Dict:
        """
        Register an agent for security protection
        
        Args:
            agent_address: Agent wallet address
            security_level: Security level (conservative, aggressive, high_security)
            guardian_addresses: List of guardian addresses for recovery
            custom_limits: Custom spending limits (overrides security_level)
            
        Returns:
            Registration result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            
            if agent_address in self.agent_profiles:
                return {
                    "status": "error",
                    "reason": "Agent already registered"
                }
            
            # Validate security level
            if security_level not in self.configurations:
                return {
                    "status": "error",
                    "reason": f"Invalid security level: {security_level}"
                }
            
            # Default guardians if none provided
            if guardian_addresses is None:
                guardian_addresses = [agent_address]  # Self-guardian (should be overridden)
            
            # Validate guardian addresses
            guardian_addresses = [to_checksum_address(addr) for addr in guardian_addresses]
            
            # Create security profile
            profile = AgentSecurityProfile(
                agent_address=agent_address,
                security_level=security_level,
                guardian_addresses=guardian_addresses,
                custom_limits=custom_limits
            )
            
            # Create guardian contract
            config = self.configurations[security_level]
            if custom_limits:
                config.update(custom_limits)
            
            guardian_contract = create_guardian_contract(
                agent_address=agent_address,
                guardians=guardian_addresses,
                **config
            )
            
            # Store profile and contract
            self.agent_profiles[agent_address] = profile
            self.guardian_contracts[agent_address] = guardian_contract
            
            # Log security event
            self._log_security_event(
                event_type="agent_registered",
                agent_address=agent_address,
                security_level=security_level,
                guardian_count=len(guardian_addresses)
            )
            
            return {
                "status": "registered",
                "agent_address": agent_address,
                "security_level": security_level,
                "guardian_addresses": guardian_addresses,
                "limits": guardian_contract.config.limits,
                "time_lock_threshold": guardian_contract.config.time_lock.threshold,
                "registered_at": profile.created_at.isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Registration failed: {str(e)}"
            }
    
    def protect_transaction(self, 
                          agent_address: str, 
                          to_address: str, 
                          amount: int, 
                          data: str = "") -> Dict:
        """
        Protect a transaction with guardian contract
        
        Args:
            agent_address: Agent wallet address
            to_address: Recipient address
            amount: Amount to transfer
            data: Transaction data
            
        Returns:
            Protection result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            
            # Check if agent is registered
            if agent_address not in self.agent_profiles:
                return {
                    "status": "unprotected",
                    "reason": "Agent not registered for security protection",
                    "suggestion": "Register agent with register_agent() first"
                }
            
            # Check if protection is enabled
            profile = self.agent_profiles[agent_address]
            if not profile.enabled:
                return {
                    "status": "unprotected",
                    "reason": "Security protection disabled for this agent"
                }
            
            # Get guardian contract
            guardian_contract = self.guardian_contracts[agent_address]
            
            # Initiate transaction protection
            result = guardian_contract.initiate_transaction(to_address, amount, data)
            
            # Log security event
            self._log_security_event(
                event_type="transaction_protected",
                agent_address=agent_address,
                to_address=to_address,
                amount=amount,
                protection_status=result["status"]
            )
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Transaction protection failed: {str(e)}"
            }
    
    def execute_protected_transaction(self, 
                                    agent_address: str, 
                                    operation_id: str, 
                                    signature: str) -> Dict:
        """
        Execute a previously protected transaction
        
        Args:
            agent_address: Agent wallet address
            operation_id: Operation ID from protection
            signature: Transaction signature
            
        Returns:
            Execution result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            
            if agent_address not in self.guardian_contracts:
                return {
                    "status": "error",
                    "reason": "Agent not registered"
                }
            
            guardian_contract = self.guardian_contracts[agent_address]
            result = guardian_contract.execute_transaction(operation_id, signature)
            
            # Log security event
            if result["status"] == "executed":
                self._log_security_event(
                    event_type="transaction_executed",
                    agent_address=agent_address,
                    operation_id=operation_id,
                    transaction_hash=result.get("transaction_hash")
                )
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Transaction execution failed: {str(e)}"
            }
    
    def emergency_pause_agent(self, agent_address: str, guardian_address: str) -> Dict:
        """
        Emergency pause an agent's operations
        
        Args:
            agent_address: Agent wallet address
            guardian_address: Guardian address initiating pause
            
        Returns:
            Pause result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            guardian_address = to_checksum_address(guardian_address)
            
            if agent_address not in self.guardian_contracts:
                return {
                    "status": "error",
                    "reason": "Agent not registered"
                }
            
            guardian_contract = self.guardian_contracts[agent_address]
            result = guardian_contract.emergency_pause(guardian_address)
            
            # Log security event
            if result["status"] == "paused":
                self._log_security_event(
                    event_type="emergency_pause",
                    agent_address=agent_address,
                    guardian_address=guardian_address
                )
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Emergency pause failed: {str(e)}"
            }
    
    def update_agent_security(self, 
                            agent_address: str, 
                            new_limits: Dict, 
                            guardian_address: str) -> Dict:
        """
        Update security limits for an agent
        
        Args:
            agent_address: Agent wallet address
            new_limits: New spending limits
            guardian_address: Guardian address making the change
            
        Returns:
            Update result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            guardian_address = to_checksum_address(guardian_address)
            
            if agent_address not in self.guardian_contracts:
                return {
                    "status": "error",
                    "reason": "Agent not registered"
                }
            
            guardian_contract = self.guardian_contracts[agent_address]
            
            # Create new spending limits
            limits = SpendingLimit(
                per_transaction=new_limits.get("per_transaction", 1000),
                per_hour=new_limits.get("per_hour", 5000),
                per_day=new_limits.get("per_day", 20000),
                per_week=new_limits.get("per_week", 100000)
            )
            
            result = guardian_contract.update_limits(limits, guardian_address)
            
            # Log security event
            if result["status"] == "updated":
                self._log_security_event(
                    event_type="security_limits_updated",
                    agent_address=agent_address,
                    guardian_address=guardian_address,
                    new_limits=new_limits
                )
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Security update failed: {str(e)}"
            }
    
    def get_agent_security_status(self, agent_address: str) -> Dict:
        """
        Get security status for an agent
        
        Args:
            agent_address: Agent wallet address
            
        Returns:
            Security status
        """
        try:
            agent_address = to_checksum_address(agent_address)
            
            if agent_address not in self.agent_profiles:
                return {
                    "status": "not_registered",
                    "message": "Agent not registered for security protection"
                }
            
            profile = self.agent_profiles[agent_address]
            guardian_contract = self.guardian_contracts[agent_address]
            
            return {
                "status": "protected",
                "agent_address": agent_address,
                "security_level": profile.security_level,
                "enabled": profile.enabled,
                "guardian_addresses": profile.guardian_addresses,
                "registered_at": profile.created_at.isoformat(),
                "spending_status": guardian_contract.get_spending_status(),
                "pending_operations": guardian_contract.get_pending_operations(),
                "recent_activity": guardian_contract.get_operation_history(10)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Status check failed: {str(e)}"
            }
    
    def list_protected_agents(self) -> List[Dict]:
        """List all protected agents"""
        agents = []
        
        for agent_address, profile in self.agent_profiles.items():
            guardian_contract = self.guardian_contracts[agent_address]
            
            agents.append({
                "agent_address": agent_address,
                "security_level": profile.security_level,
                "enabled": profile.enabled,
                "guardian_count": len(profile.guardian_addresses),
                "pending_operations": len(guardian_contract.pending_operations),
                "paused": guardian_contract.paused,
                "emergency_mode": guardian_contract.emergency_mode,
                "registered_at": profile.created_at.isoformat()
            })
        
        return sorted(agents, key=lambda x: x["registered_at"], reverse=True)
    
    def get_security_events(self, agent_address: str = None, limit: int = 50) -> List[Dict]:
        """
        Get security events
        
        Args:
            agent_address: Filter by agent address (optional)
            limit: Maximum number of events
            
        Returns:
            Security events
        """
        events = self.security_events
        
        if agent_address:
            agent_address = to_checksum_address(agent_address)
            events = [e for e in events if e.get("agent_address") == agent_address]
        
        return sorted(events, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def _log_security_event(self, **kwargs):
        """Log a security event"""
        event = {
            "timestamp": datetime.now(datetime.UTC).isoformat(),
            **kwargs
        }
        self.security_events.append(event)
    
    def disable_agent_protection(self, agent_address: str, guardian_address: str) -> Dict:
        """
        Disable protection for an agent (guardian only)
        
        Args:
            agent_address: Agent wallet address
            guardian_address: Guardian address
            
        Returns:
            Disable result
        """
        try:
            agent_address = to_checksum_address(agent_address)
            guardian_address = to_checksum_address(guardian_address)
            
            if agent_address not in self.agent_profiles:
                return {
                    "status": "error",
                    "reason": "Agent not registered"
                }
            
            profile = self.agent_profiles[agent_address]
            
            if guardian_address not in profile.guardian_addresses:
                return {
                    "status": "error",
                    "reason": "Not authorized: not a guardian"
                }
            
            profile.enabled = False
            
            # Log security event
            self._log_security_event(
                event_type="protection_disabled",
                agent_address=agent_address,
                guardian_address=guardian_address
            )
            
            return {
                "status": "disabled",
                "agent_address": agent_address,
                "disabled_at": datetime.now(datetime.UTC).isoformat(),
                "guardian": guardian_address
            }
            
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Disable protection failed: {str(e)}"
            }


# Global security manager instance
agent_wallet_security = AgentWalletSecurity()


# Convenience functions for common operations
def register_agent_for_protection(agent_address: str, 
                                 security_level: str = "conservative",
                                 guardians: List[str] = None) -> Dict:
    """Register an agent for security protection"""
    return agent_wallet_security.register_agent(
        agent_address=agent_address,
        security_level=security_level,
        guardian_addresses=guardians
    )


def protect_agent_transaction(agent_address: str, 
                             to_address: str, 
                             amount: int, 
                             data: str = "") -> Dict:
    """Protect a transaction for an agent"""
    return agent_wallet_security.protect_transaction(
        agent_address=agent_address,
        to_address=to_address,
        amount=amount,
        data=data
    )


def get_agent_security_summary(agent_address: str) -> Dict:
    """Get security summary for an agent"""
    return agent_wallet_security.get_agent_security_status(agent_address)


# Security audit and monitoring functions
def generate_security_report() -> Dict:
    """Generate comprehensive security report"""
    protected_agents = agent_wallet_security.list_protected_agents()
    
    total_agents = len(protected_agents)
    active_agents = len([a for a in protected_agents if a["enabled"]])
    paused_agents = len([a for a in protected_agents if a["paused"]])
    emergency_agents = len([a for a in protected_agents if a["emergency_mode"]])
    
    recent_events = agent_wallet_security.get_security_events(limit=20)
    
    return {
        "generated_at": datetime.now(datetime.UTC).isoformat(),
        "summary": {
            "total_protected_agents": total_agents,
            "active_agents": active_agents,
            "paused_agents": paused_agents,
            "emergency_mode_agents": emergency_agents,
            "protection_coverage": f"{(active_agents / total_agents * 100):.1f}%" if total_agents > 0 else "0%"
        },
        "agents": protected_agents,
        "recent_security_events": recent_events,
        "security_levels": {
            level: len([a for a in protected_agents if a["security_level"] == level])
            for level in ["conservative", "aggressive", "high_security"]
        }
    }


def detect_suspicious_activity(agent_address: str, hours: int = 24) -> Dict:
    """Detect suspicious activity for an agent"""
    status = agent_wallet_security.get_agent_security_status(agent_address)
    
    if status["status"] != "protected":
        return {
            "status": "not_protected",
            "suspicious_activity": False
        }
    
    spending_status = status["spending_status"]
    recent_events = agent_wallet_security.get_security_events(agent_address, limit=50)
    
    # Suspicious patterns
    suspicious_patterns = []
    
    # Check for rapid spending
    if spending_status["spent"]["current_hour"] > spending_status["current_limits"]["per_hour"] * 0.8:
        suspicious_patterns.append("High hourly spending rate")
    
    # Check for many small transactions (potential dust attack)
    recent_tx_count = len([e for e in recent_events if e["event_type"] == "transaction_executed"])
    if recent_tx_count > 20:
        suspicious_patterns.append("High transaction frequency")
    
    # Check for emergency pauses
    recent_pauses = len([e for e in recent_events if e["event_type"] == "emergency_pause"])
    if recent_pauses > 0:
        suspicious_patterns.append("Recent emergency pauses detected")
    
    return {
        "status": "analyzed",
        "agent_address": agent_address,
        "suspicious_activity": len(suspicious_patterns) > 0,
        "suspicious_patterns": suspicious_patterns,
        "analysis_period_hours": hours,
        "analyzed_at": datetime.now(datetime.UTC).isoformat()
    }
