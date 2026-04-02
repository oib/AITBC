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
