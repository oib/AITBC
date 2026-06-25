"""
Federated Learning Service

Service for managing cross-agent knowledge sharing and collaborative model training.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..blockchain.contract_interactions import ContractInteractionService  # type: ignore[import-not-found]
from ..contexts.advanced_ai.domain.federated_learning import (
    FederatedLearningSession,
    LocalModelUpdate,
    ParticipantStatus,
    TrainingParticipant,
    TrainingRound,
    TrainingStatus,
)
from ..contexts.advanced_ai.schemas.federated_learning import FederatedSessionCreate, JoinSessionRequest, SubmitUpdateRequest

logger = get_logger(__name__)


class FederatedLearningService:
    def __init__(self, session: Session, contract_service: ContractInteractionService):
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
            status=TrainingStatus.GATHERING_PARTICIPANTS,
        )
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        logger.info("Created Federated Learning Session %s by %s", session.id, request.initiator_agent_id)
        return session

    async def join_session(self, session_id: str, request: JoinSessionRequest) -> TrainingParticipant:
        """Allow an agent to join an active session"""
        fl_session = self.session.get(FederatedLearningSession, session_id)
        if not fl_session:
            raise HTTPException(status_code=404, detail="Session not found")
        if fl_session.status != TrainingStatus.GATHERING_PARTICIPANTS:
            raise HTTPException(status_code=400, detail="Session is not currently accepting participants")
        existing = self.session.execute(
            select(TrainingParticipant).where(
                TrainingParticipant.session_id == session_id, TrainingParticipant.agent_id == request.agent_id
            )
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Agent already joined this session")
        mock_reputation = 95.0
        participant = TrainingParticipant(
            session_id=session_id,
            agent_id=request.agent_id,
            compute_power_committed=request.compute_power_committed,
            reputation_score_at_join=mock_reputation,
            status=ParticipantStatus.JOINED,
        )
        self.session.add(participant)
        self.session.commit()
        self.session.refresh(participant)
        from sqlalchemy import func

        current_count = (
            self.session.scalar(
                select(func.count()).select_from(TrainingParticipant).where(TrainingParticipant.session_id == fl_session.id)
            )
            or 0
        ) + 1
        if current_count >= fl_session.target_participants:
            await self._start_training(fl_session)
        return participant

    async def _start_training(self, fl_session: FederatedLearningSession) -> None:
        """Internal method to transition from gathering to active training"""
        fl_session.status = TrainingStatus.TRAINING
        fl_session.current_round = 1
        round1 = TrainingRound(
            session_id=fl_session.id,
            round_number=1,
            status="active",
            starting_model_cid=fl_session.initial_weights_cid or fl_session.model_architecture_cid,
        )
        self.session.add(round1)
        self.session.commit()
        logger.info("Started training for session %s, Round 1 active.", fl_session.id)

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
                TrainingParticipant.session_id == session_id, TrainingParticipant.agent_id == request.agent_id
            )
        ).first()
        if not participant:
            raise HTTPException(status_code=403, detail="Agent is not a participant in this session")
        update = LocalModelUpdate(
            round_id=round_id,
            participant_agent_id=request.agent_id,
            weights_cid=request.weights_cid,
            zk_proof_hash=request.zk_proof_hash,
        )
        participant.data_samples_count += request.data_samples_count
        participant.status = ParticipantStatus.SUBMITTED
        self.session.add(update)
        self.session.commit()
        self.session.refresh(update)
        from sqlalchemy import func

        updates_count = (
            self.session.scalar(
                select(func.count()).select_from(LocalModelUpdate).where(LocalModelUpdate.round_id == current_round.id)
            )
            or 0
        ) + 1
        if updates_count >= fl_session.min_participants_per_round:
            await self._aggregate_round(fl_session, current_round)
        return update

    async def _aggregate_round(self, fl_session: FederatedLearningSession, current_round: TrainingRound) -> None:
        """Mock aggregation process"""
        current_round.status = "aggregating"
        fl_session.status = TrainingStatus.AGGREGATING
        self.session.commit()
        from sqlalchemy import func

        round_updates_count = (
            self.session.scalar(
                select(func.count()).select_from(LocalModelUpdate).where(LocalModelUpdate.round_id == current_round.id)
            )
            or 0
        )
        logger.info("Aggregating %s updates for round %s", round_updates_count, current_round.round_number)
        import hashlib
        import time

        mock_hash = hashlib.sha256(str(time.time()).encode()).hexdigest()
        new_global_cid = f"bafy_aggregated_{mock_hash[:20]}"
        current_round.aggregated_model_cid = new_global_cid
        current_round.status = "completed"
        current_round.completed_at = datetime.now(UTC)
        current_round.metrics = {
            "loss": 0.5 - current_round.round_number * 0.05,
            "accuracy": 0.7 + current_round.round_number * 0.02,
        }
        if fl_session.current_round >= fl_session.total_rounds:
            fl_session.status = TrainingStatus.COMPLETED
            fl_session.global_model_cid = new_global_cid
            logger.info("Federated Learning Session %s fully completed.", fl_session.id)
        else:
            fl_session.current_round += 1
            fl_session.status = TrainingStatus.TRAINING
            next_round = TrainingRound(
                session_id=fl_session.id,
                round_number=fl_session.current_round,
                status="active",
                starting_model_cid=new_global_cid,
            )
            self.session.add(next_round)
            for p in self.session.scalars(
                select(TrainingParticipant).where(TrainingParticipant.session_id == fl_session.id)
            ).all():
                if p.status == ParticipantStatus.SUBMITTED:
                    p.status = ParticipantStatus.TRAINING
            logger.info("Session %s progressing to Round %s", fl_session.id, fl_session.current_round)
        self.session.commit()
