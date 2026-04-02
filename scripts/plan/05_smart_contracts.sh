#!/bin/bash

# Phase 5: Smart Contract Infrastructure Setup Script
# Implements escrow system, dispute resolution, and contract management

set -e

echo "=== PHASE 5: SMART CONTRACT INFRASTRUCTURE SETUP ==="

# Configuration
CONTRACTS_DIR="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts"
CONTRACTS_TESTS_DIR="/opt/aitbc/apps/blockchain-node/tests/contracts"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Function to backup existing contracts
backup_contracts() {
    log_info "Backing up existing contracts..."
    if [ -d "$CONTRACTS_DIR" ]; then
        cp -r "$CONTRACTS_DIR" "${CONTRACTS_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backup completed"
    fi
}

# Function to create escrow system
create_escrow_system() {
    log_info "Creating escrow system implementation..."
    
    cat > "$CONTRACTS_DIR/escrow.py" << 'EOF'
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
        
        if contract.state not in [EscrowState.JOB_STARTED, EscrowState.JOB_COMPLETED]:
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
        
        # Check if all milestones are completed
        all_completed = all(ms['completed'] for ms in contract.milestones)
        if all_completed:
            contract.state = EscrowState.JOB_COMPLETED
        
        log_info(f"Milestone {milestone_id} completed for contract: {contract_id}")
        return True, "Milestone completed successfully"
    
    async def verify_milestone(self, contract_id: str, milestone_id: str, 
                             verified: bool, feedback: str = "") -> Tuple[bool, str]:
        """Verify milestone completion"""
        contract = self.escrow_contracts.get(contract_id)
        if not contract:
            return False, "Contract not found"
        
        # Find milestone
        milestone = None
        for ms in contract.milestones:
            if ms['milestone_id'] == milestone_id:
                milestone = ms
                break
        
        if not milestone:
            return False, "Milestone not found"
        
        if not milestone['completed']:
            return False, "Milestone not completed yet"
        
        # Set verification status
        milestone['verified'] = verified
        milestone['verification_feedback'] = feedback
        
        if verified:
            # Release milestone payment
            await self._release_milestone_payment(contract_id, milestone_id)
        else:
            # Create dispute if verification fails
            await self._create_dispute(contract_id, DisputeReason.QUALITY_ISSUES, 
                                    f"Milestone {milestone_id} verification failed: {feedback}")
        
        log_info(f"Milestone {milestone_id} verification: {verified} for contract: {contract_id}")
        return True, "Milestone verification processed"
    
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
        
        log_info(f"Contract expired: {contract_id}")
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
            'total_fees': float(total_fees),
            'average_contract_value': float(total_amount / total_contracts) if total_contracts > 0 else 0
        }

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
EOF

    log_info "Escrow system created"
}

# Function to create dispute resolution mechanism
create_dispute_resolution() {
    log_info "Creating dispute resolution mechanism..."
    
    cat > "$CONTRACTS/disputes.py" << 'EOF'
"""
Dispute Resolution System
Handles automated and manual dispute resolution for escrow contracts
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class ResolutionType(Enum):
    AUTOMATED = "automated"
    MEDIATED = "mediated"
    ARBITRATION = "arbitration"
    COMMUNITY_VOTE = "community_vote"

class DisputeStatus(Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MEDIATING = "mediating"
    VOTING = "voting"
    RESOLVED = "resolved"
    ESCALATED = "escalated"

class EvidenceType(Enum):
    SCREENSHOT = "screenshot"
    LOG_FILE = "log_file"
    COMMUNICATION = "communication"
    METRICS = "metrics"
    TESTIMONY = "testimony"
    TECHNICAL_REPORT = "technical_report"

@dataclass
class DisputeCase:
    dispute_id: str
    contract_id: str
    client_address: str
    agent_address: str
    reason: str
    description: str
    evidence: List[Dict]
    status: DisputeStatus
    resolution_type: ResolutionType
    created_at: float
    updated_at: float
    deadline: float
    arbitrators: List[str]
    votes: Dict[str, int]
    resolution: Optional[Dict]
    automated_score: float

@dataclass
class Arbitrator:
    arbitrator_id: str
    address: str
    reputation_score: float
    total_cases: int
    success_rate: float
    specialization: List[str]
    availability: bool
    fee_rate: Decimal

class DisputeResolver:
    """Manages dispute resolution processes"""
    
    def __init__(self):
        self.dispute_cases: Dict[str, DisputeCase] = {}
        self.arbitrators: Dict[str, Arbitrator] = {}
        self.resolution_rules = self._initialize_resolution_rules()
        
        # Resolution parameters
        self.automated_resolution_threshold = 0.8  # Confidence score for automated resolution
        self.mediation_timeout = 86400 * 3  # 3 days
        self.arbitration_timeout = 86400 * 7  # 7 days
        self.voting_timeout = 86400 * 2  # 2 days
        self.min_arbitrators = 3
        self.max_arbitrators = 5
        self.community_vote_threshold = 0.6  # 60% agreement required
        
        # Initialize arbitrators
        self._initialize_arbitrators()
    
    def _initialize_resolution_rules(self) -> Dict:
        """Initialize resolution rules for different dispute types"""
        return {
            'quality_issues': {
                'automated_weight': 0.6,
                'evidence_required': ['metrics', 'screenshot'],
                'resolution_time': 86400  # 24 hours
            },
            'delivery_late': {
                'automated_weight': 0.8,
                'evidence_required': ['communication', 'log_file'],
                'resolution_time': 43200  # 12 hours
            },
            'incomplete_work': {
                'automated_weight': 0.5,
                'evidence_required': ['metrics', 'testimony'],
                'resolution_time': 86400  # 24 hours
            },
            'technical_issues': {
                'automated_weight': 0.7,
                'evidence_required': ['technical_report', 'log_file'],
                'resolution_time': 43200  # 12 hours
            },
            'payment_dispute': {
                'automated_weight': 0.4,
                'evidence_required': ['communication', 'testimony'],
                'resolution_time': 86400  # 24 hours
            },
            'other': {
                'automated_weight': 0.3,
                'evidence_required': ['testimony'],
                'resolution_time': 172800  # 48 hours
            }
        }
    
    def _initialize_arbitrators(self):
        """Initialize default arbitrators"""
        default_arbitrators = [
            Arbitrator(
                arbitrator_id="arb_001",
                address="0xarbitrator0011111111111111111111111111111111111",
                reputation_score=0.9,
                total_cases=50,
                success_rate=0.85,
                specialization=["quality_issues", "technical_issues"],
                availability=True,
                fee_rate=Decimal('0.02')
            ),
            Arbitrator(
                arbitrator_id="arb_002",
                address="0xarbitrator0022222222222222222222222222222222222",
                reputation_score=0.85,
                total_cases=35,
                success_rate=0.82,
                specialization=["delivery_late", "payment_dispute"],
                availability=True,
                fee_rate=Decimal('0.025')
            ),
            Arbitrator(
                arbitrator_id="arb_003",
                address="0xarbitrator0033333333333333333333333333333333333",
                reputation_score=0.88,
                total_cases=42,
                success_rate=0.86,
                specialization=["incomplete_work", "other"],
                availability=True,
                fee_rate=Decimal('0.022')
            )
        ]
        
        for arbitrator in default_arbitrators:
            self.arbitrators[arbitrator.arbitrator_id] = arbitrator
    
    async def create_dispute_case(self, contract_id: str, client_address: str, agent_address: str,
                                reason: str, description: str, evidence: List[Dict]) -> Tuple[bool, str, Optional[str]]:
        """Create new dispute case"""
        try:
            # Validate inputs
            if not all([contract_id, client_address, agent_address, reason, description]):
                return False, "Missing required fields", None
            
            # Validate evidence
            if not evidence:
                return False, "At least one evidence item required", None
            
            # Generate dispute ID
            dispute_id = self._generate_dispute_id(contract_id)
            
            # Analyze evidence for automated resolution
            automated_score = await self._analyze_evidence_for_automation(reason, evidence)
            
            # Determine resolution type
            resolution_type = await self._determine_resolution_type(reason, evidence, automated_score)
            
            # Select arbitrators if needed
            arbitrators = []
            if resolution_type in [ResolutionType.MEDIATED, ResolutionType.ARBITRATION]:
                arbitrators = await self._select_arbitrators(reason, resolution_type)
            
            # Calculate deadline
            deadline = time.time() + self._get_resolution_timeout(resolution_type)
            
            # Create dispute case
            dispute_case = DisputeCase(
                dispute_id=dispute_id,
                contract_id=contract_id,
                client_address=client_address,
                agent_address=agent_address,
                reason=reason,
                description=description,
                evidence=evidence,
                status=DisputeStatus.OPEN,
                resolution_type=resolution_type,
                created_at=time.time(),
                updated_at=time.time(),
                deadline=deadline,
                arbitrators=arbitrators,
                votes={},
                resolution=None,
                automated_score=automated_score
            )
            
            self.dispute_cases[dispute_id] = dispute_case
            
            # Start resolution process
            asyncio.create_task(self._process_dispute(dispute_id))
            
            log_info(f"Dispute case created: {dispute_id} - {resolution_type.value}")
            return True, "Dispute case created successfully", dispute_id
            
        except Exception as e:
            return False, f"Failed to create dispute case: {str(e)}", None
    
    def _generate_dispute_id(self, contract_id: str) -> str:
        """Generate unique dispute ID"""
        import hashlib
        content = f"{contract_id}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]
    
    async def _analyze_evidence_for_automation(self, reason: str, evidence: List[Dict]) -> float:
        """Analyze evidence to determine automation feasibility"""
        score = 0.0
        
        # Check evidence types
        evidence_types = set()
        for ev in evidence:
            evidence_types.add(ev.get('type', 'unknown'))
        
        # Base score from evidence types
        if 'metrics' in evidence_types:
            score += 0.3
        if 'screenshot' in evidence_types:
            score += 0.2
        if 'log_file' in evidence_types:
            score += 0.2
        if 'technical_report' in evidence_types:
            score += 0.3
        
        # Adjust based on reason
        rule = self.resolution_rules.get(reason, {})
        automated_weight = rule.get('automated_weight', 0.5)
        score *= automated_weight
        
        # Check evidence quality
        for ev in evidence:
            if ev.get('verified', False):
                score += 0.1
            if ev.get('timestamp'):
                # Recent evidence gets higher score
                age = time.time() - ev['timestamp']
                if age < 86400:  # Less than 1 day
                    score += 0.05
        
        return min(1.0, score)
    
    async def _determine_resolution_type(self, reason: str, evidence: List[Dict], 
                                        automated_score: float) -> ResolutionType:
        """Determine the best resolution type"""
        # High automation score -> automated resolution
        if automated_score >= self.automated_resolution_threshold:
            return ResolutionType.AUTOMATED
        
        # Medium automation score -> mediation
        elif automated_score >= 0.5:
            return ResolutionType.MEDIATED
        
        # Low automation score -> arbitration
        elif automated_score >= 0.3:
            return ResolutionType.ARBITRATION
        
        # Very low automation score -> community vote
        else:
            return ResolutionType.COMMUNITY_VOTE
    
    async def _select_arbitrators(self, reason: str, resolution_type: ResolutionType) -> List[str]:
        """Select arbitrators for the dispute"""
        available_arbitrators = [
            arb for arb in self.arbitrators.values()
            if arb.availability and reason in arb.specialization
        ]
        
        if not available_arbitrators:
            # Fall back to any available arbitrators
            available_arbitrators = [
                arb for arb in self.arbitrators.values()
                if arb.availability
            ]
        
        # Sort by reputation and success rate
        available_arbitrators.sort(
            key=lambda x: (x.reputation_score * x.success_rate),
            reverse=True
        )
        
        # Select appropriate number
        count = self.min_arbitrators if resolution_type == ResolutionType.MEDIATED else self.max_arbitrators
        selected = available_arbitrators[:count]
        
        return [arb.arbitrator_id for arb in selected]
    
    def _get_resolution_timeout(self, resolution_type: ResolutionType) -> int:
        """Get resolution timeout based on type"""
        timeouts = {
            ResolutionType.AUTOMATED: 86400,      # 24 hours
            ResolutionType.MEDIATED: self.mediation_timeout,
            ResolutionType.ARBITRATION: self.arbitration_timeout,
            ResolutionType.COMMUNITY_VOTE: self.voting_timeout
        }
        return timeouts.get(resolution_type, 86400)
    
    async def _process_dispute(self, dispute_id: str):
        """Process dispute resolution"""
        dispute_case = self.dispute_cases.get(dispute_id)
        if not dispute_case:
            return
        
        try:
            if dispute_case.resolution_type == ResolutionType.AUTOMATED:
                await self._automated_resolution(dispute_id)
            elif dispute_case.resolution_type == ResolutionType.MEDIATED:
                await self._mediated_resolution(dispute_id)
            elif dispute_case.resolution_type == ResolutionType.ARBITRATION:
                await self._arbitration_resolution(dispute_id)
            elif dispute_case.resolution_type == ResolutionType.COMMUNITY_VOTE:
                await self._community_vote_resolution(dispute_id)
                
        except Exception as e:
            log_error(f"Error processing dispute {dispute_id}: {e}")
            # Escalate to arbitration on error
            await self._escalate_dispute(dispute_id)
    
    async def _automated_resolution(self, dispute_id: str):
        """Handle automated dispute resolution"""
        dispute_case = self.dispute_cases[dispute_id]
        dispute_case.status = DisputeStatus.INVESTIGATING
        
        # Analyze evidence and make decision
        decision = await self._make_automated_decision(dispute_case)
        
        # Apply resolution
        await self._apply_resolution(dispute_id, decision)
    
    async def _make_automated_decision(self, dispute_case: DisputeCase) -> Dict:
        """Make automated decision based on evidence"""
        # Simplified decision logic
        client_score = 0.0
        agent_score = 0.0
        
        for evidence in dispute_case.evidence:
            ev_type = evidence.get('type', 'unknown')
            submitter = evidence.get('submitter', 'unknown')
            
            if submitter == 'client':
                if ev_type == 'metrics' and evidence.get('quality_score', 0) < 0.7:
                    client_score += 0.3
                elif ev_type == 'screenshot':
                    client_score += 0.2
                elif ev_type == 'communication':
                    client_score += 0.1
                    
            elif submitter == 'agent':
                if ev_type == 'metrics' and evidence.get('quality_score', 0) >= 0.8:
                    agent_score += 0.3
                elif ev_type == 'log_file' and evidence.get('completion_rate', 0) >= 0.9:
                    agent_score += 0.2
                elif ev_type == 'technical_report':
                    agent_score += 0.2
        
        # Make decision
        if agent_score > client_score + 0.1:
            return {
                'winner': 'agent',
                'client_refund': 0.1,  # 10% refund to client
                'agent_payment': 0.9,   # 90% to agent
                'reasoning': 'Evidence supports agent completion'
            }
        elif client_score > agent_score + 0.1:
            return {
                'winner': 'client',
                'client_refund': 0.9,   # 90% refund to client
                'agent_payment': 0.1,   # 10% to agent
                'reasoning': 'Evidence supports client claim'
            }
        else:
            # Split decision
            return {
                'winner': 'split',
                'client_refund': 0.5,   # 50% refund to client
                'agent_payment': 0.5,   # 50% to agent
                'reasoning': 'Evidence is inconclusive, split payment'
            }
    
    async def _mediated_resolution(self, dispute_id: str):
        """Handle mediated dispute resolution"""
        dispute_case = self.dispute_cases[dispute_id]
        dispute_case.status = DisputeStatus.MEDIATING
        
        # In real implementation, this would involve human mediators
        # For now, simulate mediation process
        
        await asyncio.sleep(3600)  # Simulate 1 hour mediation
        
        # Make mediation decision
        decision = await self._make_mediation_decision(dispute_case)
        await self._apply_resolution(dispute_id, decision)
    
    async def _make_mediation_decision(self, dispute_case: DisputeCase) -> Dict:
        """Make mediation decision"""
        # Mediation typically aims for compromise
        return {
            'winner': 'mediated',
            'client_refund': 0.3,   # 30% refund to client
            'agent_payment': 0.7,   # 70% to agent
            'reasoning': 'Mediation compromise based on evidence'
        }
    
    async def _arbitration_resolution(self, dispute_id: str):
        """Handle arbitration dispute resolution"""
        dispute_case = self.dispute_cases[dispute_id]
        dispute_case.status = DisputeStatus.INVESTIGATING
        
        # Collect arbitrator votes
        votes = {}
        for arbitrator_id in dispute_case.arbitrators:
            vote = await self._get_arbitrator_vote(arbitrator_id, dispute_case)
            votes[arbitrator_id] = vote
        
        dispute_case.votes = votes
        
        # Make decision based on votes
        decision = await self._make_arbitration_decision(votes)
        await self._apply_resolution(dispute_id, decision)
    
    async def _get_arbitrator_vote(self, arbitrator_id: str, dispute_case: DisputeCase) -> Dict:
        """Get vote from arbitrator"""
        arbitrator = self.arbitrators.get(arbitrator_id)
        if not arbitrator:
            return {'winner': 'client', 'split': 0.5}  # Default vote
        
        # In real implementation, arbitrator would analyze evidence and vote
        # For now, simulate based on arbitrator's specialization
        if dispute_case.reason in arbitrator.specialization:
            # Favor their specialization
            return {'winner': 'agent', 'split': 0.3}
        else:
            return {'winner': 'split', 'split': 0.5}
    
    async def _make_arbitration_decision(self, votes: Dict[str, Dict]) -> Dict:
        """Make decision based on arbitrator votes"""
        if not votes:
            return {'winner': 'split', 'client_refund': 0.5, 'agent_payment': 0.5}
        
        # Count votes
        client_votes = 0
        agent_votes = 0
        split_votes = 0
        
        for vote_data in votes.values():
            winner = vote_data.get('winner', 'split')
            if winner == 'client':
                client_votes += 1
            elif winner == 'agent':
                agent_votes += 1
            else:
                split_votes += 1
        
        # Make decision
        if agent_votes > client_votes and agent_votes > split_votes:
            return {'winner': 'agent', 'client_refund': 0.1, 'agent_payment': 0.9}
        elif client_votes > agent_votes and client_votes > split_votes:
            return {'winner': 'client', 'client_refund': 0.9, 'agent_payment': 0.1}
        else:
            return {'winner': 'split', 'client_refund': 0.5, 'agent_payment': 0.5}
    
    async def _community_vote_resolution(self, dispute_id: str):
        """Handle community vote dispute resolution"""
        dispute_case = self.dispute_cases[dispute_id]
        dispute_case.status = DisputeStatus.VOTING
        
        # In real implementation, this would involve community voting
        # For now, simulate community vote
        
        await asyncio.sleep(3600)  # Simulate 1 hour voting
        
        # Make community decision
        decision = await self._make_community_decision(dispute_case)
        await self._apply_resolution(dispute_id, decision)
    
    async def _make_community_decision(self, dispute_case: DisputeCase) -> Dict:
        """Make community-based decision"""
        # Community typically favors fairness
        return {
            'winner': 'community',
            'client_refund': 0.4,   # 40% refund to client
            'agent_payment': 0.6,   # 60% to agent
            'reasoning': 'Community vote based on fairness principles'
        }
    
    async def _apply_resolution(self, dispute_id: str, resolution: Dict):
        """Apply dispute resolution"""
        dispute_case = self.dispute_cases[dispute_id]
        dispute_case.resolution = resolution
        dispute_case.status = DisputeStatus.RESOLVED
        dispute_case.updated_at = time.time()
        
        # Update escrow contract
        from .escrow import get_escrow_manager
        escrow_manager = get_escrow_manager()
        if escrow_manager:
            await escrow_manager.resolve_dispute(dispute_case.contract_id, resolution)
        
        log_info(f"Dispute resolved: {dispute_id} - {resolution.get('winner', 'unknown')}")
    
    async def _escalate_dispute(self, dispute_id: str):
        """Escalate dispute to higher resolution type"""
        dispute_case = self.dispute_cases[dispute_id]
        
        # Escalate to arbitration
        if dispute_case.resolution_type != ResolutionType.ARBITRATION:
            dispute_case.resolution_type = ResolutionType.ARBITRATION
            dispute_case.arbitrators = await self._select_arbitrators(
                dispute_case.reason, ResolutionType.ARBITRATION
            )
            dispute_case.deadline = time.time() + self.arbitration_timeout
            
            # Restart resolution process
            asyncio.create_task(self._process_dispute(dispute_id))
        else:
            # Mark as escalated (manual intervention required)
            dispute_case.status = DisputeStatus.ESCALATED
    
    async def get_dispute_case(self, dispute_id: str) -> Optional[DisputeCase]:
        """Get dispute case information"""
        return self.dispute_cases.get(dispute_id)
    
    async def get_disputes_by_status(self, status: DisputeStatus) -> List[DisputeCase]:
        """Get disputes by status"""
        return [
            case for case in self.dispute_cases.values()
            if case.status == status
        ]
    
    async def get_dispute_statistics(self) -> Dict:
        """Get dispute resolution statistics"""
        total_disputes = len(self.dispute_cases)
        
        if total_disputes == 0:
            return {
                'total_disputes': 0,
                'resolution_types': {},
                'status_distribution': {},
                'average_resolution_time': 0,
                'success_rate': 0
            }
        
        # Resolution type distribution
        type_counts = {}
        for case in self.dispute_cases.values():
            res_type = case.resolution_type.value
            type_counts[res_type] = type_counts.get(res_type, 0) + 1
        
        # Status distribution
        status_counts = {}
        for case in self.dispute_cases.values():
            status = case.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Resolution statistics
        resolved_cases = [
            case for case in self.dispute_cases.values()
            if case.status == DisputeStatus.RESOLVED
        ]
        
        if resolved_cases:
            resolution_times = [
                case.updated_at - case.created_at
                for case in resolved_cases
            ]
            avg_resolution_time = sum(resolution_times) / len(resolution_times)
            
            # Success rate (cases resolved without escalation)
            non_escalated = len([
                case for case in resolved_cases
                if case.resolution_type != ResolutionType.COMMUNITY_VOTE
            ])
            success_rate = non_escalated / len(resolved_cases)
        else:
            avg_resolution_time = 0
            success_rate = 0
        
        return {
            'total_disputes': total_disputes,
            'resolution_types': type_counts,
            'status_distribution': status_counts,
            'average_resolution_time': avg_resolution_time,
            'success_rate': success_rate,
            'total_arbitrators': len(self.arbitrators),
            'active_arbitrators': len([a for a in self.arbitrators.values() if a.availability])
        }

# Global dispute resolver
dispute_resolver: Optional[DisputeResolver] = None

def get_dispute_resolver() -> Optional[DisputeResolver]:
    """Get global dispute resolver"""
    return dispute_resolver

def create_dispute_resolver() -> DisputeResolver:
    """Create and set global dispute resolver"""
    global dispute_resolver
    dispute_resolver = DisputeResolver()
    return dispute_resolver
EOF

    log_info "Dispute resolution mechanism created"
}

# Function to create contract upgrade system
create_contract_upgrade_system() {
    log_info "Creating contract upgrade system..."
    
    cat > "$CONTRACTS_DIR/upgrades.py" << 'EOF'
"""
Contract Upgrade System
Handles safe contract versioning and upgrade mechanisms
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class UpgradeStatus(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class UpgradeType(Enum):
    PARAMETER_CHANGE = "parameter_change"
    LOGIC_UPDATE = "logic_update"
    SECURITY_PATCH = "security_patch"
    FEATURE_ADDITION = "feature_addition"
    EMERGENCY_FIX = "emergency_fix"

@dataclass
class ContractVersion:
    version: str
    address: str
    deployed_at: float
    total_contracts: int
    total_value: Decimal
    is_active: bool
    metadata: Dict

@dataclass
class UpgradeProposal:
    proposal_id: str
    contract_type: str
    current_version: str
    new_version: str
    upgrade_type: UpgradeType
    description: str
    changes: Dict
    voting_deadline: float
    execution_deadline: float
    status: UpgradeStatus
    votes: Dict[str, bool]
    total_votes: int
    yes_votes: int
    no_votes: int
    required_approval: float
    created_at: float
    proposer: str
    executed_at: Optional[float]
    rollback_data: Optional[Dict]

class ContractUpgradeManager:
    """Manages contract upgrades and versioning"""
    
    def __init__(self):
        self.contract_versions: Dict[str, List[ContractVersion]] = {}  # contract_type -> versions
        self.active_versions: Dict[str, str] = {}  # contract_type -> active version
        self.upgrade_proposals: Dict[str, UpgradeProposal] = {}
        self.upgrade_history: List[Dict] = []
        
        # Upgrade parameters
        self.min_voting_period = 86400 * 3  # 3 days
        self.max_voting_period = 86400 * 7  # 7 days
        self.required_approval_rate = 0.6  # 60% approval required
        self.min_participation_rate = 0.3  # 30% minimum participation
        self.emergency_upgrade_threshold = 0.8  # 80% for emergency upgrades
        self.rollback_timeout = 86400 * 7  # 7 days to rollback
        
        # Governance
        self.governance_addresses: Set[str] = set()
        self.stake_weights: Dict[str, Decimal] = {}
        
        # Initialize governance
        self._initialize_governance()
    
    def _initialize_governance(self):
        """Initialize governance addresses"""
        # In real implementation, this would load from blockchain state
        # For now, use default governance addresses
        governance_addresses = [
            "0xgovernance1111111111111111111111111111111111111",
            "0xgovernance2222222222222222222222222222222222222",
            "0xgovernance3333333333333333333333333333333333333"
        ]
        
        for address in governance_addresses:
            self.governance_addresses.add(address)
            self.stake_weights[address] = Decimal('1000')  # Equal stake weights initially
    
    async def propose_upgrade(self, contract_type: str, current_version: str, new_version: str,
                            upgrade_type: UpgradeType, description: str, changes: Dict,
                            proposer: str, emergency: bool = False) -> Tuple[bool, str, Optional[str]]:
        """Propose contract upgrade"""
        try:
            # Validate inputs
            if not all([contract_type, current_version, new_version, description, changes, proposer]):
                return False, "Missing required fields", None
            
            # Check proposer authority
            if proposer not in self.governance_addresses:
                return False, "Proposer not authorized", None
            
            # Check current version
            active_version = self.active_versions.get(contract_type)
            if active_version != current_version:
                return False, f"Current version mismatch. Active: {active_version}, Proposed: {current_version}", None
            
            # Validate new version format
            if not self._validate_version_format(new_version):
                return False, "Invalid version format", None
            
            # Check for existing proposal
            for proposal in self.upgrade_proposals.values():
                if (proposal.contract_type == contract_type and
                    proposal.new_version == new_version and
                    proposal.status in [UpgradeStatus.PROPOSED, UpgradeStatus.APPROVED]):
                    return False, "Proposal for this version already exists", None
            
            # Generate proposal ID
            proposal_id = self._generate_proposal_id(contract_type, new_version)
            
            # Set voting deadlines
            current_time = time.time()
            voting_period = self.min_voting_period if not emergency else self.min_voting_period // 2
            voting_deadline = current_time + voting_period
            execution_deadline = voting_deadline + 86400  # 1 day after voting
            
            # Set required approval rate
            required_approval = self.emergency_upgrade_threshold if emergency else self.required_approval_rate
            
            # Create proposal
            proposal = UpgradeProposal(
                proposal_id=proposal_id,
                contract_type=contract_type,
                current_version=current_version,
                new_version=new_version,
                upgrade_type=upgrade_type,
                description=description,
                changes=changes,
                voting_deadline=voting_deadline,
                execution_deadline=execution_deadline,
                status=UpgradeStatus.PROPOSED,
                votes={},
                total_votes=0,
                yes_votes=0,
                no_votes=0,
                required_approval=required_approval,
                created_at=current_time,
                proposer=proposer,
                executed_at=None,
                rollback_data=None
            )
            
            self.upgrade_proposals[proposal_id] = proposal
            
            # Start voting process
            asyncio.create_task(self._manage_voting_process(proposal_id))
            
            log_info(f"Upgrade proposal created: {proposal_id} - {contract_type} {current_version} -> {new_version}")
            return True, "Upgrade proposal created successfully", proposal_id
            
        except Exception as e:
            return False, f"Failed to create proposal: {str(e)}", None
    
    def _validate_version_format(self, version: str) -> bool:
        """Validate semantic version format"""
        try:
            parts = version.split('.')
            if len(parts) != 3:
                return False
            
            major, minor, patch = parts
            int(major) and int(minor) and int(patch)
            return True
        except ValueError:
            return False
    
    def _generate_proposal_id(self, contract_type: str, new_version: str) -> str:
        """Generate unique proposal ID"""
        import hashlib
        content = f"{contract_type}:{new_version}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]
    
    async def _manage_voting_process(self, proposal_id: str):
        """Manage voting process for proposal"""
        proposal = self.upgrade_proposals.get(proposal_id)
        if not proposal:
            return
        
        try:
            # Wait for voting deadline
            await asyncio.sleep(proposal.voting_deadline - time.time())
            
            # Check voting results
            await self._finalize_voting(proposal_id)
            
        except Exception as e:
            log_error(f"Error in voting process for {proposal_id}: {e}")
            proposal.status = UpgradeStatus.FAILED
    
    async def _finalize_voting(self, proposal_id: str):
        """Finalize voting and determine outcome"""
        proposal = self.upgrade_proposals[proposal_id]
        
        # Calculate voting results
        total_stake = sum(self.stake_weights.get(voter, Decimal('0')) for voter in proposal.votes.keys())
        yes_stake = sum(self.stake_weights.get(voter, Decimal('0')) for voter, vote in proposal.votes.items() if vote)
        
        # Check minimum participation
        total_governance_stake = sum(self.stake_weights.values())
        participation_rate = float(total_stake / total_governance_stake) if total_governance_stake > 0 else 0
        
        if participation_rate < self.min_participation_rate:
            proposal.status = UpgradeStatus.REJECTED
            log_info(f"Proposal {proposal_id} rejected due to low participation: {participation_rate:.2%}")
            return
        
        # Check approval rate
        approval_rate = float(yes_stake / total_stake) if total_stake > 0 else 0
        
        if approval_rate >= proposal.required_approval:
            proposal.status = UpgradeStatus.APPROVED
            log_info(f"Proposal {proposal_id} approved with {approval_rate:.2%} approval")
            
            # Schedule execution
            asyncio.create_task(self._execute_upgrade(proposal_id))
        else:
            proposal.status = UpgradeStatus.REJECTED
            log_info(f"Proposal {proposal_id} rejected with {approval_rate:.2%} approval")
    
    async def vote_on_proposal(self, proposal_id: str, voter_address: str, vote: bool) -> Tuple[bool, str]:
        """Cast vote on upgrade proposal"""
        proposal = self.upgrade_proposals.get(proposal_id)
        if not proposal:
            return False, "Proposal not found"
        
        # Check voting authority
        if voter_address not in self.governance_addresses:
            return False, "Not authorized to vote"
        
        # Check voting period
        if time.time() > proposal.voting_deadline:
            return False, "Voting period has ended"
        
        # Check if already voted
        if voter_address in proposal.votes:
            return False, "Already voted"
        
        # Cast vote
        proposal.votes[voter_address] = vote
        proposal.total_votes += 1
        
        if vote:
            proposal.yes_votes += 1
        else:
            proposal.no_votes += 1
        
        log_info(f"Vote cast on proposal {proposal_id} by {voter_address}: {'YES' if vote else 'NO'}")
        return True, "Vote cast successfully"
    
    async def _execute_upgrade(self, proposal_id: str):
        """Execute approved upgrade"""
        proposal = self.upgrade_proposals[proposal_id]
        
        try:
            # Wait for execution deadline
            await asyncio.sleep(proposal.execution_deadline - time.time())
            
            # Check if still approved
            if proposal.status != UpgradeStatus.APPROVED:
                return
            
            # Prepare rollback data
            rollback_data = await self._prepare_rollback_data(proposal)
            
            # Execute upgrade
            success = await self._perform_upgrade(proposal)
            
            if success:
                proposal.status = UpgradeStatus.EXECUTED
                proposal.executed_at = time.time()
                proposal.rollback_data = rollback_data
                
                # Update active version
                self.active_versions[proposal.contract_type] = proposal.new_version
                
                # Record in history
                self.upgrade_history.append({
                    'proposal_id': proposal_id,
                    'contract_type': proposal.contract_type,
                    'from_version': proposal.current_version,
                    'to_version': proposal.new_version,
                    'executed_at': proposal.executed_at,
                    'upgrade_type': proposal.upgrade_type.value
                })
                
                log_info(f"Upgrade executed: {proposal_id} - {proposal.contract_type} {proposal.current_version} -> {proposal.new_version}")
                
                # Start rollback window
                asyncio.create_task(self._manage_rollback_window(proposal_id))
            else:
                proposal.status = UpgradeStatus.FAILED
                log_error(f"Upgrade execution failed: {proposal_id}")
                
        except Exception as e:
            proposal.status = UpgradeStatus.FAILED
            log_error(f"Error executing upgrade {proposal_id}: {e}")
    
    async def _prepare_rollback_data(self, proposal: UpgradeProposal) -> Dict:
        """Prepare data for potential rollback"""
        return {
            'previous_version': proposal.current_version,
            'contract_state': {},  # Would capture current contract state
            'migration_data': {},  # Would store migration data
            'timestamp': time.time()
        }
    
    async def _perform_upgrade(self, proposal: UpgradeProposal) -> bool:
        """Perform the actual upgrade"""
        try:
            # In real implementation, this would:
            # 1. Deploy new contract version
            # 2. Migrate state from old contract
            # 3. Update contract references
            # 4. Verify upgrade integrity
            
            # Simulate upgrade process
            await asyncio.sleep(10)  # Simulate upgrade time
            
            # Create new version record
            new_version = ContractVersion(
                version=proposal.new_version,
                address=f"0x{proposal.contract_type}_{proposal.new_version}",  # New address
                deployed_at=time.time(),
                total_contracts=0,
                total_value=Decimal('0'),
                is_active=True,
                metadata={
                    'upgrade_type': proposal.upgrade_type.value,
                    'proposal_id': proposal.proposal_id,
                    'changes': proposal.changes
                }
            )
            
            # Add to version history
            if proposal.contract_type not in self.contract_versions:
                self.contract_versions[proposal.contract_type] = []
            
            # Deactivate old version
            for version in self.contract_versions[proposal.contract_type]:
                if version.version == proposal.current_version:
                    version.is_active = False
                    break
            
            # Add new version
            self.contract_versions[proposal.contract_type].append(new_version)
            
            return True
            
        except Exception as e:
            log_error(f"Upgrade execution error: {e}")
            return False
    
    async def _manage_rollback_window(self, proposal_id: str):
        """Manage rollback window after upgrade"""
        proposal = self.upgrade_proposals[proposal_id]
        
        try:
            # Wait for rollback timeout
            await asyncio.sleep(self.rollback_timeout)
            
            # Check if rollback was requested
            if proposal.status == UpgradeStatus.EXECUTED:
                # No rollback requested, finalize upgrade
                await self._finalize_upgrade(proposal_id)
                
        except Exception as e:
            log_error(f"Error in rollback window for {proposal_id}: {e}")
    
    async def _finalize_upgrade(self, proposal_id: str):
        """Finalize upgrade after rollback window"""
        proposal = self.upgrade_proposals[proposal_id]
        
        # Clear rollback data to save space
        proposal.rollback_data = None
        
        log_info(f"Upgrade finalized: {proposal_id}")
    
    async def rollback_upgrade(self, proposal_id: str, reason: str) -> Tuple[bool, str]:
        """Rollback upgrade to previous version"""
        proposal = self.upgrade_proposals.get(proposal_id)
        if not proposal:
            return False, "Proposal not found"
        
        if proposal.status != UpgradeStatus.EXECUTED:
            return False, "Can only rollback executed upgrades"
        
        if not proposal.rollback_data:
            return False, "Rollback data not available"
        
        # Check rollback window
        if time.time() - proposal.executed_at > self.rollback_timeout:
            return False, "Rollback window has expired"
        
        try:
            # Perform rollback
            success = await self._perform_rollback(proposal)
            
            if success:
                proposal.status = UpgradeStatus.ROLLED_BACK
                
                # Restore previous version
                self.active_versions[proposal.contract_type] = proposal.current_version
                
                # Update version records
                for version in self.contract_versions[proposal.contract_type]:
                    if version.version == proposal.new_version:
                        version.is_active = False
                    elif version.version == proposal.current_version:
                        version.is_active = True
                
                log_info(f"Upgrade rolled back: {proposal_id} - Reason: {reason}")
                return True, "Rollback successful"
            else:
                return False, "Rollback execution failed"
                
        except Exception as e:
            log_error(f"Rollback error for {proposal_id}: {e}")
            return False, f"Rollback failed: {str(e)}"
    
    async def _perform_rollback(self, proposal: UpgradeProposal) -> bool:
        """Perform the actual rollback"""
        try:
            # In real implementation, this would:
            # 1. Restore previous contract state
            # 2. Update contract references back
            # 3. Verify rollback integrity
            
            # Simulate rollback process
            await asyncio.sleep(5)  # Simulate rollback time
            
            return True
            
        except Exception as e:
            log_error(f"Rollback execution error: {e}")
            return False
    
    async def get_proposal(self, proposal_id: str) -> Optional[UpgradeProposal]:
        """Get upgrade proposal"""
        return self.upgrade_proposals.get(proposal_id)
    
    async def get_proposals_by_status(self, status: UpgradeStatus) -> List[UpgradeProposal]:
        """Get proposals by status"""
        return [
            proposal for proposal in self.upgrade_proposals.values()
            if proposal.status == status
        ]
    
    async def get_contract_versions(self, contract_type: str) -> List[ContractVersion]:
        """Get all versions for a contract type"""
        return self.contract_versions.get(contract_type, [])
    
    async def get_active_version(self, contract_type: str) -> Optional[str]:
        """Get active version for contract type"""
        return self.active_versions.get(contract_type)
    
    async def get_upgrade_statistics(self) -> Dict:
        """Get upgrade system statistics"""
        total_proposals = len(self.upgrade_proposals)
        
        if total_proposals == 0:
            return {
                'total_proposals': 0,
                'status_distribution': {},
                'upgrade_types': {},
                'average_execution_time': 0,
                'success_rate': 0
            }
        
        # Status distribution
        status_counts = {}
        for proposal in self.upgrade_proposals.values():
            status = proposal.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Upgrade type distribution
        type_counts = {}
        for proposal in self.upgrade_proposals.values():
            up_type = proposal.upgrade_type.value
            type_counts[up_type] = type_counts.get(up_type, 0) + 1
        
        # Execution statistics
        executed_proposals = [
            proposal for proposal in self.upgrade_proposals.values()
            if proposal.status == UpgradeStatus.EXECUTED
        ]
        
        if executed_proposals:
            execution_times = [
                proposal.executed_at - proposal.created_at
                for proposal in executed_proposals
                if proposal.executed_at
            ]
            avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        else:
            avg_execution_time = 0
        
        # Success rate
        successful_upgrades = len(executed_proposals)
        success_rate = successful_upgrades / total_proposals if total_proposals > 0 else 0
        
        return {
            'total_proposals': total_proposals,
            'status_distribution': status_counts,
            'upgrade_types': type_counts,
            'average_execution_time': avg_execution_time,
            'success_rate': success_rate,
            'total_governance_addresses': len(self.governance_addresses),
            'contract_types': len(self.contract_versions)
        }

# Global upgrade manager
upgrade_manager: Optional[ContractUpgradeManager] = None

def get_upgrade_manager() -> Optional[ContractUpgradeManager]:
    """Get global upgrade manager"""
    return upgrade_manager

def create_upgrade_manager() -> ContractUpgradeManager:
    """Create and set global upgrade manager"""
    global upgrade_manager
    upgrade_manager = ContractUpgradeManager()
    return upgrade_manager
EOF

    log_info "Contract upgrade system created"
}

# Function to create gas optimization
create_gas_optimization() {
    log_info "Creating gas optimization system..."
    
    cat > "$CONTRACTS_DIR/optimization.py" << 'EOF'
"""
Gas Optimization System
Optimizes gas usage and fee efficiency for smart contracts
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class OptimizationStrategy(Enum):
    BATCH_OPERATIONS = "batch_operations"
    LAZY_EVALUATION = "lazy_evaluation"
    STATE_COMPRESSION = "state_compression"
    EVENT_FILTERING = "event_filtering"
    STORAGE_OPTIMIZATION = "storage_optimization"

@dataclass
class GasMetric:
    contract_address: str
    function_name: str
    gas_used: int
    gas_limit: int
    execution_time: float
    timestamp: float
    optimization_applied: Optional[str]

@dataclass
class OptimizationResult:
    strategy: OptimizationStrategy
    original_gas: int
    optimized_gas: int
    gas_savings: int
    savings_percentage: float
    implementation_cost: Decimal
    net_benefit: Decimal

class GasOptimizer:
    """Optimizes gas usage for smart contracts"""
    
    def __init__(self):
        self.gas_metrics: List[GasMetric] = []
        self.optimization_results: List[OptimizationResult] = []
        self.optimization_strategies = self._initialize_strategies()
        
        # Optimization parameters
        self.min_optimization_threshold = 1000  # Minimum gas to consider optimization
        self.optimization_target_savings = 0.1  # 10% minimum savings
        self.max_optimization_cost = Decimal('0.01')  # Maximum cost per optimization
        self.metric_retention_period = 86400 * 7  # 7 days
        
        # Gas price tracking
        self.gas_price_history: List[Dict] = []
        self.current_gas_price = Decimal('0.001')
    
    def _initialize_strategies(self) -> Dict[OptimizationStrategy, Dict]:
        """Initialize optimization strategies"""
        return {
            OptimizationStrategy.BATCH_OPERATIONS: {
                'description': 'Batch multiple operations into single transaction',
                'potential_savings': 0.3,  # 30% potential savings
                'implementation_cost': Decimal('0.005'),
                'applicable_functions': ['transfer', 'approve', 'mint']
            },
            OptimizationStrategy.LAZY_EVALUATION: {
                'description': 'Defer expensive computations until needed',
                'potential_savings': 0.2,  # 20% potential savings
                'implementation_cost': Decimal('0.003'),
                'applicable_functions': ['calculate', 'validate', 'process']
            },
            OptimizationStrategy.STATE_COMPRESSION: {
                'description': 'Compress state data to reduce storage costs',
                'potential_savings': 0.4,  # 40% potential savings
                'implementation_cost': Decimal('0.008'),
                'applicable_functions': ['store', 'update', 'save']
            },
            OptimizationStrategy.EVENT_FILTERING: {
                'description': 'Filter events to reduce emission costs',
                'potential_savings': 0.15,  # 15% potential savings
                'implementation_cost': Decimal('0.002'),
                'applicable_functions': ['emit', 'log', 'notify']
            },
            OptimizationStrategy.STORAGE_OPTIMIZATION: {
                'description': 'Optimize storage patterns and data structures',
                'potential_savings': 0.25,  # 25% potential savings
                'implementation_cost': Decimal('0.006'),
                'applicable_functions': ['set', 'add', 'remove']
            }
        }
    
    async def record_gas_usage(self, contract_address: str, function_name: str,
                              gas_used: int, gas_limit: int, execution_time: float,
                              optimization_applied: Optional[str] = None):
        """Record gas usage metrics"""
        metric = GasMetric(
            contract_address=contract_address,
            function_name=function_name,
            gas_used=gas_used,
            gas_limit=gas_limit,
            execution_time=execution_time,
            timestamp=time.time(),
            optimization_applied=optimization_applied
        )
        
        self.gas_metrics.append(metric)
        
        # Limit history size
        if len(self.gas_metrics) > 10000:
            self.gas_metrics = self.gas_metrics[-5000]
        
        # Trigger optimization analysis if threshold met
        if gas_used >= self.min_optimization_threshold:
            asyncio.create_task(self._analyze_optimization_opportunity(metric))
    
    async def _analyze_optimization_opportunity(self, metric: GasMetric):
        """Analyze if optimization is beneficial"""
        # Get historical average for this function
        historical_metrics = [
            m for m in self.gas_metrics
            if m.function_name == metric.function_name and
            m.contract_address == metric.contract_address and
            not m.optimization_applied
        ]
        
        if len(historical_metrics) < 5:  # Need sufficient history
            return
        
        avg_gas = sum(m.gas_used for m in historical_metrics) / len(historical_metrics)
        
        # Test each optimization strategy
        for strategy, config in self.optimization_strategies.items():
            if self._is_strategy_applicable(strategy, metric.function_name):
                potential_savings = avg_gas * config['potential_savings']
                
                if potential_savings >= self.min_optimization_threshold:
                    # Calculate net benefit
                    gas_price = self.current_gas_price
                    gas_savings_value = potential_savings * gas_price
                    net_benefit = gas_savings_value - config['implementation_cost']
                    
                    if net_benefit > 0:
                        # Create optimization result
                        result = OptimizationResult(
                            strategy=strategy,
                            original_gas=int(avg_gas),
                            optimized_gas=int(avg_gas - potential_savings),
                            gas_savings=int(potential_savings),
                            savings_percentage=config['potential_savings'],
                            implementation_cost=config['implementation_cost'],
                            net_benefit=net_benefit
                        )
                        
                        self.optimization_results.append(result)
                        
                        # Keep only recent results
                        if len(self.optimization_results) > 1000:
                            self.optimization_results = self.optimization_results[-500]
                        
                        log_info(f"Optimization opportunity found: {strategy.value} for {metric.function_name} - Potential savings: {potential_savings} gas")
    
    def _is_strategy_applicable(self, strategy: OptimizationStrategy, function_name: str) -> bool:
        """Check if optimization strategy is applicable to function"""
        config = self.optimization_strategies.get(strategy, {})
        applicable_functions = config.get('applicable_functions', [])
        
        # Check if function name contains any applicable keywords
        for applicable in applicable_functions:
            if applicable.lower() in function_name.lower():
                return True
        
        return False
    
    async def apply_optimization(self, contract_address: str, function_name: str,
                               strategy: OptimizationStrategy) -> Tuple[bool, str]:
        """Apply optimization strategy to contract function"""
        try:
            # Validate strategy
            if strategy not in self.optimization_strategies:
                return False, "Unknown optimization strategy"
            
            # Check applicability
            if not self._is_strategy_applicable(strategy, function_name):
                return False, "Strategy not applicable to this function"
            
            # Get optimization result
            result = None
            for res in self.optimization_results:
                if (res.strategy == strategy and 
                    res.strategy in self.optimization_strategies):
                    result = res
                    break
            
            if not result:
                return False, "No optimization analysis available"
            
            # Check if net benefit is positive
            if result.net_benefit <= 0:
                return False, "Optimization not cost-effective"
            
            # Apply optimization (in real implementation, this would modify contract code)
            success = await self._implement_optimization(contract_address, function_name, strategy)
            
            if success:
                # Record optimization
                await self.record_gas_usage(
                    contract_address, function_name, result.optimized_gas,
                    result.optimized_gas, 0.0, strategy.value
                )
                
                log_info(f"Optimization applied: {strategy.value} to {function_name}")
                return True, f"Optimization applied successfully. Gas savings: {result.gas_savings}"
            else:
                return False, "Optimization implementation failed"
                
        except Exception as e:
            return False, f"Optimization error: {str(e)}"
    
    async def _implement_optimization(self, contract_address: str, function_name: str,
                                    strategy: OptimizationStrategy) -> bool:
        """Implement the optimization strategy"""
        try:
            # In real implementation, this would:
            # 1. Analyze contract bytecode
            # 2. Apply optimization patterns
            # 3. Generate optimized bytecode
            # 4. Deploy optimized version
            # 5. Verify functionality
            
            # Simulate implementation
            await asyncio.sleep(2)  # Simulate optimization time
            
            return True
            
        except Exception as e:
            log_error(f"Optimization implementation error: {e}")
            return False
    
    async def update_gas_price(self, new_price: Decimal):
        """Update current gas price"""
        self.current_gas_price = new_price
        
        # Record price history
        self.gas_price_history.append({
            'price': float(new_price),
            'timestamp': time.time()
        })
        
        # Limit history size
        if len(self.gas_price_history) > 1000:
            self.gas_price_history = self.gas_price_history[-500]
        
        # Re-evaluate optimization opportunities with new price
        asyncio.create_task(self._reevaluate_optimizations())
    
    async def _reevaluate_optimizations(self):
        """Re-evaluate optimization opportunities with new gas price"""
        # Clear old results and re-analyze
        self.optimization_results.clear()
        
        # Re-analyze recent metrics
        recent_metrics = [
            m for m in self.gas_metrics
            if time.time() - m.timestamp < 3600  # Last hour
        ]
        
        for metric in recent_metrics:
            if metric.gas_used >= self.min_optimization_threshold:
                await self._analyze_optimization_opportunity(metric)
    
    async def get_optimization_recommendations(self, contract_address: Optional[str] = None,
                                             limit: int = 10) -> List[Dict]:
        """Get optimization recommendations"""
        recommendations = []
        
        for result in self.optimization_results:
            if contract_address and result.strategy.value not in self.optimization_strategies:
                continue
            
            if result.net_benefit > 0:
                recommendations.append({
                    'strategy': result.strategy.value,
                    'function': 'contract_function',  # Would map to actual function
                    'original_gas': result.original_gas,
                    'optimized_gas': result.optimized_gas,
                    'gas_savings': result.gas_savings,
                    'savings_percentage': result.savings_percentage,
                    'net_benefit': float(result.net_benefit),
                    'implementation_cost': float(result.implementation_cost)
                })
        
        # Sort by net benefit
        recommendations.sort(key=lambda x: x['net_benefit'], reverse=True)
        
        return recommendations[:limit]
    
    async def get_gas_statistics(self) -> Dict:
        """Get gas usage statistics"""
        if not self.gas_metrics:
            return {
                'total_transactions': 0,
                'average_gas_used': 0,
                'total_gas_used': 0,
                'gas_efficiency': 0,
                'optimization_opportunities': 0
            }
        
        total_transactions = len(self.gas_metrics)
        total_gas_used = sum(m.gas_used for m in self.gas_metrics)
        average_gas_used = total_gas_used / total_transactions
        
        # Calculate efficiency (gas used vs gas limit)
        efficiency_scores = [
            m.gas_used / m.gas_limit for m in self.gas_metrics
            if m.gas_limit > 0
        ]
        avg_efficiency = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 0
        
        # Optimization opportunities
        optimization_count = len([
            result for result in self.optimization_results
            if result.net_benefit > 0
        ])
        
        return {
            'total_transactions': total_transactions,
            'average_gas_used': average_gas_used,
            'total_gas_used': total_gas_used,
            'gas_efficiency': avg_efficiency,
            'optimization_opportunities': optimization_count,
            'current_gas_price': float(self.current_gas_price),
            'total_optimizations_applied': len([
                m for m in self.gas_metrics
                if m.optimization_applied
            ])
        }

# Global gas optimizer
gas_optimizer: Optional[GasOptimizer] = None

def get_gas_optimizer() -> Optional[GasOptimizer]:
    """Get global gas optimizer"""
    return gas_optimizer

def create_gas_optimizer() -> GasOptimizer:
    """Create and set global gas optimizer"""
    global gas_optimizer
    gas_optimizer = GasOptimizer()
    return gas_optimizer
EOF

    log_info "Gas optimization system created"
}

# Function to create contract tests
create_contract_tests() {
    log_info "Creating smart contract test suite..."
    
    mkdir -p "$CONTRACTS_TESTS_DIR"
    
    cat > "$CONTRACTS_TESTS_DIR/test_escrow.py" << 'EOF'
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
EOF

    log_info "Smart contract test suite created"
}

# Function to setup test environment
setup_test_environment() {
    log_info "Setting up smart contract test environment..."
    
    # Create test configuration
    cat > "/opt/aitbc/config/smart_contracts_test.json" << 'EOF'
{
    "escrow": {
        "default_fee_rate": 0.025,
        "max_contract_duration": 2592000,
        "dispute_timeout": 604800,
        "min_dispute_evidence": 1,
        "max_dispute_evidence": 10,
        "min_milestone_amount": 0.01,
        "max_milestones": 10,
        "verification_timeout": 86400
    },
    "disputes": {
        "automated_resolution_threshold": 0.8,
        "mediation_timeout": 259200,
        "arbitration_timeout": 604800,
        "voting_timeout": 172800,
        "min_arbitrators": 3,
        "max_arbitrators": 5,
        "community_vote_threshold": 0.6
    },
    "upgrades": {
        "min_voting_period": 259200,
        "max_voting_period": 604800,
        "required_approval_rate": 0.6,
        "min_participation_rate": 0.3,
        "emergency_upgrade_threshold": 0.8,
        "rollback_timeout": 604800
    },
    "optimization": {
        "min_optimization_threshold": 1000,
        "optimization_target_savings": 0.1,
        "max_optimization_cost": 0.01,
        "metric_retention_period": 604800
    }
}
EOF

    log_info "Smart contract test configuration created"
}

# Function to run contract tests
run_contract_tests() {
    log_info "Running smart contract tests..."
    
    cd /opt/aitbc/apps/blockchain-node
    
    # Install test dependencies if needed
    if ! python -c "import pytest" 2>/dev/null; then
        log_info "Installing pytest..."
        pip install pytest pytest-asyncio
    fi
    
    # Run tests
    python -m pytest tests/contracts/ -v
    
    if [ $? -eq 0 ]; then
        log_info "All smart contract tests passed!"
    else
        log_error "Some smart contract tests failed!"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Phase 5: Smart Contract Infrastructure Setup"
    
    # Create necessary directories
    mkdir -p "$CONTRACTS_DIR"
    mkdir -p "$CONTRACTS_TESTS_DIR"
    
    # Execute setup steps
    backup_contracts
    create_escrow_system
    create_dispute_resolution
    create_contract_upgrade_system
    create_gas_optimization
    create_contract_tests
    setup_test_environment
    
    # Run tests
    if run_contract_tests; then
        log_info "Phase 5 smart contract infrastructure setup completed successfully!"
        log_info "Next steps:"
        log_info "1. Configure smart contract parameters"
        log_info "2. Initialize escrow services"
        log_info "3. Set up dispute resolution system"
        log_info "4. Configure contract upgrade mechanisms"
        log_info "5. Enable gas optimization features"
        log_info "6. 🎉 COMPLETE MESH NETWORK TRANSITION PLAN 🎉"
    else
        log_error "Phase 5 setup failed - check test output"
        return 1
    fi
}

# Execute main function
main "$@"
