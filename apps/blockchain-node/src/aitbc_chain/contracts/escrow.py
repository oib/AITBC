"""
Smart Contract Escrow System
Handles automated payment holding and release for AI job marketplace
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal

def log_info(message: str):
    """Simple logging function"""
    print(f"[EscrowManager] {message}")

class EscrowState(Enum):
    CREATED = "created"
    FUNDED = "funded"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    DISPUTED = "disputed"
    RESOLVED = "resolved"
    RELEASED = "released"
    REFUNDED = "refunded"
    EXPIRED = "expired"

class DisputeReason(Enum):
    QUALITY_ISSUES = "quality_issues"
    DELIVERY_LATE = "delivery_late"
    INCOMPLETE_WORK = "incomplete_work"
    TECHNICAL_ISSUES = "technical_issues"
    PAYMENT_DISPUTE = "payment_dispute"
    OTHER = "other"

@dataclass
class EscrowContract:
    contract_id: str
    job_id: str
    client_address: str
    agent_address: str
    amount: Decimal
    fee_rate: Decimal  # Platform fee rate
    created_at: float
    expires_at: float
    state: EscrowState
    milestones: List[Dict]
    current_milestone: int
    dispute_reason: Optional[DisputeReason]
    dispute_evidence: List[Dict]
    resolution: Optional[Dict]
    released_amount: Decimal
    refunded_amount: Decimal

@dataclass
class Milestone:
    milestone_id: str
    description: str
    amount: Decimal
    completed: bool
    completed_at: Optional[float]
    verified: bool

class EscrowManager:
    """Manages escrow contracts for AI job marketplace"""
    
    def __init__(self):
        self.escrow_contracts: Dict[str, EscrowContract] = {}
        self.active_contracts: Set[str] = set()
        self.disputed_contracts: Set[str] = set()
        
        # Escrow parameters
        self.default_fee_rate = Decimal('0.025')  # 2.5% platform fee
        self.max_contract_duration = 86400 * 30  # 30 days
        self.dispute_timeout = 86400 * 7  # 7 days for dispute resolution
        self.min_dispute_evidence = 1
        self.max_dispute_evidence = 10
        
        # Milestone parameters
        self.min_milestone_amount = Decimal('0.01')
        self.max_milestones = 10
        self.verification_timeout = 86400  # 24 hours for milestone verification
    
    async def create_contract(self, job_id: str, client_address: str, agent_address: str,
                            amount: Decimal, fee_rate: Optional[Decimal] = None,
                            milestones: Optional[List[Dict]] = None,
                            duration_days: int = 30) -> Tuple[bool, str, Optional[str]]:
        """Create new escrow contract"""
        try:
            # Validate inputs
            if not self._validate_contract_inputs(job_id, client_address, agent_address, amount):
                return False, "Invalid contract inputs", None
            
            # Calculate fee
            fee_rate = fee_rate or self.default_fee_rate
            platform_fee = amount * fee_rate
            total_amount = amount + platform_fee
            
            # Validate milestones
            validated_milestones = []
            if milestones:
                validated_milestones = await self._validate_milestones(milestones, amount)
                if not validated_milestones:
                    return False, "Invalid milestones configuration", None
            else:
                # Create single milestone for full amount
                validated_milestones = [{
                    'milestone_id': 'milestone_1',
                    'description': 'Complete job',
                    'amount': amount,
                    'completed': False
                }]
            
            # Create contract
            contract_id = self._generate_contract_id(client_address, agent_address, job_id)
            current_time = time.time()
            
            contract = EscrowContract(
                contract_id=contract_id,
                job_id=job_id,
                client_address=client_address,
                agent_address=agent_address,
                amount=total_amount,
                fee_rate=fee_rate,
                created_at=current_time,
                expires_at=current_time + (duration_days * 86400),
                state=EscrowState.CREATED,
                milestones=validated_milestones,
                current_milestone=0,
                dispute_reason=None,
                dispute_evidence=[],
                resolution=None,
                released_amount=Decimal('0'),
                refunded_amount=Decimal('0')
            )
            
            self.escrow_contracts[contract_id] = contract
            
            log_info(f"Escrow contract created: {contract_id} for job {job_id}")
            return True, "Contract created successfully", contract_id
            
        except Exception as e:
            return False, f"Contract creation failed: {str(e)}", None
    
    def _validate_contract_inputs(self, job_id: str, client_address: str, 
                                 agent_address: str, amount: Decimal) -> bool:
        """Validate contract creation inputs"""
        if not all([job_id, client_address, agent_address]):
            return False
        
        # Validate addresses (simplified)
        if not (client_address.startswith('0x') and len(client_address) == 42):
            return False
        if not (agent_address.startswith('0x') and len(agent_address) == 42):
            return False
        
        # Validate amount
        if amount <= 0:
            return False
        
        # Check for existing contract
        for contract in self.escrow_contracts.values():
            if contract.job_id == job_id:
                return False  # Contract already exists for this job
        
        return True
    
    async def _validate_milestones(self, milestones: List[Dict], total_amount: Decimal) -> Optional[List[Dict]]:
        """Validate milestone configuration"""
        if not milestones or len(milestones) > self.max_milestones:
            return None
        
        validated_milestones = []
        milestone_total = Decimal('0')
        
        for i, milestone_data in enumerate(milestones):
            # Validate required fields
            required_fields = ['milestone_id', 'description', 'amount']
            if not all(field in milestone_data for field in required_fields):
                return None
            
            # Validate amount
            amount = Decimal(str(milestone_data['amount']))
            if amount < self.min_milestone_amount:
                return None
            
            milestone_total += amount
            validated_milestones.append({
                'milestone_id': milestone_data['milestone_id'],
                'description': milestone_data['description'],
                'amount': amount,
                'completed': False
            })
        
        # Check if milestone amounts sum to total
        if abs(milestone_total - total_amount) > Decimal('0.01'):  # Allow small rounding difference
            return None
        
        return validated_milestones
    
    def _generate_contract_id(self, client_address: str, agent_address: str, job_id: str) -> str:
        """Generate unique contract ID"""
        import hashlib
        content = f"{client_address}:{agent_address}:{job_id}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def fund_contract(self, contract_id: str, payment_tx_hash: str) -> Tuple[bool, str]:
        """Fund escrow contract"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state != EscrowState.CREATED:
            return False, f"Cannot fund contract in {contract.state.value} state"
        
        # In real implementation, this would verify the payment transaction
        # For now, assume payment is valid
        
        contract.state = EscrowState.FUNDED
        self.active_contracts.add(contract_id)
        
        log_info(f"Contract funded: {contract_id}")
        return True, "Contract funded successfully"
    
    async def start_job(self, contract_id: str) -> Tuple[bool, str]:
        """Mark job as started"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state != EscrowState.FUNDED:
            return False, f"Cannot start job in {contract.state.value} state"
        
        contract.state = EscrowState.JOB_STARTED
        
        log_info(f"Job started for contract: {contract_id}")
        return True, "Job started successfully"
    
    async def complete_milestone(self, contract_id: str, milestone_id: str, 
                               evidence: Dict = None) -> Tuple[bool, str]:
        """Mark milestone as completed"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED, EscrowState.JOB_COMPLETED]:
            return False, f"Cannot complete milestone in {contract.state.value} state"
        
        # Find milestone
        milestone = None
        for ms in contract.milestones:
            if ms['milestone_id'] == milestone_id:
                milestone = ms
                break
        
        if not milestone:
            return False, "Milestone not found"
        
        if milestone['completed']:
            return False, "Milestone already completed"
        
        # Mark as completed
        milestone['completed'] = True
        milestone['completed_at'] = time.time()
        
        # Add evidence if provided
        if evidence:
            milestone['evidence'] = evidence
        
        # Only transition to JOB_COMPLETED if we have multiple milestones and all are complete
        # Don't auto-transition when milestones are being added incrementally
        if len(contract.milestones) > 1:
            all_completed = all(ms['completed'] for ms in contract.milestones)
            if all_completed:
                contract.state = EscrowState.JOB_COMPLETED
        
        log_info(f"Milestone {milestone_id} completed for contract: {contract_id}")
        return True, "Milestone completed successfully"
    
    async def _release_milestone_payment(self, contract_id: str, milestone_id: str):
        """Release payment for verified milestone"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return
        
        # Find milestone
        milestone = None
        for ms in contract.milestones:
            if ms['milestone_id'] == milestone_id:
                milestone = ms
                break
        
        if not milestone:
            return
        
        # Calculate payment amount (minus platform fee)
        milestone_amount = Decimal(str(milestone['amount']))
        platform_fee = milestone_amount * contract.fee_rate
        payment_amount = milestone_amount - platform_fee
        
        # Update released amount
        contract.released_amount += payment_amount
        
        # In real implementation, this would trigger actual payment transfer
        log_info(f"Released {payment_amount} for milestone {milestone_id} in contract {contract_id}")
    
    async def release_full_payment(self, contract_id: str) -> Tuple[bool, str]:
        """Release full payment to agent"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state != EscrowState.JOB_COMPLETED:
            return False, f"Cannot release payment in {contract.state.value} state"
        
        # Check if all milestones are verified
        all_verified = all(ms.get('verified', False) for ms in contract.milestones)
        if not all_verified:
            return False, "Not all milestones are verified"
        
        # Calculate remaining payment
        total_milestone_amount = sum(Decimal(str(ms['amount'])) for ms in contract.milestones)
        platform_fee_total = total_milestone_amount * contract.fee_rate
        remaining_payment = total_milestone_amount - contract.released_amount - platform_fee_total
        
        if remaining_payment > 0:
            contract.released_amount += remaining_payment
        
        contract.state = EscrowState.RELEASED
        self.active_contracts.discard(contract_id)
        
        log_info(f"Full payment released for contract: {contract_id}")
        return True, "Payment released successfully"
    
    async def create_dispute(self, contract_id: str, reason: DisputeReason, 
                           description: str, evidence: List[Dict] = None) -> Tuple[bool, str]:
        """Create dispute for contract"""
        return await self._create_dispute(contract_id, reason, description, evidence)
    
    async def _create_dispute(self, contract_id: str, reason: DisputeReason, 
                           description: str, evidence: List[Dict] = None):
        """Internal dispute creation method"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state == EscrowState.DISPUTED:
            return False, "Contract already disputed"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED, EscrowState.JOB_COMPLETED]:
            return False, f"Cannot dispute contract in {contract.state.value} state"
        
        # Validate evidence
        if evidence and (len(evidence) < self.min_dispute_evidence or len(evidence) > self.max_dispute_evidence):
            return False, f"Invalid evidence count: {len(evidence)}"
        
        # Create dispute
        contract.state = EscrowState.DISPUTED
        contract.dispute_reason = reason
        contract.dispute_evidence = evidence or []
        contract.dispute_created_at = time.time()
        
        self.disputed_contracts.add(contract_id)
        
        log_info(f"Dispute created for contract: {contract_id} - {reason.value}")
        return True, "Dispute created successfully"
    
    async def resolve_dispute(self, contract_id: str, resolution: Dict) -> Tuple[bool, str]:
        """Resolve dispute with specified outcome"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state != EscrowState.DISPUTED:
            return False, f"Contract not in disputed state: {contract.state.value}"
        
        # Validate resolution
        required_fields = ['winner', 'client_refund', 'agent_payment']
        if not all(field in resolution for field in required_fields):
            return False, "Invalid resolution format"
        
        winner = resolution['winner']
        client_refund = Decimal(str(resolution['client_refund']))
        agent_payment = Decimal(str(resolution['agent_payment']))
        
        # Validate amounts
        total_refund = client_refund + agent_payment
        if total_refund > contract.amount:
            return False, "Refund amounts exceed contract amount"
        
        # Apply resolution
        contract.resolution = resolution
        contract.state = EscrowState.RESOLVED
        
        # Update amounts
        contract.released_amount += agent_payment
        contract.refunded_amount += client_refund
        
        # Remove from disputed contracts
        self.disputed_contracts.discard(contract_id)
        self.active_contracts.discard(contract_id)
        
        log_info(f"Dispute resolved for contract: {contract_id} - Winner: {winner}")
        return True, "Dispute resolved successfully"
    
    async def refund_contract(self, contract_id: str, reason: str = "") -> Tuple[bool, str]:
        """Refund contract to client"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state in [EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.EXPIRED]:
            return False, f"Cannot refund contract in {contract.state.value} state"
        
        # Calculate refund amount (minus any released payments)
        refund_amount = contract.amount - contract.released_amount
        
        if refund_amount <= 0:
            return False, "No amount available for refund"
        
        contract.state = EscrowState.REFUNDED
        contract.refunded_amount = refund_amount
        
        self.active_contracts.discard(contract_id)
        self.disputed_contracts.discard(contract_id)
        
        log_info(f"Contract refunded: {contract_id} - Amount: {refund_amount}")
        return True, "Contract refunded successfully"
    
    async def expire_contract(self, contract_id: str) -> Tuple[bool, str]:
        """Mark contract as expired"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if time.time() < contract.expires_at:
            return False, "Contract has not expired yet"
        
        if contract.state in [EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.EXPIRED]:
            return False, f"Contract already in final state: {contract.state.value}"
        
        # Auto-refund if no work has been done
        if contract.state == EscrowState.FUNDED:
            return await self.refund_contract(contract_id, "Contract expired")
        
        # Handle other states based on work completion
        contract.state = EscrowState.EXPIRED
        self.active_contracts.discard(contract_id)
        self.disputed_contracts.discard(contract_id)
        
        # Contract expired successfully
        return True, "Contract expired successfully"
    
    async def get_contract_info(self, contract_id: str) -> Optional[EscrowContract]:
        """Get contract information"""
        return self.escrow_contracts.get(contract_id)
    
    async def get_contracts_by_client(self, client_address: str) -> List[EscrowContract]:
        """Get contracts for specific client"""
        return [
            contract for contract in self.escrow_contracts.values()
            if contract.client_address == client_address
        ]
    
    async def get_contracts_by_agent(self, agent_address: str) -> List[EscrowContract]:
        """Get contracts for specific agent"""
        return [
            contract for contract in self.escrow_contracts.values()
            if contract.agent_address == agent_address
        ]
    
    async def get_active_contracts(self) -> List[EscrowContract]:
        """Get all active contracts"""
        return [
            self.escrow_contracts[contract_id] 
            for contract_id in self.active_contracts
            if contract_id in self.escrow_contracts
        ]
    
    async def get_disputed_contracts(self) -> List[EscrowContract]:
        """Get all disputed contracts"""
        return [
            self.escrow_contracts[contract_id]
            for contract_id in self.disputed_contracts
            if contract_id in self.escrow_contracts
        ]
    
    async def get_escrow_statistics(self) -> Dict:
        """Get escrow system statistics"""
        total_contracts = len(self.escrow_contracts)
        active_count = len(self.active_contracts)
        disputed_count = len(self.disputed_contracts)
        
        # State distribution
        state_counts = {}
        for contract in self.escrow_contracts.values():
            state = contract.state.value
            state_counts[state] = state_counts.get(state, 0) + 1
        
        # Financial statistics
        total_amount = sum(contract.amount for contract in self.escrow_contracts.values())
        total_released = sum(contract.released_amount for contract in self.escrow_contracts.values())
        total_refunded = sum(contract.refunded_amount for contract in self.escrow_contracts.values())
        total_fees = total_amount - total_released - total_refunded
        
        return {
            'total_contracts': total_contracts,
            'active_contracts': active_count,
            'disputed_contracts': disputed_count,
            'state_distribution': state_counts,
            'total_amount': float(total_amount),
            'total_released': float(total_released),
            'total_refunded': float(total_refunded),
            'total_fees': float(total_fees)
        }
    
    async def add_milestone(self, contract_id: str, milestone_id: str, 
                          amount: Decimal, description: str = "") -> Tuple[bool, str]:
        """Add a milestone to an escrow contract"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED]:
            return False, "Contract is not in an active state"
        
        # Check milestone count limit
        if len(contract.milestones) >= self.max_milestones:
            return False, f"Maximum {self.max_milestones} milestones reached"
        
        # Validate amount
        if amount < self.min_milestone_amount:
            return False, f"Milestone amount must be at least {self.min_milestone_amount}"
        
        # Add milestone
        milestone = {
            'milestone_id': milestone_id,
            'description': description,
            'amount': amount,
            'completed': False,
            'completed_at': None,
            'verified': False
        }
        
        contract.milestones.append(milestone)
        return True, "Milestone added successfully"
    
    async def report_agent_failure(self, contract_id: str, agent_address: str, 
                                 reason: str) -> Tuple[bool, str]:
        """Report agent failure for a contract"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.agent_address != agent_address:
            return False, "Agent address mismatch"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED]:
            return False, "Contract is not in an active state"
        
        # Record failure in dispute evidence
        failure_evidence = {
            'type': 'agent_failure',
            'agent_address': agent_address,
            'reason': reason,
            'timestamp': time.time()
        }
        
        contract.dispute_evidence.append(failure_evidence)
        
        # Move to disputed state if not already
        if contract.state != EscrowState.DISPUTED:
            contract.state = EscrowState.DISPUTED
            contract.dispute_reason = DisputeReason.INCOMPLETE_WORK
            self.disputed_contracts.add(contract_id)
            self.active_contracts.discard(contract_id)
        
        return True, "Agent failure reported successfully"
    
    async def fail_job(self, contract_id: str, reason: str = "") -> Tuple[bool, str]:
        """Mark a job as failed and initiate refund"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED, EscrowState.DISPUTED]:
            return False, "Contract is not in a failable state"
        
        # Mark as failed (refunded)
        contract.state = EscrowState.REFUNDED
        contract.dispute_reason = DisputeReason.TECHNICAL_ISSUES
        
        # Remove from active contracts
        self.active_contracts.discard(contract_id)
        self.disputed_contracts.discard(contract_id)
        
        # Calculate refund amount (total minus any completed milestones)
        completed_amount = Decimal('0')
        for milestone in contract.milestones:
            if milestone.get('completed', False):
                completed_amount += milestone.get('amount', Decimal('0'))
        
        refund_amount = contract.amount - completed_amount - contract.released_amount
        contract.refunded_amount = refund_amount
        
        return True, f"Job failed, refund amount: {refund_amount}"
    
    async def reassign_job(self, contract_id: str, new_agent_address: str) -> Tuple[bool, str]:
        """Reassign a job to a new agent"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        if contract.state not in [EscrowState.FUNDED, EscrowState.JOB_STARTED, EscrowState.DISPUTED]:
            return False, "Contract is not in a reassignable state"
        
        # Update agent address
        old_agent = contract.agent_address
        contract.agent_address = new_agent_address
        
        # Reset milestone progress
        for milestone in contract.milestones:
            milestone['completed'] = False
            milestone['completed_at'] = None
            milestone['verified'] = False
        
        contract.current_milestone = 0
        
        # Move back to active if was disputed
        if contract.state == EscrowState.DISPUTED:
            contract.state = EscrowState.JOB_STARTED
            self.disputed_contracts.discard(contract_id)
            self.active_contracts.add(contract_id)
        
        return True, f"Job reassigned from {old_agent} to {new_agent_address}"
    
    async def process_refund(self, contract_id: str) -> Tuple[bool, Decimal]:
        """Process refund for a contract"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, Decimal('0')
        
        refund_amount = contract.amount - contract.released_amount
        contract.refunded_amount = refund_amount
        contract.state = EscrowState.REFUNDED
        
        self.active_contracts.discard(contract_id)
        self.disputed_contracts.discard(contract_id)
        
        return True, refund_amount
    
    async def process_partial_payment(self, contract_id: str) -> Tuple[Decimal, Decimal]:
        """Process partial payment based on completed milestones"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return Decimal('0'), Decimal('0')
        
        completed_amount = Decimal('0')
        for milestone in contract.milestones:
            if milestone.get('completed', False):
                completed_amount += milestone.get('amount', Decimal('0'))
        
        # Apply fee (2.5%)
        fee = completed_amount * Decimal('0.025')
        agent_payment = completed_amount - fee
        client_refund = contract.amount - completed_amount
        
        contract.released_amount += agent_payment
        contract.refunded_amount = client_refund
        
        return agent_payment, client_refund

# Global escrow manager
escrow_manager: Optional[EscrowManager] = None

def get_escrow_manager() -> Optional[EscrowManager]:
    """Get global escrow manager"""
    return escrow_manager

def create_escrow_manager() -> EscrowManager:
    """Create and set global escrow manager"""
    global escrow_manager
    escrow_manager = EscrowManager()
    return escrow_manager
