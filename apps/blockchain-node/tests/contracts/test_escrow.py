"""
Tests for Escrow System
"""

import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import Mock, patch

from aitbc_chain.contracts.escrow import EscrowManager, EscrowState, DisputeReason

class TestEscrowManager:
    """Test cases for escrow manager"""
    
    def setup_method(self):
        """Setup test environment"""
        self.escrow_manager = EscrowManager()
    
    def test_create_contract(self):
        """Test escrow contract creation"""
        success, message, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_001",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        assert success, f"Contract creation failed: {message}"
        assert contract_id is not None
        
        # Check contract details
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract is not None
        assert contract.job_id == "job_001"
        assert contract.client_address == "0x1234567890123456789012345678901234567890"
        assert contract.agent_address == "0x2345678901234567890123456789012345678901"
        assert contract.amount > Decimal('100.0')  # Includes platform fee
        assert contract.state == EscrowState.CREATED
    
    def test_create_contract_invalid_inputs(self):
        """Test contract creation with invalid inputs"""
        success, message, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="",  # Empty job ID
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        assert not success
        assert contract_id is None
        assert "invalid" in message.lower()
    
    def test_create_contract_with_milestones(self):
        """Test contract creation with milestones"""
        milestones = [
            {
                'milestone_id': 'milestone_1',
                'description': 'Initial setup',
                'amount': Decimal('30.0')
            },
            {
                'milestone_id': 'milestone_2',
                'description': 'Main work',
                'amount': Decimal('50.0')
            },
            {
                'milestone_id': 'milestone_3',
                'description': 'Final delivery',
                'amount': Decimal('20.0')
            }
        ]
        
        success, message, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_002",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0'),
                milestones=milestones
            )
        )
        
        assert success
        assert contract_id is not None
        
        # Check milestones
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert len(contract.milestones) == 3
        assert contract.milestones[0]['amount'] == Decimal('30.0')
        assert contract.milestones[1]['amount'] == Decimal('50.0')
        assert contract.milestones[2]['amount'] == Decimal('20.0')
    
    def test_create_contract_invalid_milestones(self):
        """Test contract creation with invalid milestones"""
        milestones = [
            {
                'milestone_id': 'milestone_1',
                'description': 'Setup',
                'amount': Decimal('30.0')
            },
            {
                'milestone_id': 'milestone_2',
                'description': 'Main work',
                'amount': Decimal('80.0')  # Total exceeds contract amount
            }
        ]
        
        success, message, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_003",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0'),
                milestones=milestones
            )
        )
        
        assert not success
        assert "milestones" in message.lower()
    
    def test_fund_contract(self):
        """Test funding contract"""
        # Create contract first
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_004",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        assert success
        
        # Fund contract
        success, message = asyncio.run(
            self.escrow_manager.fund_contract(contract_id, "tx_hash_001")
        )
        
        assert success, f"Contract funding failed: {message}"
        
        # Check state
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.FUNDED
    
    def test_fund_already_funded_contract(self):
        """Test funding already funded contract"""
        # Create and fund contract
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_005",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        
        # Try to fund again
        success, message = asyncio.run(
            self.escrow_manager.fund_contract(contract_id, "tx_hash_002")
        )
        
        assert not success
        assert "state" in message.lower()
    
    def test_start_job(self):
        """Test starting job"""
        # Create and fund contract
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_006",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        
        # Start job
        success, message = asyncio.run(self.escrow_manager.start_job(contract_id))
        
        assert success, f"Job start failed: {message}"
        
        # Check state
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.JOB_STARTED
    
    def test_complete_milestone(self):
        """Test completing milestone"""
        milestones = [
            {
                'milestone_id': 'milestone_1',
                'description': 'Setup',
                'amount': Decimal('50.0')
            },
            {
                'milestone_id': 'milestone_2',
                'description': 'Delivery',
                'amount': Decimal('50.0')
            }
        ]
        
        # Create contract with milestones
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_007",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0'),
                milestones=milestones
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        asyncio.run(self.escrow_manager.start_job(contract_id))
        
        # Complete milestone
        success, message = asyncio.run(
            self.escrow_manager.complete_milestone(contract_id, "milestone_1")
        )
        
        assert success, f"Milestone completion failed: {message}"
        
        # Check milestone status
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        milestone = contract.milestones[0]
        assert milestone['completed']
        assert milestone['completed_at'] is not None
    
    def test_verify_milestone(self):
        """Test verifying milestone"""
        milestones = [
            {
                'milestone_id': 'milestone_1',
                'description': 'Setup',
                'amount': Decimal('50.0')
            }
        ]
        
        # Create contract with milestone
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_008",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0'),
                milestones=milestones
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        asyncio.run(self.escrow_manager.start_job(contract_id))
        asyncio.run(self.escrow_manager.complete_milestone(contract_id, "milestone_1"))
        
        # Verify milestone
        success, message = asyncio.run(
            self.escrow_manager.verify_milestone(contract_id, "milestone_1", True, "Work completed successfully")
        )
        
        assert success, f"Milestone verification failed: {message}"
        
        # Check verification status
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        milestone = contract.milestones[0]
        assert milestone['verified']
        assert milestone['verification_feedback'] == "Work completed successfully"
    
    def test_create_dispute(self):
        """Test creating dispute"""
        # Create and fund contract
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_009",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        asyncio.run(self.escrow_manager.start_job(contract_id))
        
        # Create dispute
        evidence = [
            {
                'type': 'screenshot',
                'description': 'Poor quality work',
                'timestamp': time.time()
            }
        ]
        
        success, message = asyncio.run(
            self.escrow_manager.create_dispute(
                contract_id, DisputeReason.QUALITY_ISSUES, "Work quality is poor", evidence
            )
        )
        
        assert success, f"Dispute creation failed: {message}"
        
        # Check dispute status
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.DISPUTED
        assert contract.dispute_reason == DisputeReason.QUALITY_ISSUES
    
    def test_resolve_dispute(self):
        """Test resolving dispute"""
        # Create and fund contract
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_010",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        asyncio.run(self.escrow_manager.start_job(contract_id))
        
        # Create dispute
        asyncio.run(
            self.escrow_manager.create_dispute(
                contract_id, DisputeReason.QUALITY_ISSUES, "Quality issues"
            )
        )
        
        # Resolve dispute
        resolution = {
            'winner': 'client',
            'client_refund': 0.8,  # 80% refund
            'agent_payment': 0.2   # 20% payment
        }
        
        success, message = asyncio.run(
            self.escrow_manager.resolve_dispute(contract_id, resolution)
        )
        
        assert success, f"Dispute resolution failed: {message}"
        
        # Check resolution
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.RESOLVED
        assert contract.resolution == resolution
    
    def test_refund_contract(self):
        """Test refunding contract"""
        # Create and fund contract
        success, _, contract_id = asyncio.run(
            self.escrow_manager.create_contract(
                job_id="job_011",
                client_address="0x1234567890123456789012345678901234567890",
                agent_address="0x2345678901234567890123456789012345678901",
                amount=Decimal('100.0')
            )
        )
        
        asyncio.run(self.escrow_manager.fund_contract(contract_id, "tx_hash_001"))
        
        # Refund contract
        success, message = asyncio.run(
            self.escrow_manager.refund_contract(contract_id, "Client requested refund")
        )
        
        assert success, f"Refund failed: {message}"
        
        # Check refund status
        contract = asyncio.run(self.escrow_manager.get_contract_info(contract_id))
        assert contract.state == EscrowState.REFUNDED
        assert contract.refunded_amount > 0
    
    def test_get_escrow_statistics(self):
        """Test getting escrow statistics"""
        # Create multiple contracts
        for i in range(5):
            asyncio.run(
                self.escrow_manager.create_contract(
                    job_id=f"job_{i:03d}",
                    client_address=f"0x123456789012345678901234567890123456789{i}",
                    agent_address=f"0x234567890123456789012345678901234567890{i}",
                    amount=Decimal('100.0')
                )
            )
        
        stats = asyncio.run(self.escrow_manager.get_escrow_statistics())
        
        assert 'total_contracts' in stats
        assert 'active_contracts' in stats
        assert 'disputed_contracts' in stats
        assert 'state_distribution' in stats
        assert 'total_amount' in stats
        assert stats['total_contracts'] >= 5

if __name__ == "__main__":
    pytest.main([__file__])
