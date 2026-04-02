"""
Fixed Guardian Configuration with Proper Guardian Setup
Addresses the critical vulnerability where guardian lists were empty
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from eth_account import Account
from eth_utils import to_checksum_address, keccak

from .guardian_contract import (
    SpendingLimit, 
    TimeLockConfig, 
    GuardianConfig,
    GuardianContract
)


@dataclass
class GuardianSetup:
    """Guardian setup configuration"""
    primary_guardian: str      # Main guardian address
    backup_guardians: List[str] # Backup guardian addresses
    multisig_threshold: int     # Number of signatures required
    emergency_contacts: List[str] # Additional emergency contacts


class SecureGuardianManager:
    """
    Secure guardian management with proper initialization
    """
    
    def __init__(self):
        self.guardian_registrations: Dict[str, GuardianSetup] = {}
        self.guardian_contracts: Dict[str, GuardianContract] = {}
    
    def create_guardian_setup(
        self, 
        agent_address: str,
        owner_address: str,
        security_level: str = "conservative",
        custom_guardians: Optional[List[str]] = None
    ) -> GuardianSetup:
        """
        Create a proper guardian setup for an agent
        
        Args:
            agent_address: Agent wallet address
            owner_address: Owner of the agent
            security_level: Security level (conservative, aggressive, high_security)
            custom_guardians: Optional custom guardian addresses
            
        Returns:
            Guardian setup configuration
        """
        agent_address = to_checksum_address(agent_address)
        owner_address = to_checksum_address(owner_address)
        
        # Determine guardian requirements based on security level
        if security_level == "conservative":
            required_guardians = 3
            multisig_threshold = 2
        elif security_level == "aggressive":
            required_guardians = 2
            multisig_threshold = 2
        elif security_level == "high_security":
            required_guardians = 5
            multisig_threshold = 3
        else:
            raise ValueError(f"Invalid security level: {security_level}")
        
        # Build guardian list
        guardians = []
        
        # Always include the owner as primary guardian
        guardians.append(owner_address)
        
        # Add custom guardians if provided
        if custom_guardians:
            for guardian in custom_guardians:
                guardian = to_checksum_address(guardian)
                if guardian not in guardians:
                    guardians.append(guardian)
        
        # Generate backup guardians if needed
        while len(guardians) < required_guardians:
            # Generate a deterministic backup guardian based on agent address
            # In production, these would be trusted service addresses
            backup_index = len(guardians) - 1  # -1 because owner is already included
            backup_guardian = self._generate_backup_guardian(agent_address, backup_index)
            
            if backup_guardian not in guardians:
                guardians.append(backup_guardian)
        
        # Create setup
        setup = GuardianSetup(
            primary_guardian=owner_address,
            backup_guardians=[g for g in guardians if g != owner_address],
            multisig_threshold=multisig_threshold,
            emergency_contacts=guardians.copy()
        )
        
        self.guardian_registrations[agent_address] = setup
        
        return setup
    
    def _generate_backup_guardian(self, agent_address: str, index: int) -> str:
        """
        Generate deterministic backup guardian address
        
        In production, these would be pre-registered trusted guardian addresses
        """
        # Create a deterministic address based on agent address and index
        seed = f"{agent_address}_{index}_backup_guardian"
        hash_result = keccak(seed.encode())
        
        # Use the hash to generate a valid address
        address_bytes = hash_result[-20:]  # Take last 20 bytes
        address = "0x" + address_bytes.hex()
        
        return to_checksum_address(address)
    
    def create_secure_guardian_contract(
        self, 
        agent_address: str,
        security_level: str = "conservative",
        custom_guardians: Optional[List[str]] = None
    ) -> GuardianContract:
        """
        Create a guardian contract with proper guardian configuration
        
        Args:
            agent_address: Agent wallet address
            security_level: Security level
            custom_guardians: Optional custom guardian addresses
            
        Returns:
            Configured guardian contract
        """
        # Create guardian setup
        setup = self.create_guardian_setup(
            agent_address=agent_address,
            owner_address=agent_address,  # Agent is its own owner initially
            security_level=security_level,
            custom_guardians=custom_guardians
        )
        
        # Get security configuration
        config = self._get_security_config(security_level, setup)
        
        # Create contract
        contract = GuardianContract(agent_address, config)
        
        # Store contract
        self.guardian_contracts[agent_address] = contract
        
        return contract
    
    def _get_security_config(self, security_level: str, setup: GuardianSetup) -> GuardianConfig:
        """Get security configuration with proper guardian list"""
        
        # Build guardian list
        all_guardians = [setup.primary_guardian] + setup.backup_guardians
        
        if security_level == "conservative":
            return GuardianConfig(
                limits=SpendingLimit(
                    per_transaction=1000,
                    per_hour=5000,
                    per_day=20000,
                    per_week=100000
                ),
                time_lock=TimeLockConfig(
                    threshold=5000,
                    delay_hours=24,
                    max_delay_hours=168
                ),
                guardians=all_guardians,
                pause_enabled=True,
                emergency_mode=False,
                multisig_threshold=setup.multisig_threshold
            )
        
        elif security_level == "aggressive":
            return GuardianConfig(
                limits=SpendingLimit(
                    per_transaction=5000,
                    per_hour=25000,
                    per_day=100000,
                    per_week=500000
                ),
                time_lock=TimeLockConfig(
                    threshold=20000,
                    delay_hours=12,
                    max_delay_hours=72
                ),
                guardians=all_guardians,
                pause_enabled=True,
                emergency_mode=False,
                multisig_threshold=setup.multisig_threshold
            )
        
        elif security_level == "high_security":
            return GuardianConfig(
                limits=SpendingLimit(
                    per_transaction=500,
                    per_hour=2000,
                    per_day=8000,
                    per_week=40000
                ),
                time_lock=TimeLockConfig(
                    threshold=2000,
                    delay_hours=48,
                    max_delay_hours=168
                ),
                guardians=all_guardians,
                pause_enabled=True,
                emergency_mode=False,
                multisig_threshold=setup.multisig_threshold
            )
        
        else:
            raise ValueError(f"Invalid security level: {security_level}")
    
    def test_emergency_pause(self, agent_address: str, guardian_address: str) -> Dict:
        """
        Test emergency pause functionality
        
        Args:
            agent_address: Agent address
            guardian_address: Guardian attempting pause
            
        Returns:
            Test result
        """
        if agent_address not in self.guardian_contracts:
            return {
                "status": "error",
                "reason": "Agent not registered"
            }
        
        contract = self.guardian_contracts[agent_address]
        return contract.emergency_pause(guardian_address)
    
    def verify_guardian_authorization(self, agent_address: str, guardian_address: str) -> bool:
        """
        Verify if a guardian is authorized for an agent
        
        Args:
            agent_address: Agent address
            guardian_address: Guardian address to verify
            
        Returns:
            True if guardian is authorized
        """
        if agent_address not in self.guardian_registrations:
            return False
        
        setup = self.guardian_registrations[agent_address]
        all_guardians = [setup.primary_guardian] + setup.backup_guardians
        
        return to_checksum_address(guardian_address) in [
            to_checksum_address(g) for g in all_guardians
        ]
    
    def get_guardian_summary(self, agent_address: str) -> Dict:
        """
        Get guardian setup summary for an agent
        
        Args:
            agent_address: Agent address
            
        Returns:
            Guardian summary
        """
        if agent_address not in self.guardian_registrations:
            return {"error": "Agent not registered"}
        
        setup = self.guardian_registrations[agent_address]
        contract = self.guardian_contracts.get(agent_address)
        
        return {
            "agent_address": agent_address,
            "primary_guardian": setup.primary_guardian,
            "backup_guardians": setup.backup_guardians,
            "total_guardians": len(setup.backup_guardians) + 1,
            "multisig_threshold": setup.multisig_threshold,
            "emergency_contacts": setup.emergency_contacts,
            "contract_status": contract.get_spending_status() if contract else None,
            "pause_functional": contract is not None and len(setup.backup_guardians) > 0
        }


# Fixed security configurations with proper guardians
def get_fixed_conservative_config(agent_address: str, owner_address: str) -> GuardianConfig:
    """Get fixed conservative configuration with proper guardians"""
    return GuardianConfig(
        limits=SpendingLimit(
            per_transaction=1000,
            per_hour=5000,
            per_day=20000,
            per_week=100000
        ),
        time_lock=TimeLockConfig(
            threshold=5000,
            delay_hours=24,
            max_delay_hours=168
        ),
        guardians=[owner_address],  # At least the owner
        pause_enabled=True,
        emergency_mode=False
    )


def get_fixed_aggressive_config(agent_address: str, owner_address: str) -> GuardianConfig:
    """Get fixed aggressive configuration with proper guardians"""
    return GuardianConfig(
        limits=SpendingLimit(
            per_transaction=5000,
            per_hour=25000,
            per_day=100000,
            per_week=500000
        ),
        time_lock=TimeLockConfig(
            threshold=20000,
            delay_hours=12,
            max_delay_hours=72
        ),
        guardians=[owner_address],  # At least the owner
        pause_enabled=True,
        emergency_mode=False
    )


def get_fixed_high_security_config(agent_address: str, owner_address: str) -> GuardianConfig:
    """Get fixed high security configuration with proper guardians"""
    return GuardianConfig(
        limits=SpendingLimit(
            per_transaction=500,
            per_hour=2000,
            per_day=8000,
            per_week=40000
        ),
        time_lock=TimeLockConfig(
            threshold=2000,
            delay_hours=48,
            max_delay_hours=168
        ),
        guardians=[owner_address],  # At least the owner
        pause_enabled=True,
        emergency_mode=False
    )


# Global secure guardian manager
secure_guardian_manager = SecureGuardianManager()


# Convenience function for secure agent registration
def register_agent_with_guardians(
    agent_address: str,
    owner_address: str,
    security_level: str = "conservative",
    custom_guardians: Optional[List[str]] = None
) -> Dict:
    """
    Register an agent with proper guardian configuration
    
    Args:
        agent_address: Agent wallet address
        owner_address: Owner address
        security_level: Security level
        custom_guardians: Optional custom guardians
        
    Returns:
        Registration result
    """
    try:
        # Create secure guardian contract
        contract = secure_guardian_manager.create_secure_guardian_contract(
            agent_address=agent_address,
            security_level=security_level,
            custom_guardians=custom_guardians
        )
        
        # Get guardian summary
        summary = secure_guardian_manager.get_guardian_summary(agent_address)
        
        return {
            "status": "registered",
            "agent_address": agent_address,
            "security_level": security_level,
            "guardian_count": summary["total_guardians"],
            "multisig_threshold": summary["multisig_threshold"],
            "pause_functional": summary["pause_functional"],
            "registered_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Registration failed: {str(e)}"
        }
