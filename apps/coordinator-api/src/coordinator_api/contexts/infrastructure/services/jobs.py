from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ....schemas import AssignedJob, Constraints, JobCreate, JobResult, JobView
from ...payments.services.payments import PaymentService
from ..domain import Job, JobReceipt, Miner

logger = get_logger(__name__)


class JobService:
    def __init__(self, session: Session):
        self.session = session
        self.payment_service = PaymentService(session)

    def create_job(self, client_id: str, req: JobCreate) -> Job:
        ttl = max(req.ttl_seconds, 1)
        now = datetime.now()
        job = Job(
            client_id=client_id,
            state="QUEUED",
            payload=req.payload,
            constraints=req.constraints.model_dump() if hasattr(req.constraints, "model_dump") else req.constraints,
            ttl_seconds=ttl,
            requested_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        if req.payment_amount and req.payment_amount > 0:
            job.payment_amount = req.payment_amount
            job.payment_token = req.payment_currency
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get_job(self, job_id: str, client_id: str | None = None) -> Job:
        query = select(Job).where(Job.id == job_id)
        if client_id:
            query = query.where(Job.client_id == client_id)
        job = self.session.execute(query).scalar_one_or_none()
        if not job:
            raise KeyError("job not found")
        return self._ensure_not_expired(job)

    def list_receipts(self, job_id: str, client_id: str | None = None) -> list[JobReceipt]:
        self.get_job(job_id, client_id=client_id)
        return list(self.session.execute(select(JobReceipt).where(JobReceipt.job_id == job_id)).scalars().all())

    def list_jobs(self, client_id: str | None = None, limit: int = 20, offset: int = 0, **filters: Any) -> list[Job]:
        """List jobs with optional filtering"""
        query = select(Job).order_by(Job.requested_at.desc())  # type: ignore[attr-defined]
        if client_id:
            query = query.where(Job.client_id == client_id)
        if "state" in filters:
            query = query.where(Job.state == filters["state"])
        if "job_type" in filters:
            query = query.where(Job.payload["type"].as_string() == filters["job_type"])
        query = query.offset(offset).limit(limit)
        return list(self.session.execute(query).scalars().all())

    def fail_job(self, job_id: str, miner_id: str, error_message: str) -> Job:
        """Mark a job as failed"""
        job = self.get_job(job_id)
        job.state = "FAILED"
        job.error = error_message
        job.assigned_miner_id = miner_id
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def cancel_job(self, job: Job) -> Job:
        if job.state not in {"QUEUED", "RUNNING"}:
            return job
        job.state = "CANCELED"
        job.error = "canceled by client"
        job.assigned_miner_id = None
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def to_view(self, job: Job) -> JobView:
        receipt = job.receipt or {}
        zk_proof = receipt.get("zk_proof") or {}
        return JobView(
            job_id=job.id,
            state=job.state,
            assigned_miner_id=job.assigned_miner_id,
            requested_at=job.requested_at,
            expires_at=job.expires_at,
            error=job.error,
            payment_id=job.payment_id,
            payment_status=job.payment_status,
            zk_status=receipt.get("zk_status"),
            zk_proof_id=zk_proof.get("circuit_hash"),
        )

    def to_result(self, job: Job) -> JobResult:
        return JobResult(result=job.result, receipt=job.receipt)

    def to_assigned(self, job: Job) -> AssignedJob:
        constraints = Constraints(**job.constraints) if isinstance(job.constraints, dict) else Constraints()
        return AssignedJob(job_id=job.id, payload=job.payload, constraints=constraints)

    def acquire_next_job(self, miner: Miner) -> Job | None:
        try:
            now = datetime.now()
            statement = select(Job).where(Job.state == "QUEUED").order_by(Job.requested_at.asc())  # type: ignore[attr-defined]
            jobs = self.session.scalars(statement).all()

            # Load the pool of online miners once per dispatch decision so we can
            # route high-reputation jobs to the best available provider.
            online_miners = list(
                self.session.scalars(select(Miner).where(Miner.status == "ONLINE")).all()
            )
            current_reputation = self._get_miner_reputation(miner)

            for job in jobs:
                try:
                    job = self._ensure_not_expired(job)
                    if job.state != "QUEUED":
                        continue
                    if job.expires_at and job.expires_at <= now:
                        continue
                    if not self._satisfies_constraints(job, miner):
                        continue
                    if self._has_higher_reputation_miner(job, online_miners, miner, current_reputation):
                        # A better-suited, higher-reputation miner is online and
                        # has capacity. Leave this job for them to pick up.
                        continue
                    job.state = "RUNNING"
                    job.assigned_miner_id = miner.id
                    self.session.add(job)
                    self.session.commit()
                    self.session.refresh(job)
                    return job
                except Exception as e:
                    logger.warning("Error checking job %s: %s", job.id, e)
                    self.session.rollback()
                    continue
            return None
        except Exception as e:
            logger.error("Error acquiring next job: %s", e)
            raise

    def _ensure_not_expired(self, job: Job) -> Job:
        if job.state in {"QUEUED", "RUNNING"} and job.expires_at and (job.expires_at <= datetime.now()):
            job.state = "EXPIRED"
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
            if price is None:
                return False
            try:
                price_value = Decimal(str(price))
            except (TypeError, ValueError, InvalidOperation):
                return False
            if price_value > Decimal(str(constraints.max_price)):
                return False
        if constraints.min_reputation is not None:
            if self._get_miner_reputation(miner) < constraints.min_reputation:
                return False
        return True

    def _get_miner_reputation(self, miner: Miner) -> float:
        """Return the reputation score for a miner.

        The score can be reported by the miner (via heartbeat/registration
        metadata) or derived from its historical job completion ratio.  A neutral
        starting value of 0.5 is used for miners with no track record so that
        first-time providers are neither favoured nor penalised.
        """
        for source in (miner.extra_metadata or {}, miner.capabilities or {}):
            reported = source.get("reputation_score")
            if reported is not None:
                try:
                    return float(reported)
                except (TypeError, ValueError):
                    pass

        total = (miner.jobs_completed or 0) + (miner.jobs_failed or 0)
        if total == 0:
            return 0.5
        return miner.jobs_completed / total

    def _has_higher_reputation_miner(
        self,
        job: Job,
        online_miners: list[Miner],
        current_miner: Miner,
        current_reputation: float,
    ) -> bool:
        """Check whether a higher-reputation, capable miner is available for a job."""
        constraints = Constraints(**job.constraints) if job.constraints else Constraints()
        for other in online_miners:
            if other.id == current_miner.id:
                continue
            if other.status != "ONLINE":
                continue
            if other.concurrency and other.inflight >= other.concurrency:
                continue
            if not self._satisfies_constraints(job, other):
                continue
            if constraints.min_reputation is not None:
                if self._get_miner_reputation(other) < constraints.min_reputation:
                    continue
            if self._get_miner_reputation(other) > current_reputation:
                return True
        return False

    def execute_job(self, job_id: str, result: dict[str, Any]) -> Job:
        """
        Execute a job and store results.

        This method processes the actual AI work and updates the job state.
        """
        try:
            statement = select(Job).where(Job.id == job_id)
            job = self.session.scalars(statement).first()
            if not job:
                raise ValueError(f"Job {job_id} not found")
            if job.state != "RUNNING":
                raise ValueError(f"Job {job_id} is not in running state")
            job.state = "COMPLETED"
            job.result = result.get("output")
            job.receipt = result.get("receipt")
            job.completed_at = datetime.now()
            self.session.add(job)
            self.session.commit()
            self.session.refresh(job)
            logger.info(
                "Job %s executed successfully",
                job_id,
                extra={"job_id": job_id, "result_size": len(str(result)) if result else 0},
            )
            return job
        except Exception as e:
            logger.error("Failed to execute job %s: %s", job_id, e)
            self.session.rollback()
            try:
                statement = select(Job).where(Job.id == job_id)
                job = self.session.scalars(statement).first()
                if job:
                    job.state = "FAILED"
                    job.error = str(e)
                    self.session.add(job)
                    self.session.commit()
            except Exception:
                pass
            raise
