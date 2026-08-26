from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

_MINER_HEARTBEAT_CUTOFF_SECONDS = int(os.getenv("COORDINATOR_MINER_HEARTBEAT_CUTOFF_SECONDS", "300"))
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from ..domain import Miner
from ...payments.provider_binding import WALLET_CAPABILITY_KEY
from ....schemas import AssignedJob, MinerHeartbeat, MinerRegister
from .jobs import JobService


class MinerService:
    def __init__(self, session: Session):
        self.session = session

    def register(self, miner_id: str, payload: MinerRegister) -> Miner:
        miner = self.session.get(Miner, miner_id)
        session_token = uuid4().hex
        # G2: the payout address is folded into capabilities rather than kept in
        # extra_metadata, because heartbeat() replaces extra_metadata wholesale and
        # would drop it on the next beat. A miner that puts wallet_address straight
        # into its capabilities dict works without the explicit field.
        capabilities = dict(payload.capabilities or {})
        if payload.wallet_address:
            capabilities[WALLET_CAPABILITY_KEY] = payload.wallet_address
        if miner is None:
            miner = Miner(
                id=miner_id,
                capabilities=capabilities,
                concurrency=payload.concurrency,
                region=payload.region,
                session_token=session_token,
            )
            self.session.add(miner)
        else:
            miner.capabilities = capabilities
            miner.concurrency = payload.concurrency
            miner.region = payload.region
            miner.session_token = session_token
        miner.inflight = 0
        miner.last_heartbeat = datetime.now(UTC)
        miner.status = "ONLINE"
        self.session.commit()
        self.session.refresh(miner)
        return miner

    def heartbeat(self, miner_id: str, payload: MinerHeartbeat | dict[str, Any]) -> Miner:
        if not isinstance(payload, MinerHeartbeat):
            payload = MinerHeartbeat.model_validate(payload)
        miner = self.session.get(Miner, miner_id)
        if miner is None:
            raise KeyError("miner not registered")
        miner.inflight = payload.inflight
        miner.status = payload.status
        metadata = dict(payload.metadata)
        if payload.architecture is not None:
            metadata["architecture"] = payload.architecture
        if payload.edge_optimized is not None:
            metadata["edge_optimized"] = payload.edge_optimized
        if payload.network_latency_ms is not None:
            metadata["network_latency_ms"] = payload.network_latency_ms
        miner.extra_metadata = metadata
        miner.last_heartbeat = datetime.now(UTC)
        self.session.add(miner)
        self.session.commit()
        self.session.refresh(miner)
        return miner

    def poll(self, miner_id: str, max_wait_seconds: int) -> AssignedJob | None:
        miner = self.session.get(Miner, miner_id)
        if miner is None:
            raise KeyError("miner not registered")
        if miner.concurrency and miner.inflight >= miner.concurrency:
            return None

        job_service = JobService(self.session)
        job = job_service.acquire_next_job(miner)
        if not job:
            return None

        miner.inflight += 1
        miner.last_heartbeat = datetime.now(UTC)
        miner.last_job_at = datetime.now(UTC)
        self.session.add(miner)
        self.session.commit()
        return job_service.to_assigned(job)

    def release(
        self,
        miner_id: str,
        success: bool | None = None,
        duration_ms: int | None = None,
        receipt_id: str | None = None,
    ) -> None:
        miner = self.session.get(Miner, miner_id)
        if miner:
            miner.inflight = max(0, miner.inflight - 1)
            if success is True:
                miner.jobs_completed += 1
                if duration_ms is not None:
                    miner.total_job_duration_ms += duration_ms
                    miner.average_job_duration_ms = miner.total_job_duration_ms / max(miner.jobs_completed, 1)
            elif success is False:
                miner.jobs_failed += 1
            if receipt_id:
                miner.last_receipt_id = receipt_id
            self.session.add(miner)
            self.session.commit()

    def get(self, miner_id: str) -> Miner:
        miner = self.session.get(Miner, miner_id)
        if miner is None:
            raise KeyError("miner not registered")
        return miner

    def list_records(self) -> list[Miner]:
        return list(self.session.scalars(select(Miner)).all())

    def online_count(self) -> int:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=_MINER_HEARTBEAT_CUTOFF_SECONDS)
        statement = select(Miner).where(Miner.status == "ONLINE", Miner.last_heartbeat >= cutoff)
        result = self.session.execute(statement)
        return len(result.all())

    def deregister(self, miner_id: str) -> None:
        """Deregister a miner from the system"""
        miner = self.session.get(Miner, miner_id)
        if miner is None:
            raise KeyError("miner not registered")

        # Set status to OFFLINE instead of deleting to maintain history
        miner.status = "OFFLINE"
        miner.session_token = None
        self.session.add(miner)
        self.session.commit()
