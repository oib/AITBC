"""
Distributed Consensus Implementation for AITBC Agent Coordinator
Implements various consensus algorithms for distributed decision making
"""

import asyncio
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json
import uuid
import hashlib
import statistics

from aitbc import get_logger

logger = get_logger(__name__)

@dataclass
class ConsensusProposal:
    """Represents a consensus proposal"""
    proposal_id: str
    proposer_id: str
    proposal_data: Dict[str, Any]
    timestamp: datetime
    deadline: datetime
    required_votes: int
    current_votes: Dict[str, bool] = field(default_factory=dict)
    status: str = 'pending'  # pending, approved, rejected, expired

@dataclass
class ConsensusNode:
    """Represents a node in the consensus network"""
    node_id: str
    endpoint: str
    last_seen: datetime
    reputation_score: float = 1.0
    voting_power: float = 1.0
    is_active: bool = True

class DistributedConsensus:
    """Distributed consensus implementation with multiple algorithms"""
    
    def __init__(self):
        self.nodes: Dict[str, ConsensusNode] = {}
        self.proposals: Dict[str, ConsensusProposal] = {}
        self.consensus_history: List[Dict[str, Any]] = []
        self.current_algorithm = 'majority_vote'
        self.voting_timeout = timedelta(minutes=5)
        self.min_participation = 0.5  # Minimum 50% participation
        
    async def register_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new node in the consensus network"""
        try:
            node_id = node_data.get('node_id', str(uuid.uuid4()))
            endpoint = node_data.get('endpoint', '')
            
            node = ConsensusNode(
                node_id=node_id,
                endpoint=endpoint,
                last_seen=datetime.now(datetime.UTC),
                reputation_score=node_data.get('reputation_score', 1.0),
                voting_power=node_data.get('voting_power', 1.0),
                is_active=True
            )
            
            self.nodes[node_id] = node
            
            return {
                'status': 'success',
                'node_id': node_id,
                'registered_at': datetime.now(datetime.UTC).isoformat(),
                'total_nodes': len(self.nodes)
            }
            
        except Exception as e:
            logger.error(f"Error registering node: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def create_proposal(self, proposal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new consensus proposal"""
        try:
            proposal_id = str(uuid.uuid4())
            proposer_id = proposal_data.get('proposer_id', '')
            
            # Calculate required votes based on algorithm
            if self.current_algorithm == 'majority_vote':
                required_votes = max(1, len(self.nodes) // 2 + 1)
            elif self.current_algorithm == 'supermajority':
                required_votes = max(1, int(len(self.nodes) * 0.67))
            elif self.current_algorithm == 'unanimous':
                required_votes = len(self.nodes)
            else:
                required_votes = max(1, len(self.nodes) // 2 + 1)
            
            proposal = ConsensusProposal(
                proposal_id=proposal_id,
                proposer_id=proposer_id,
                proposal_data=proposal_data.get('content', {}),
                timestamp=datetime.now(datetime.UTC),
                deadline=datetime.now(datetime.UTC) + self.voting_timeout,
                required_votes=required_votes
            )
            
            self.proposals[proposal_id] = proposal
            
            # Start voting process
            await self._initiate_voting(proposal)
            
            return {
                'status': 'success',
                'proposal_id': proposal_id,
                'required_votes': required_votes,
                'deadline': proposal.deadline.isoformat(),
                'algorithm': self.current_algorithm
            }
            
        except Exception as e:
            logger.error(f"Error creating proposal: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _initiate_voting(self, proposal: ConsensusProposal):
        """Initiate voting for a proposal"""
        try:
            # Notify all active nodes
            active_nodes = [node for node in self.nodes.values() if node.is_active]
            
            for node in active_nodes:
                # In a real implementation, this would send messages to other nodes
                # For now, we'll simulate the voting process
                await self._simulate_node_vote(proposal, node.node_id)
            
            # Check if consensus is reached
            await self._check_consensus(proposal)
            
        except Exception as e:
            logger.error(f"Error initiating voting: {e}")
    
    async def _simulate_node_vote(self, proposal: ConsensusProposal, node_id: str):
        """Simulate a node's voting decision"""
        try:
            # Simple voting logic based on proposal content and node characteristics
            node = self.nodes.get(node_id)
            if not node or not node.is_active:
                return
            
            # Simulate voting decision (in real implementation, this would be based on actual node logic)
            import random
            
            # Factors influencing vote
            vote_probability = 0.5  # Base probability
            
            # Adjust based on node reputation
            vote_probability += node.reputation_score * 0.2
            
            # Adjust based on proposal content (simplified)
            if proposal.proposal_data.get('priority') == 'high':
                vote_probability += 0.1
            
            # Add some randomness
            vote_probability += random.uniform(-0.2, 0.2)
            
            # Make decision
            vote = random.random() < vote_probability
            
            # Record vote
            await self.cast_vote(proposal.proposal_id, node_id, vote)
            
        except Exception as e:
            logger.error(f"Error simulating node vote: {e}")
    
    async def cast_vote(self, proposal_id: str, node_id: str, vote: bool) -> Dict[str, Any]:
        """Cast a vote for a proposal"""
        try:
            if proposal_id not in self.proposals:
                return {'status': 'error', 'message': 'Proposal not found'}
            
            proposal = self.proposals[proposal_id]
            
            if proposal.status != 'pending':
                return {'status': 'error', 'message': f'Proposal is {proposal.status}'}
            
            if node_id not in self.nodes:
                return {'status': 'error', 'message': 'Node not registered'}
            
            # Record vote
            proposal.current_votes[node_id] = vote
            self.nodes[node_id].last_seen = datetime.now(datetime.UTC)
            
            # Check if consensus is reached
            await self._check_consensus(proposal)
            
            return {
                'status': 'success',
                'proposal_id': proposal_id,
                'node_id': node_id,
                'vote': vote,
                'votes_count': len(proposal.current_votes),
                'required_votes': proposal.required_votes
            }
            
        except Exception as e:
            logger.error(f"Error casting vote: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _check_consensus(self, proposal: ConsensusProposal):
        """Check if consensus is reached for a proposal"""
        try:
            if proposal.status != 'pending':
                return
            
            # Count votes
            yes_votes = sum(1 for vote in proposal.current_votes.values() if vote)
            no_votes = len(proposal.current_votes) - yes_votes
            total_votes = len(proposal.current_votes)
            
            # Check if deadline passed
            if datetime.now(datetime.UTC) > proposal.deadline:
                proposal.status = 'expired'
                await self._finalize_proposal(proposal, False, 'Deadline expired')
                return
            
            # Check minimum participation
            active_nodes = sum(1 for node in self.nodes.values() if node.is_active)
            if total_votes < active_nodes * self.min_participation:
                return  # Not enough participation yet
            
            # Check consensus based on algorithm
            if self.current_algorithm == 'majority_vote':
                if yes_votes >= proposal.required_votes:
                    proposal.status = 'approved'
                    await self._finalize_proposal(proposal, True, f'Majority reached: {yes_votes}/{total_votes}')
                elif no_votes >= proposal.required_votes:
                    proposal.status = 'rejected'
                    await self._finalize_proposal(proposal, False, f'Majority against: {no_votes}/{total_votes}')
            
            elif self.current_algorithm == 'supermajority':
                if yes_votes >= proposal.required_votes:
                    proposal.status = 'approved'
                    await self._finalize_proposal(proposal, True, f'Supermajority reached: {yes_votes}/{total_votes}')
                elif no_votes >= proposal.required_votes:
                    proposal.status = 'rejected'
                    await self._finalize_proposal(proposal, False, f'Supermajority against: {no_votes}/{total_votes}')
            
            elif self.current_algorithm == 'unanimous':
                if total_votes == len(self.nodes) and yes_votes == total_votes:
                    proposal.status = 'approved'
                    await self._finalize_proposal(proposal, True, 'Unanimous approval')
                elif no_votes > 0:
                    proposal.status = 'rejected'
                    await self._finalize_proposal(proposal, False, f'Not unanimous: {yes_votes}/{total_votes}')
            
        except Exception as e:
            logger.error(f"Error checking consensus: {e}")
    
    async def _finalize_proposal(self, proposal: ConsensusProposal, approved: bool, reason: str):
        """Finalize a proposal decision"""
        try:
            # Record in history
            history_record = {
                'proposal_id': proposal.proposal_id,
                'proposer_id': proposal.proposer_id,
                'proposal_data': proposal.proposal_data,
                'approved': approved,
                'reason': reason,
                'votes': dict(proposal.current_votes),
                'required_votes': proposal.required_votes,
                'finalized_at': datetime.now(datetime.UTC).isoformat(),
                'algorithm': self.current_algorithm
            }
            
            self.consensus_history.append(history_record)
            
            # Clean up old proposals
            await self._cleanup_old_proposals()
            
            logger.info(f"Proposal {proposal.proposal_id} {'approved' if approved else 'rejected'}: {reason}")
            
        except Exception as e:
            logger.error(f"Error finalizing proposal: {e}")
    
    async def _cleanup_old_proposals(self):
        """Clean up old and expired proposals"""
        try:
            current_time = datetime.now(datetime.UTC)
            expired_proposals = [
                pid for pid, proposal in self.proposals.items()
                if proposal.deadline < current_time or proposal.status in ['approved', 'rejected', 'expired']
            ]
            
            for pid in expired_proposals:
                del self.proposals[pid]
            
        except Exception as e:
            logger.error(f"Error cleaning up proposals: {e}")
    
    async def get_proposal_status(self, proposal_id: str) -> Dict[str, Any]:
        """Get the status of a proposal"""
        try:
            if proposal_id not in self.proposals:
                return {'status': 'error', 'message': 'Proposal not found'}
            
            proposal = self.proposals[proposal_id]
            
            yes_votes = sum(1 for vote in proposal.current_votes.values() if vote)
            no_votes = len(proposal.current_votes) - yes_votes
            
            return {
                'status': 'success',
                'proposal_id': proposal_id,
                'status': proposal.status,
                'proposer_id': proposal.proposer_id,
                'created_at': proposal.timestamp.isoformat(),
                'deadline': proposal.deadline.isoformat(),
                'required_votes': proposal.required_votes,
                'current_votes': {
                    'yes': yes_votes,
                    'no': no_votes,
                    'total': len(proposal.current_votes),
                    'details': proposal.current_votes
                },
                'algorithm': self.current_algorithm
            }
            
        except Exception as e:
            logger.error(f"Error getting proposal status: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def set_consensus_algorithm(self, algorithm: str) -> Dict[str, Any]:
        """Set the consensus algorithm"""
        try:
            valid_algorithms = ['majority_vote', 'supermajority', 'unanimous']
            
            if algorithm not in valid_algorithms:
                return {'status': 'error', 'message': f'Invalid algorithm. Valid options: {valid_algorithms}'}
            
            self.current_algorithm = algorithm
            
            return {
                'status': 'success',
                'algorithm': algorithm,
                'changed_at': datetime.now(datetime.UTC).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error setting consensus algorithm: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_consensus_statistics(self) -> Dict[str, Any]:
        """Get comprehensive consensus statistics"""
        try:
            total_proposals = len(self.consensus_history)
            active_nodes = sum(1 for node in self.nodes.values() if node.is_active)
            
            if total_proposals == 0:
                return {
                    'status': 'success',
                    'total_proposals': 0,
                    'active_nodes': active_nodes,
                    'current_algorithm': self.current_algorithm,
                    'message': 'No proposals processed yet'
                }
            
            # Calculate statistics
            approved_proposals = sum(1 for record in self.consensus_history if record['approved'])
            rejected_proposals = total_proposals - approved_proposals
            
            # Algorithm performance
            algorithm_stats = defaultdict(lambda: {'approved': 0, 'total': 0})
            for record in self.consensus_history:
                algorithm = record['algorithm']
                algorithm_stats[algorithm]['total'] += 1
                if record['approved']:
                    algorithm_stats[algorithm]['approved'] += 1
            
            # Calculate success rates
            for algorithm, stats in algorithm_stats.items():
                stats['success_rate'] = stats['approved'] / stats['total'] if stats['total'] > 0 else 0
            
            # Node participation
            node_participation = {}
            for node_id, node in self.nodes.items():
                votes_cast = sum(1 for record in self.consensus_history if node_id in record['votes'])
                node_participation[node_id] = {
                    'votes_cast': votes_cast,
                    'participation_rate': votes_cast / total_proposals if total_proposals > 0 else 0,
                    'reputation_score': node.reputation_score
                }
            
            return {
                'status': 'success',
                'total_proposals': total_proposals,
                'approved_proposals': approved_proposals,
                'rejected_proposals': rejected_proposals,
                'success_rate': approved_proposals / total_proposals,
                'active_nodes': active_nodes,
                'total_nodes': len(self.nodes),
                'current_algorithm': self.current_algorithm,
                'algorithm_performance': dict(algorithm_stats),
                'node_participation': node_participation,
                'active_proposals': len(self.proposals),
                'last_updated': datetime.now(datetime.UTC).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting consensus statistics: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def update_node_status(self, node_id: str, is_active: bool) -> Dict[str, Any]:
        """Update a node's active status"""
        try:
            if node_id not in self.nodes:
                return {'status': 'error', 'message': 'Node not found'}
            
            self.nodes[node_id].is_active = is_active
            self.nodes[node_id].last_seen = datetime.now(datetime.UTC)
            
            return {
                'status': 'success',
                'node_id': node_id,
                'is_active': is_active,
                'updated_at': datetime.now(datetime.UTC).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error updating node status: {e}")
            return {'status': 'error', 'message': str(e)}

# Global consensus instance
distributed_consensus = DistributedConsensus()
