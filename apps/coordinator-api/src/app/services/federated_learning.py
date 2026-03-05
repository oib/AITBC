"""
Federated Learning Service

Service for managing cross-agent knowledge sharing and collaborative model training.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select
from fastapi import HTTPException

from ..domain.federated_learning import (
    FederatedLearningSession, TrainingParticipant, TrainingRound, 
    LocalModelUpdate, TrainingStatus, ParticipantStatus
)
from ..schemas.federated_learning import (
    FederatedSessionCreate, JoinSessionRequest, SubmitUpdateRequest
)
from ..blockchain.contract_interactions import ContractInteractionService

logger = logging.getLogger(__name__)

class FederatedLearningService:
    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService
    ):
        self.session = session
        self.contract_service = contract_service

    async def create_session(self, request: FederatedSessionCreate) -> FederatedLearningSession:
        """Create a new federated learning session"""
        
        session = FederatedLearningSession(
            initiator_agent_id=request.initiator_agent_id,
            task_description=request.task_description,
            model_architecture_cid=request.model_architecture_cid,
            initial_weights_cid=request.initial_weights_cid,
            target_participants=request.target_participants,
            total_rounds=request.total_rounds,
            aggregation_strategy=request.aggregation_strategy,
            min_participants_per_round=request.min_participants_per_round,
            reward_pool_amount=request.reward_pool_amount,
            status=TrainingStatus.GATHERING_PARTICIPANTS
        )
        
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        
        logger.info(f"Created Federated Learning Session {session.id} by {request.initiator_agent_id}")
        return session

    async def join_session(self, session_id: str, request: JoinSessionRequest) -> TrainingParticipant:
        """Allow an agent to join an active session"""
        
        fl_session = self.session.get(FederatedLearningSession, session_id)
        if not fl_session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if fl_session.status != TrainingStatus.GATHERING_PARTICIPANTS:
            raise HTTPException(status_code=400, detail="Session is not currently accepting participants")

        # Check if already joined
        existing = self.session.execute(
            select(TrainingParticipant).where(
                TrainingParticipant.session_id == session_id,
                TrainingParticipant.agent_id == request.agent_id
            )
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Agent already joined this session")

        # In reality, fetch reputation from blockchain/service
        mock_reputation = 95.0

        participant = TrainingParticipant(
            session_id=session_id,
            agent_id=request.agent_id,
            compute_power_committed=request.compute_power_committed,
            reputation_score_at_join=mock_reputation,
            status=ParticipantStatus.JOINED
        )
        
        self.session.add(participant)
        self.session.commit()
        self.session.refresh(participant)
        
        # Check if we have enough participants to start
        current_count = len(fl_session.participants) + 1 # +1 for the newly added but not refreshed one
        if current_count >= fl_session.target_participants:
            await self._start_training(fl_session)
            
        return participant

    async def _start_training(self, fl_session: FederatedLearningSession):
        """Internal method to transition from gathering to active training"""
        fl_session.status = TrainingStatus.TRAINING
        fl_session.current_round = 1
        
        # Start Round 1
        round1 = TrainingRound(
            session_id=fl_session.id,
            round_number=1,
            status="active",
            starting_model_cid=fl_session.initial_weights_cid or fl_session.model_architecture_cid
        )
        
        self.session.add(round1)
        self.session.commit()
        logger.info(f"Started training for session {fl_session.id}, Round 1 active.")

    async def submit_local_update(self, session_id: str, round_id: str, request: SubmitUpdateRequest) -> LocalModelUpdate:
        """Participant submits their locally trained model weights"""
        
        fl_session = self.session.get(FederatedLearningSession, session_id)
        current_round = self.session.get(TrainingRound, round_id)
        
        if not fl_session or not current_round:
            raise HTTPException(status_code=404, detail="Session or Round not found")
            
        if fl_session.status != TrainingStatus.TRAINING or current_round.status != "active":
            raise HTTPException(status_code=400, detail="Round is not currently active")

        participant = self.session.execute(
            select(TrainingParticipant).where(
                TrainingParticipant.session_id == session_id,
                TrainingParticipant.agent_id == request.agent_id
            )
        ).first()
        
        if not participant:
            raise HTTPException(status_code=403, detail="Agent is not a participant in this session")

        update = LocalModelUpdate(
            round_id=round_id,
            participant_agent_id=request.agent_id,
            weights_cid=request.weights_cid,
            zk_proof_hash=request.zk_proof_hash
        )
        
        participant.data_samples_count += request.data_samples_count
        participant.status = ParticipantStatus.SUBMITTED
        
        self.session.add(update)
        self.session.commit()
        self.session.refresh(update)
        
        # Check if we should trigger aggregation
        updates_count = len(current_round.updates) + 1
        if updates_count >= fl_session.min_participants_per_round:
            # Note: In a real system, this might be triggered asynchronously via a Celery task
            await self._aggregate_round(fl_session, current_round)
            
        return update

    async def _aggregate_round(self, fl_session: FederatedLearningSession, current_round: TrainingRound):
        """Mock aggregation process"""
        current_round.status = "aggregating"
        fl_session.status = TrainingStatus.AGGREGATING
        self.session.commit()
        
        # Mocking the actual heavy ML aggregation that would happen elsewhere
        logger.info(f"Aggregating {len(current_round.updates)} updates for round {current_round.round_number}")
        
        # Assume successful aggregation creates a new global CID
        import hashlib
        import time
        mock_hash = hashlib.md5(str(time.time()).encode()).hexdigest()
        new_global_cid = f"bafy_aggregated_{mock_hash[:20]}"
        
        current_round.aggregated_model_cid = new_global_cid
        current_round.status = "completed"
        current_round.completed_at = datetime.utcnow()
        current_round.metrics = {"loss": 0.5 - (current_round.round_number * 0.05), "accuracy": 0.7 + (current_round.round_number * 0.02)}
        
        if fl_session.current_round >= fl_session.total_rounds:
            fl_session.status = TrainingStatus.COMPLETED
            fl_session.global_model_cid = new_global_cid
            logger.info(f"Federated Learning Session {fl_session.id} fully completed.")
            # Here we would handle reward distribution via smart contracts
        else:
            fl_session.current_round += 1
            fl_session.status = TrainingStatus.TRAINING
            
            # Start next round
            next_round = TrainingRound(
                session_id=fl_session.id,
                round_number=fl_session.current_round,
                status="active",
                starting_model_cid=new_global_cid
            )
            self.session.add(next_round)
            
            # Reset participant statuses
            for p in fl_session.participants:
                if p.status == ParticipantStatus.SUBMITTED:
                    p.status = ParticipantStatus.TRAINING
                    
            logger.info(f"Session {fl_session.id} progressing to Round {fl_session.current_round}")
            
        self.session.commit()
