"""
Tests for AITBC Agent Wallet Security System

Comprehensive test suite for the guardian contract system that protects
autonomous agent wallets from unlimited spending in case of compromise.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from eth_account import Account
from eth_utils import to_checksum_address

from aitbc_chain.contracts.guardian_contract import (
    GuardianContract,
    SpendingLimit,
    TimeLockConfig,
    GuardianConfig,
    create_guardian_contract,
    CONSERVATIVE_CONFIG,
    AGGRESSIVE_CONFIG,
    HIGH_SECURITY_CONFIG
)

from aitbc_chain.contracts.agent_wallet_security import (
    AgentWalletSecurity,
    AgentSecurityProfile,
    register_agent_for_protection,
    protect_agent_transaction,
    get_agent_security_summary,
    generate_security_report,
    detect_suspicious_activity
)


class TestGuardianContract:
    """Test the core guardian contract functionality"""
    
    @pytest.fixture
    def sample_config(self):
        """Sample guardian configuration for testing"""
        limits = SpendingLimit(
            per_transaction=100,
            per_hour=500,
            per_day=2000,
            per_week=10000
        )
        
        time_lock = TimeLockConfig(
            threshold=1000,
            delay_hours=24,
            max_delay_hours=168
        )
        
        guardians = [to_checksum_address(f"0x{'0'*38}{i:02d}") for i in range(3)]
        
        return GuardianConfig(
            limits=limits,
            time_lock=time_lock,
            guardians=guardians
        )
    
    @pytest.fixture
    def guardian_contract(self, sample_config):
        """Create a guardian contract for testing"""
        agent_address = to_checksum_address("0x1234567890123456789012345678901234567890")
        return GuardianContract(agent_address, sample_config)
    
    def test_spending_limit_enforcement(self, guardian_contract):
        """Test that spending limits are properly enforced"""
        # Test per-transaction limit
        result = guardian_contract.initiate_transaction(
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=150  # Exceeds per_transaction limit of 100
        )
        
        assert result["status"] == "rejected"
        assert "per-transaction limit" in result["reason"]
        
        # Test within limits
        result = guardian_contract.initiate_transaction(
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50  # Within limits
        )
        
        assert result["status"] == "approved"
        assert "operation_id" in result
    
    def test_time_lock_functionality(self, guardian_contract):
        """Test time lock for large transactions"""
        # Test time lock threshold
        result = guardian_contract.initiate_transaction(
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=1500  # Exceeds time lock threshold of 1000
        )
        
        assert result["status"] == "time_locked"
        assert "unlock_time" in result
        assert result["delay_hours"] == 24
        
        # Test execution before unlock time
        operation_id = result["operation_id"]
        exec_result = guardian_contract.execute_transaction(
            operation_id=operation_id,
            signature="mock_signature"
        )
        
        assert exec_result["status"] == "error"
        assert "locked until" in exec_result["reason"]
    
    def test_hourly_spending_limits(self, guardian_contract):
        """Test hourly spending limit enforcement"""
        # Create multiple transactions within hour limit
        for i in range(5):  # 5 transactions of 100 each = 500 (hourly limit)
            result = guardian_contract.initiate_transaction(
                to_address=f"0xabcdef123456789012345678901234567890ab{i:02d}",
                amount=100
            )
            
            if i < 4:  # First 4 should be approved
                assert result["status"] == "approved"
                # Execute the transaction
                guardian_contract.execute_transaction(
                    operation_id=result["operation_id"],
                    signature="mock_signature"
                )
            else:  # 5th should be rejected (exceeds hourly limit)
                assert result["status"] == "rejected"
                assert "Hourly spending" in result["reason"]
    
    def test_emergency_pause(self, guardian_contract):
        """Test emergency pause functionality"""
        guardian_address = guardian_contract.config.guardians[0]
        
        # Test emergency pause
        result = guardian_contract.emergency_pause(guardian_address)
        
        assert result["status"] == "paused"
        assert result["guardian"] == guardian_address
        
        # Test that transactions are rejected during pause
        tx_result = guardian_contract.initiate_transaction(
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50
        )
        
        assert tx_result["status"] == "rejected"
        assert "paused" in tx_result["reason"]
    
    def test_unauthorized_operations(self, guardian_contract):
        """Test that unauthorized operations are rejected"""
        unauthorized_address = to_checksum_address("0xunauthorized123456789012345678901234567890")
        
        # Test unauthorized emergency pause
        result = guardian_contract.emergency_pause(unauthorized_address)
        
        assert result["status"] == "rejected"
        assert "Not authorized" in result["reason"]
        
        # Test unauthorized limit updates
        new_limits = SpendingLimit(200, 1000, 4000, 20000)
        result = guardian_contract.update_limits(new_limits, unauthorized_address)
        
        assert result["status"] == "rejected"
        assert "Not authorized" in result["reason"]
    
    def test_spending_status_tracking(self, guardian_contract):
        """Test spending status tracking and reporting"""
        # Execute some transactions
        for i in range(3):
            result = guardian_contract.initiate_transaction(
                to_address=f"0xabcdef123456789012345678901234567890ab{i:02d}",
                amount=50
            )
            if result["status"] == "approved":
                guardian_contract.execute_transaction(
                    operation_id=result["operation_id"],
                    signature="mock_signature"
                )
        
        status = guardian_contract.get_spending_status()
        
        assert status["agent_address"] == guardian_contract.agent_address
        assert status["spent"]["current_hour"] == 150  # 3 * 50
        assert status["remaining"]["current_hour"] == 350  # 500 - 150
        assert status["nonce"] == 3


class TestAgentWalletSecurity:
    """Test the agent wallet security manager"""
    
    @pytest.fixture
    def security_manager(self):
        """Create a security manager for testing"""
        return AgentWalletSecurity()
    
    @pytest.fixture
    def sample_agent(self):
        """Sample agent address for testing"""
        return to_checksum_address("0x1234567890123456789012345678901234567890")
    
    @pytest.fixture
    def sample_guardians(self):
        """Sample guardian addresses for testing"""
        return [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)  # Guardians 01, 02, 03
        ]
    
    def test_agent_registration(self, security_manager, sample_agent, sample_guardians):
        """Test agent registration for security protection"""
        result = security_manager.register_agent(
            agent_address=sample_agent,
            security_level="conservative",
            guardian_addresses=sample_guardians
        )
        
        assert result["status"] == "registered"
        assert result["agent_address"] == sample_agent
        assert result["security_level"] == "conservative"
        assert len(result["guardian_addresses"]) == 3
        assert "limits" in result
        
        # Verify agent is in registry
        assert sample_agent in security_manager.agent_profiles
        assert sample_agent in security_manager.guardian_contracts
    
    def test_duplicate_registration(self, security_manager, sample_agent, sample_guardians):
        """Test that duplicate registrations are rejected"""
        # Register agent once
        security_manager.register_agent(sample_agent, "conservative", sample_guardians)
        
        # Try to register again
        result = security_manager.register_agent(sample_agent, "aggressive", sample_guardians)
        
        assert result["status"] == "error"
        assert "already registered" in result["reason"]
    
    def test_transaction_protection(self, security_manager, sample_agent, sample_guardians):
        """Test transaction protection for registered agents"""
        # Register agent
        security_manager.register_agent(sample_agent, "conservative", sample_guardians)
        
        # Protect transaction
        result = security_manager.protect_transaction(
            agent_address=sample_agent,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50
        )
        
        assert result["status"] == "approved"
        assert "operation_id" in result
        
        # Test transaction exceeding limits
        result = security_manager.protect_transaction(
            agent_address=sample_agent,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=150  # Exceeds conservative per-transaction limit
        )
        
        assert result["status"] == "rejected"
        assert "per-transaction limit" in result["reason"]
    
    def test_unprotected_agent_transactions(self, security_manager, sample_agent):
        """Test transactions from unregistered agents"""
        result = security_manager.protect_transaction(
            agent_address=sample_agent,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50
        )
        
        assert result["status"] == "unprotected"
        assert "not registered" in result["reason"]
    
    def test_emergency_pause_integration(self, security_manager, sample_agent, sample_guardians):
        """Test emergency pause functionality"""
        # Register agent
        security_manager.register_agent(sample_agent, "conservative", sample_guardians)
        
        # Emergency pause by guardian
        result = security_manager.emergency_pause_agent(
            agent_address=sample_agent,
            guardian_address=sample_guardians[0]
        )
        
        assert result["status"] == "paused"
        
        # Verify transactions are blocked
        tx_result = security_manager.protect_transaction(
            agent_address=sample_agent,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50
        )
        
        assert tx_result["status"] == "unprotected"
        assert "disabled" in tx_result["reason"]
    
    def test_security_status_reporting(self, security_manager, sample_agent, sample_guardians):
        """Test security status reporting"""
        # Register agent
        security_manager.register_agent(sample_agent, "conservative", sample_guardians)
        
        # Get security status
        status = security_manager.get_agent_security_status(sample_agent)
        
        assert status["status"] == "protected"
        assert status["agent_address"] == sample_agent
        assert status["security_level"] == "conservative"
        assert status["enabled"] == True
        assert len(status["guardian_addresses"]) == 3
        assert "spending_status" in status
        assert "pending_operations" in status
    
    def test_security_level_configurations(self, security_manager, sample_agent, sample_guardians):
        """Test different security level configurations"""
        configurations = [
            ("conservative", CONSERVATIVE_CONFIG),
            ("aggressive", AGGRESSIVE_CONFIG),
            ("high_security", HIGH_SECURITY_CONFIG)
        ]
        
        for level, config in configurations:
            # Register with specific security level
            result = security_manager.register_agent(
                sample_agent + f"_{level}",
                level,
                sample_guardians
            )
            
            assert result["status"] == "registered"
            assert result["security_level"] == level
            
            # Verify limits match configuration
            limits = result["limits"]
            assert limits.per_transaction == config["per_transaction"]
            assert limits.per_hour == config["per_hour"]
            assert limits.per_day == config["per_day"]
            assert limits.per_week == config["per_week"]


class TestSecurityMonitoring:
    """Test security monitoring and detection features"""
    
    @pytest.fixture
    def security_manager(self):
        """Create a security manager with sample data"""
        manager = AgentWalletSecurity()
        
        # Register some test agents
        agents = [
            ("0x1111111111111111111111111111111111111111", "conservative"),
            ("0x2222222222222222222222222222222222222222", "aggressive"),
            ("0x3333333333333333333333333333333333333333", "high_security")
        ]
        
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        for agent_addr, level in agents:
            manager.register_agent(agent_addr, level, guardians)
        
        return manager
    
    def test_security_report_generation(self, security_manager):
        """Test comprehensive security report generation"""
        report = generate_security_report()
        
        assert "generated_at" in report
        assert "summary" in report
        assert "agents" in report
        assert "recent_security_events" in report
        assert "security_levels" in report
        
        summary = report["summary"]
        assert "total_protected_agents" in summary
        assert "active_agents" in summary
        assert "protection_coverage" in summary
        
        # Verify all security levels are represented
        levels = report["security_levels"]
        assert "conservative" in levels
        assert "aggressive" in levels
        assert "high_security" in levels
    
    def test_suspicious_activity_detection(self, security_manager):
        """Test suspicious activity detection"""
        agent_addr = "0x1111111111111111111111111111111111111111"
        
        # Test normal activity
        result = detect_suspicious_activity(agent_addr, hours=24)
        assert result["status"] == "analyzed"
        assert result["suspicious_activity"] == False
        
        # Simulate high activity by creating many transactions
        # (This would require more complex setup in a real test)
    
    def test_protected_agents_listing(self, security_manager):
        """Test listing of protected agents"""
        agents = security_manager.list_protected_agents()
        
        assert len(agents) == 3
        
        for agent in agents:
            assert "agent_address" in agent
            assert "security_level" in agent
            assert "enabled" in agent
            assert "guardian_count" in agent
            assert "pending_operations" in agent
            assert "paused" in agent
            assert "emergency_mode" in agent
            assert "registered_at" in agent


class TestConvenienceFunctions:
    """Test convenience functions for common operations"""
    
    def test_register_agent_for_protection(self):
        """Test the convenience registration function"""
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        result = register_agent_for_protection(
            agent_address=agent_addr,
            security_level="conservative",
            guardians=guardians
        )
        
        assert result["status"] == "registered"
        assert result["agent_address"] == agent_addr
        assert result["security_level"] == "conservative"
    
    def test_protect_agent_transaction(self):
        """Test the convenience transaction protection function"""
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        # Register first
        register_agent_for_protection(agent_addr, "conservative", guardians)
        
        # Protect transaction
        result = protect_agent_transaction(
            agent_address=agent_addr,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=50
        )
        
        assert result["status"] == "approved"
        assert "operation_id" in result
    
    def test_get_agent_security_summary(self):
        """Test the convenience security summary function"""
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        # Register first
        register_agent_for_protection(agent_addr, "conservative", guardians)
        
        # Get summary
        summary = get_agent_security_summary(agent_addr)
        
        assert summary["status"] == "protected"
        assert summary["agent_address"] == agent_addr
        assert summary["security_level"] == "conservative"
        assert "spending_status" in summary


class TestSecurityEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_invalid_address_handling(self):
        """Test handling of invalid addresses"""
        manager = AgentWalletSecurity()
        
        # Test invalid agent address
        result = manager.register_agent("invalid_address", "conservative")
        assert result["status"] == "error"
        
        # Test invalid guardian address
        result = manager.register_agent(
            "0x1234567890123456789012345678901234567890",
            "conservative",
            ["invalid_guardian"]
        )
        assert result["status"] == "error"
    
    def test_invalid_security_level(self):
        """Test handling of invalid security levels"""
        manager = AgentWalletSecurity()
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        
        result = manager.register_agent(agent_addr, "invalid_level")
        assert result["status"] == "error"
        assert "Invalid security level" in result["reason"]
    
    def test_zero_amount_transactions(self):
        """Test handling of zero amount transactions"""
        manager = AgentWalletSecurity()
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        # Register agent
        manager.register_agent(agent_addr, "conservative", guardians)
        
        # Test zero amount transaction
        result = manager.protect_transaction(
            agent_address=agent_addr,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=0
        )
        
        # Zero amount should be allowed (no spending)
        assert result["status"] == "approved"
    
    def test_negative_amount_transactions(self):
        """Test handling of negative amount transactions"""
        manager = AgentWalletSecurity()
        agent_addr = to_checksum_address("0x1234567890123456789012345678901234567890")
        guardians = [
            to_checksum_address(f"0x{'0'*38}{i:02d}") 
            for i in range(1, 4)
        ]
        
        # Register agent
        manager.register_agent(agent_addr, "conservative", guardians)
        
        # Test negative amount transaction
        result = manager.protect_transaction(
            agent_address=agent_addr,
            to_address="0xabcdef123456789012345678901234567890abcd",
            amount=-100
        )
        
        # Negative amounts should be rejected
        assert result["status"] == "rejected"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
