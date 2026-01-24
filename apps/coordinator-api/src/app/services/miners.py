from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, select

from ..domain import Miner
from ..schemas import AssignedJob, MinerHeartbeat, MinerRegister
from .jobs import JobService


class MinerService:
    def __init__(self, session: Session):
        self.session = session

    def register(self, miner_id: str, payload: MinerRegister) -> Miner:
        miner = self.session.get(Miner, miner_id)
        session_token = uuid4().hex
        if miner is None:
            miner = Miner(
                id=miner_id,
                capabilities=payload.capabilities,
                concurrency=payload.concurrency,
                region=payload.region,
                session_token=session_token,
            )
            self.session.add(miner)
        else:
            miner.capabilities = payload.capabilities
            miner.concurrency = payload.concurrency
            miner.region = payload.region
            miner.session_token = session_token
        miner.inflight = 0
        miner.last_heartbeat = datetime.utcnow()
        miner.status = "ONLINE"
        self.session.commit()
        self.session.refresh(miner)
        return miner

    def heartbeat(self, miner_id: str, payload: MinerHeartbeat | dict) -> Miner:
        if not isinstance(payload, MinerHeartbeat):
            payload = MinerHeartbeat.model_validate(payload)
        miner = self.session.get(Miner, miner_id)
        if miner is None:
            raise KeyError("miner not registered")
        miner.inflight = payload.inflight
        miner.status = payload.status
        miner.extra_metadata = payload.metadata
        miner.last_heartbeat = datetime.utcnow()
        self.session.add(miner)
        self.session.commit()
        self.session.refresh(miner)
        return miner

    def poll(self, miner_id: str, max_wait_seconds: int) -> Optional[AssignedJob]:
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
        miner.last_heartbeat = datetime.utcnow()
        miner.last_job_at = datetime.utcnow()
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
                    miner.average_job_duration_ms = (
                        miner.total_job_duration_ms / max(miner.jobs_completed, 1)
                    )
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
        return list(self.session.exec(select(Miner)).all())

    def online_count(self) -> int:
        result = self.session.exec(select(Miner).where(Miner.status == "ONLINE"))
        return len(result.all())
