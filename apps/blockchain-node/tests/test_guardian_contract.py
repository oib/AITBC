"""Test suite for Guardian Contract - Agent wallet security and spending limits."""

from __future__ import annotations

import sys
import pytest
import tempfile
import shutil
from datetime import datetime, UTC, timedelta
from pathlib import Path
from unittest.mock import patch, Mock
from typing import Generator

from aitbc_chain.contracts.guardian_contract import (
    GuardianContract, 
    GuardianConfig, 
    SpendingLimit,
    TimeLockConfig
)


@pytest.fixture
def temp_storage_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for contract storage."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def guardian_config() -> GuardianConfig:
    """Create a test guardian configuration."""
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
            max_delay_hours=168  # 1 week max
        ),
        guardians=["0xguardian1", "0xguardian2", "0xguardian3"]
    )


@pytest.fixture
def agent_address() -> str:
    """Test agent address."""
    return "0x1234567890123456789012345678901234567890"


@pytest.fixture
def guardian_contract(
    agent_address: str, 
    guardian_config: GuardianConfig, 
    temp_storage_dir: Path
) -> Generator[GuardianContract, None, None]:
    """Create a guardian contract instance."""
    contract = GuardianContract(
        agent_address=agent_address,
        config=guardian_config,
        storage_path=str(temp_storage_dir)
    )
    yield contract
    # Cleanup is handled by temp_storage_dir fixture


class TestGuardianContract:
    """Test Guardian Contract functionality."""

    def test_contract_initialization(
        self, 
        agent_address: str, 
        guardian_config: GuardianConfig, 
        temp_storage_dir: Path
    ) -> None:
        """Test contract initialization."""
        contract = GuardianContract(
            agent_address=agent_address,
            config=guardian_config,
            storage_path=str(temp_storage_dir)
        )
        
        assert contract.agent_address == agent_address.lower()
        assert contract.config == guardian_config
        assert contract.storage_dir == temp_storage_dir
        assert contract.paused is False
        assert contract.emergency_mode is False
        assert contract.nonce == 0
        assert len(contract.spending_history) == 0
        assert len(contract.pending_operations) == 0

    def test_storage_initialization(self, guardian_contract: GuardianContract) -> None:
        """Test that storage is properly initialized."""
        assert guardian_contract.db_path.exists()
        assert guardian_contract.db_path.is_file()

    def test_spending_limit_check_per_transaction(self, guardian_contract: GuardianContract) -> None:
        """Test per-transaction spending limit."""
        # Should pass for amount within limit
        allowed, message = guardian_contract._check_spending_limits(500)
        assert allowed is True
        assert "passed" in message.lower()
        
        # Should fail for amount exceeding limit
        allowed, message = guardian_contract._check_spending_limits(1500)
        assert allowed is False
        assert "per-transaction limit" in message

    def test_spending_limit_check_hourly(self, guardian_contract: GuardianContract) -> None:
        """Test hourly spending limit."""
        # Add some spending history
        base_time = datetime.now(datetime.UTC)
        guardian_contract.spending_history = [
            {
                "operation_id": "op1",
                "to": "0xrecipient",
                "amount": 3000,
                "data": "",
                "timestamp": base_time.isoformat(),
                "executed_at": base_time.isoformat(),
                "status": "completed",
                "nonce": 1
            }
        ]
        
        # Should fail when exceeding hourly limit
        allowed, message = guardian_contract._check_spending_limits(2500, base_time)
        assert allowed is False
        assert "hourly spending" in message
        
        # Should pass for smaller amount
        allowed, message = guardian_contract._check_spending_limits(1500, base_time)
        assert allowed is True

    def test_spending_limit_check_daily(self, guardian_contract: GuardianContract) -> None:
        """Test daily spending limit."""
        # Add spending history across the day
        base_time = datetime.now(datetime.UTC)
        guardian_contract.spending_history = [
            {
                "operation_id": "op1",
                "to": "0xrecipient",
                "amount": 15000,
                "data": "",
                "timestamp": base_time.isoformat(),
                "executed_at": base_time.isoformat(),
                "status": "completed",
                "nonce": 1
            }
        ]
        
        # Should fail when exceeding daily limit
        allowed, message = guardian_contract._check_spending_limits(6000, base_time)
        assert allowed is False
        assert "daily spending" in message
        
        # Should pass for smaller amount
        allowed, message = guardian_contract._check_spending_limits(4000, base_time)
        assert allowed is True

    def test_spending_limit_check_weekly(self, guardian_contract: GuardianContract) -> None:
        """Test weekly spending limit."""
        # Add spending history across the week
        base_time = datetime.now(datetime.UTC)
        guardian_contract.spending_history = [
            {
                "operation_id": "op1",
                "to": "0xrecipient",
                "amount": 80000,
                "data": "",
                "timestamp": base_time.isoformat(),
                "executed_at": base_time.isoformat(),
                "status": "completed",
                "nonce": 1
            }
        ]
        
        # Should fail when exceeding weekly limit
        allowed, message = guardian_contract._check_spending_limits(25000, base_time)
        assert allowed is False
        assert "weekly spending" in message
        
        # Should pass for smaller amount
        allowed, message = guardian_contract._check_spending_limits(15000, base_time)
        assert allowed is True

    def test_time_lock_requirement(self, guardian_contract: GuardianContract) -> None:
        """Test time lock requirement for large amounts."""
        # Should require time lock for amounts >= threshold
        assert guardian_contract._requires_time_lock(5000) is True
        assert guardian_contract._requires_time_lock(10000) is True
        
        # Should not require time lock for amounts < threshold
        assert guardian_contract._requires_time_lock(4000) is False
        assert guardian_contract._requires_time_lock(1000) is False

    def test_initiate_transaction_small_amount(self, guardian_contract: GuardianContract) -> None:
        """Test initiating transaction with small amount (no time lock)."""
        result = guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=1000,
            data="test transaction"
        )
        
        assert result["status"] == "approved"
        assert "operation_id" in result
        assert "approved for execution" in result["message"]
        
        # Check operation is stored
        operation_id = result["operation_id"]
        assert operation_id in guardian_contract.pending_operations
        assert guardian_contract.pending_operations[operation_id]["status"] == "pending"

    def test_initiate_transaction_large_amount(self, guardian_contract: GuardianContract) -> None:
        """Test initiating transaction with large amount (time lock required)."""
        result = guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=6000,
            data="large transaction"
        )
        
        assert result["status"] == "time_locked"
        assert "operation_id" in result
        assert "unlock_time" in result
        assert "delay_hours" in result
        assert result["delay_hours"] == 24
        assert "time lock" in result["message"].lower()
        
        # Check operation is stored with time lock
        operation_id = result["operation_id"]
        assert operation_id in guardian_contract.pending_operations
        assert guardian_contract.pending_operations[operation_id]["status"] == "time_locked"
        assert "unlock_time" in guardian_contract.pending_operations[operation_id]

    def test_initiate_transaction_exceeds_limit(self, guardian_contract: GuardianContract) -> None:
        """Test initiating transaction that exceeds spending limits."""
        result = guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=1500,  # Exceeds per-transaction limit
            data="excessive transaction"
        )
        
        assert result["status"] == "rejected"
        assert "exceeds per-transaction limit" in result["message"]
        assert "operation_id" not in result

    def test_execute_transaction_success(self, guardian_contract: GuardianContract) -> None:
        """Test successful transaction execution."""
        # First initiate a transaction
        init_result = guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=1000,
            data="test transaction"
        )
        
        operation_id = init_result["operation_id"]
        signature = "0xsignature"
        
        # Execute the transaction
        result = guardian_contract.execute_transaction(operation_id, signature)
        
        assert result["status"] == "executed"
        assert operation_id in result
        assert "executed successfully" in result["message"]
        
        # Check operation is no longer pending
        assert operation_id not in guardian_contract.pending_operations
        
        # Check it's in spending history
        assert len(guardian_contract.spending_history) > 0
        executed_tx = next(tx for tx in guardian_contract.spending_history if tx["operation_id"] == operation_id)
        assert executed_tx["status"] == "completed"
        assert executed_tx["to"] == "0xrecipient"
        assert executed_tx["amount"] == 1000

    def test_execute_transaction_not_found(self, guardian_contract: GuardianContract) -> None:
        """Test executing transaction that doesn't exist."""
        result = guardian_contract.execute_transaction("nonexistent_id", "0xsignature")
        
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_execute_transaction_time_locked(self, guardian_contract: GuardianContract) -> None:
        """Test executing transaction that is still time locked."""
        # Initiate a large transaction that gets time locked
        init_result = guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=6000,
            data="large transaction"
        )
        
        operation_id = init_result["operation_id"]
        signature = "0xsignature"
        
        # Try to execute before time lock expires
        result = guardian_contract.execute_transaction(operation_id, signature)
        
        assert result["status"] == "error"
        assert "time locked" in result["message"].lower()

    def test_emergency_pause(self, guardian_contract: GuardianContract) -> None:
        """Test emergency pause functionality."""
        # Emergency pause
        result = guardian_contract.emergency_pause("0xguardian1")
        
        assert result["status"] == "paused"
        assert "Emergency pause activated" in result["message"]
        assert guardian_contract.paused is True

    def test_emergency_unpause(self, guardian_contract: GuardianContract) -> None:
        """Test emergency unpause functionality."""
        # First pause
        guardian_contract.emergency_pause("0xguardian1")
        
        # Then unpause with signatures
        result = guardian_contract.emergency_unpause(["0xguardian1", "0xguardian2"])
        
        assert result["status"] == "active"
        assert "Emergency pause lifted" in result["message"]
        assert guardian_contract.paused is False

    def test_get_spending_status(self, guardian_contract: GuardianContract) -> None:
        """Test getting spending status."""
        status = guardian_contract.get_spending_status()
        
        assert "spent_hour" in status
        assert "spent_day" in status
        assert "spent_week" in status
        assert "limits" in status
        assert "paused" in status
        assert "emergency_mode" in status
        assert "nonce" in status

    def test_period_key_generation(self, guardian_contract: GuardianContract) -> None:
        """Test period key generation for different time periods."""
        base_time = datetime(2023, 6, 15, 14, 30, 0)  # Thursday 2:30 PM
        
        # Hour key should be YYYY-MM-DD-HH
        hour_key = guardian_contract._get_period_key(base_time, "hour")
        assert hour_key == "2023-06-15-14"
        
        # Day key should be YYYY-MM-DD
        day_key = guardian_contract._get_period_key(base_time, "day")
        assert day_key == "2023-06-15"
        
        # Week key should be YYYY-WW (ISO week)
        week_key = guardian_contract._get_period_key(base_time, "week")
        assert week_key.startswith("2023-")  # Should be 2023-W24 for this date

    def test_operation_hash_creation(self, guardian_contract: GuardianContract) -> None:
        """Test operation hash creation."""
        operation = {
            "to": "0xrecipient",
            "amount": 1000,
            "nonce": 1
        }
        
        hash1 = guardian_contract._create_operation_hash(operation)
        hash2 = guardian_contract._create_operation_hash(operation)
        
        # Same operation should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # 64 hex chars (no 0x prefix)

    def test_persistence_across_instances(
        self, 
        agent_address: str, 
        guardian_config: GuardianConfig, 
        temp_storage_dir: Path
    ) -> None:
        """Test that contract state persists across instances."""
        # Create first instance and add data
        contract1 = GuardianContract(
            agent_address=agent_address,
            config=guardian_config,
            storage_path=str(temp_storage_dir)
        )
        
        contract1.initiate_transaction(
            to_address="0xrecipient",
            amount=1000,
            data="persistence test"
        )
        
        # Create second instance and check data is loaded
        contract2 = GuardianContract(
            agent_address=agent_address,
            config=guardian_config,
            storage_path=str(temp_storage_dir)
        )
        
        assert len(contract2.pending_operations) == 1
        assert contract2.nonce == 1

    def test_config_properties(self, guardian_contract: GuardianContract) -> None:
        """Test that configuration properties are properly set."""
        assert guardian_contract.config.limits.per_transaction == 1000
        assert guardian_contract.config.limits.per_hour == 5000
        assert guardian_contract.config.limits.per_day == 20000
        assert guardian_contract.config.limits.per_week == 100000
        assert guardian_contract.config.time_lock.threshold == 5000
        assert guardian_contract.config.time_lock.delay_hours == 24
        assert guardian_contract.config.time_lock.max_delay_hours == 168
        assert guardian_contract.config.guardians == ["0xguardian1", "0xguardian2", "0xguardian3"]

    def test_nonce_increment(self, guardian_contract: GuardianContract) -> None:
        """Test that nonce increments properly."""
        initial_nonce = guardian_contract.nonce
        
        # Initiate transaction
        guardian_contract.initiate_transaction(
            to_address="0xrecipient",
            amount=1000,
            data="nonce test"
        )
        
        assert guardian_contract.nonce == initial_nonce + 1

    def test_get_pending_operations(self, guardian_contract: GuardianContract) -> None:
        """Test getting list of pending operations."""
        # Add some pending operations
        result1 = guardian_contract.initiate_transaction(
            to_address="0xrecipient1",
            amount=1000,
            data="pending 1"
        )
        
        result2 = guardian_contract.initiate_transaction(
            to_address="0xrecipient2",
            amount=2000,
            data="pending 2"
        )
        
        pending = guardian_contract.get_pending_operations()
        
        assert len(pending) == 2
        assert result1["operation_id"] in pending
        assert result2["operation_id"] in pending
