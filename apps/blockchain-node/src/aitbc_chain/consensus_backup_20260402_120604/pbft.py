"""
Practical Byzantine Fault Tolerance (PBFT) Consensus Implementation
Provides Byzantine fault tolerance for up to 1/3 faulty validators
"""

import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from .multi_validator_poa import MultiValidatorPoA, Validator

class PBFTPhase(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    EXECUTE = "execute"

class PBFTMessageType(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"

@dataclass
class PBFTMessage:
    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float

@dataclass
class PBFTState:
    current_view: int
    current_sequence: int
    prepared_messages: Dict[str, List[PBFTMessage]]
    committed_messages: Dict[str, List[PBFTMessage]]
    pre_prepare_messages: Dict[str, PBFTMessage]

class PBFTConsensus:
    """PBFT consensus implementation"""
    
    def __init__(self, consensus: MultiValidatorPoA):
        self.consensus = consensus
        self.state = PBFTState(
            current_view=0,
            current_sequence=0,
            prepared_messages={},
            committed_messages={},
            pre_prepare_messages={}
        )
        self.fault_tolerance = max(1, len(consensus.get_consensus_participants()) // 3)
        self.required_messages = 2 * self.fault_tolerance + 1
        
    def get_message_digest(self, block_hash: str, sequence: int, view: int) -> str:
        """Generate message digest for PBFT"""
        content = f"{block_hash}:{sequence}:{view}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def pre_prepare_phase(self, proposer: str, block_hash: str) -> bool:
        """Phase 1: Pre-prepare"""
        sequence = self.state.current_sequence + 1
        view = self.state.current_view
        digest = self.get_message_digest(block_hash, sequence, view)
        
        message = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=proposer,
            view_number=view,
            sequence_number=sequence,
            digest=digest,
            signature="",  # Would be signed in real implementation
            timestamp=time.time()
        )
        
        # Store pre-prepare message
        key = f"{sequence}:{view}"
        self.state.pre_prepare_messages[key] = message
        
        # Broadcast to all validators
        await self._broadcast_message(message)
        return True
    
    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        """Phase 2: Prepare"""
        key = f"{pre_prepare_msg.sequence_number}:{pre_prepare_msg.view_number}"
        
        if key not in self.state.pre_prepare_messages:
            return False
        
        # Create prepare message
        prepare_msg = PBFTMessage(
            message_type=PBFTMessageType.PREPARE,
            sender=validator,
            view_number=pre_prepare_msg.view_number,
            sequence_number=pre_prepare_msg.sequence_number,
            digest=pre_prepare_msg.digest,
            signature="",  # Would be signed
            timestamp=time.time()
        )
        
        # Store prepare message
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        self.state.prepared_messages[key].append(prepare_msg)
        
        # Broadcast prepare message
        await self._broadcast_message(prepare_msg)
        
        # Check if we have enough prepare messages
        return len(self.state.prepared_messages[key]) >= self.required_messages
    
    async def commit_phase(self, validator: str, prepare_msg: PBFTMessage) -> bool:
        """Phase 3: Commit"""
        key = f"{prepare_msg.sequence_number}:{prepare_msg.view_number}"
        
        # Create commit message
        commit_msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=validator,
            view_number=prepare_msg.view_number,
            sequence_number=prepare_msg.sequence_number,
            digest=prepare_msg.digest,
            signature="",  # Would be signed
            timestamp=time.time()
        )
        
        # Store commit message
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        self.state.committed_messages[key].append(commit_msg)
        
        # Broadcast commit message
        await self._broadcast_message(commit_msg)
        
        # Check if we have enough commit messages
        if len(self.state.committed_messages[key]) >= self.required_messages:
            return await self.execute_phase(key)
        
        return False
    
    async def execute_phase(self, key: str) -> bool:
        """Phase 4: Execute"""
        # Extract sequence and view from key
        sequence, view = map(int, key.split(':'))
        
        # Update state
        self.state.current_sequence = sequence
        
        # Clean up old messages
        self._cleanup_messages(sequence)
        
        return True
    
    async def _broadcast_message(self, message: PBFTMessage):
        """Broadcast message to all validators"""
        validators = self.consensus.get_consensus_participants()
        
        for validator in validators:
            if validator != message.sender:
                # In real implementation, this would send over network
                await self._send_to_validator(validator, message)
    
    async def _send_to_validator(self, validator: str, message: PBFTMessage):
        """Send message to specific validator"""
        # Network communication would be implemented here
        pass
    
    def _cleanup_messages(self, sequence: int):
        """Clean up old messages to prevent memory leaks"""
        old_keys = [
            key for key in self.state.prepared_messages.keys()
            if int(key.split(':')[0]) < sequence
        ]
        
        for key in old_keys:
            self.state.prepared_messages.pop(key, None)
            self.state.committed_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)
    
    def handle_view_change(self, new_view: int) -> bool:
        """Handle view change when proposer fails"""
        self.state.current_view = new_view
        # Reset state for new view
        self.state.prepared_messages.clear()
        self.state.committed_messages.clear()
        self.state.pre_prepare_messages.clear()
        return True
