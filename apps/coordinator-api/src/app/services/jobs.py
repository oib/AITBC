from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..domain import Job, Miner, JobReceipt
from ..models import AssignedJob, Constraints, JobCreate, JobResult, JobState, JobView


class JobService:
    def __init__(self, session: Session):
        self.session = session

    def create_job(self, client_id: str, req: JobCreate) -> Job:
        ttl = max(req.ttl_seconds, 1)
        now = datetime.utcnow()
        job = Job(
            client_id=client_id,
            payload=req.payload,
            constraints=req.constraints.model_dump(exclude_none=True),
            ttl_seconds=ttl,
            requested_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_job(self, job_id: str, client_id: Optional[str] = None) -> Job:
        query = select(Job).where(Job.id == job_id)
        if client_id:
            query = query.where(Job.client_id == client_id)
        job = self.session.exec(query).one_or_none()
        if not job:
            raise KeyError("job not found")
        return self._ensure_not_expired(job)

    def list_receipts(self, job_id: str, client_id: Optional[str] = None) -> list[JobReceipt]:
        job = self.get_job(job_id, client_id=client_id)
        receipts = self.session.exec(
            select(JobReceipt)
            .where(JobReceipt.job_id == job.id)
            .order_by(JobReceipt.created_at.asc())
        ).all()
        return receipts

    def cancel_job(self, job: Job) -> Job:
        if job.state not in {JobState.queued, JobState.running}:
            return job
        job.state = JobState.canceled
        job.error = "canceled by client"
        job.assigned_miner_id = None
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def to_view(self, job: Job) -> JobView:
        return JobView(
            job_id=job.id,
            state=job.state,
            assigned_miner_id=job.assigned_miner_id,
            requested_at=job.requested_at,
            expires_at=job.expires_at,
            error=job.error,
        )

    def to_result(self, job: Job) -> JobResult:
        return JobResult(result=job.result, receipt=job.receipt)

    def to_assigned(self, job: Job) -> AssignedJob:
        constraints = Constraints(**job.constraints) if isinstance(job.constraints, dict) else Constraints()
        return AssignedJob(job_id=job.id, payload=job.payload, constraints=constraints)

    def acquire_next_job(self, miner: Miner) -> Optional[Job]:
        now = datetime.utcnow()
        statement = (
            select(Job)
            .where(Job.state == JobState.queued)
            .order_by(Job.requested_at.asc())
        )

        jobs = self.session.exec(statement).all()
        for job in jobs:
            job = self._ensure_not_expired(job)
            if job.state != JobState.queued:
                continue
            if job.expires_at <= now:
                continue
            if not self._satisfies_constraints(job, miner):
                continue
            job.state = JobState.running
            job.assigned_miner_id = miner.id
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
            return job
        return None

    def _ensure_not_expired(self, job: Job) -> Job:
        if job.state == JobState.queued and job.expires_at <= datetime.utcnow():
            job.state = JobState.expired
            job.error = "job expired"
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
        return job

    def _satisfies_constraints(self, job: Job, miner: Miner) -> bool:
        if not job.constraints:
            return True
        constraints = Constraints(**job.constraints)
        capabilities = miner.capabilities or {}

        # Region matching
        if constraints.region and constraints.region != miner.region:
            return False

        gpu_specs = capabilities.get("gpus", []) or []
        has_gpu = bool(gpu_specs)

        if constraints.gpu:
            if not has_gpu:
                return False
            names = [gpu.get("name") for gpu in gpu_specs]
            if constraints.gpu not in names:
                return False

        if constraints.min_vram_gb:
            required_mb = constraints.min_vram_gb * 1024
            if not any((gpu.get("memory_mb") or 0) >= required_mb for gpu in gpu_specs):
                return False

        if constraints.cuda:
            cuda_info = capabilities.get("cuda")
            if not cuda_info or constraints.cuda not in str(cuda_info):
                return False

        if constraints.models:
            available_models = capabilities.get("models", [])
            if not set(constraints.models).issubset(set(available_models)):
                return False

        if constraints.max_price is not None:
            price = capabilities.get("price")
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                return False
            if price_value > constraints.max_price:
                return False

        return True
