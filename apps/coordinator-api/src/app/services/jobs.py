from __future__ import annotations

from datetime import datetime, UTC, timedelta

from sqlmodel import Session, select

from ..domain import Job, JobReceipt, Miner
from ..schemas import AssignedJob, Constraints, JobCreate, JobResult, JobState, JobView
from .payments import PaymentService


class JobService:
    def __init__(self, session: Session):
        self.session = session
        self.payment_service = PaymentService(session)

    def create_job(self, client_id: str, req: JobCreate) -> Job:
        ttl = max(req.ttl_seconds, 1)
        now = datetime.now(datetime.UTC)
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

        # Create payment if amount is specified
        if req.payment_amount and req.payment_amount > 0:
            # Note: Payment creation is handled in the router
            pass

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
        return self.session.execute(select(JobReceipt).where(JobReceipt.job_id == job_id)).scalars().all()

    def list_jobs(self, client_id: str | None = None, limit: int = 20, offset: int = 0, **filters) -> list[Job]:
        """List jobs with optional filtering"""
        query = select(Job).order_by(Job.requested_at.desc())

        if client_id:
            query = query.where(Job.client_id == client_id)

        # Apply filters
        if "state" in filters:
            query = query.where(Job.state == filters["state"])

        if "job_type" in filters:
            # Filter by job type in payload
            query = query.where(Job.payload["type"].as_string() == filters["job_type"])

        # Apply pagination
        query = query.offset(offset).limit(limit)

        return self.session.execute(query).scalars().all()

    def fail_job(self, job_id: str, miner_id: str, error_message: str) -> Job:
        """Mark a job as failed"""
        job = self.get_job(job_id)
        job.state = JobState.FAILED
        job.error = error_message
        job.assigned_miner_id = miner_id
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

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
            payment_id=job.payment_id,
            payment_status=job.payment_status,
        )

    def to_result(self, job: Job) -> JobResult:
        return JobResult(result=job.result, receipt=job.receipt)

    def to_assigned(self, job: Job) -> AssignedJob:
        constraints = Constraints(**job.constraints) if isinstance(job.constraints, dict) else Constraints()
        return AssignedJob(job_id=job.id, payload=job.payload, constraints=constraints)

    def acquire_next_job(self, miner: Miner) -> Job | None:
        try:
            now = datetime.now(datetime.UTC)
            statement = select(Job).where(Job.state == JobState.queued).order_by(Job.requested_at.asc())

            jobs = self.session.scalars(statement).all()
            for job in jobs:
                try:
                    job = self._ensure_not_expired(job)
                    if job.state != JobState.queued:
                        continue
                    if job.expires_at <= now:
                        continue
                    if not self._satisfies_constraints(job, miner):
                        continue

                    # Update job state
                    job.state = JobState.running
                    job.assigned_miner_id = miner.id
                    self.session.add(job)
                    self.session.commit()
                    self.session.refresh(job)
                    return job
                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error checking job {job.id}: {e}")
                    self.session.rollback()  # Rollback on individual job failure
                    continue

            return None
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error acquiring next job: {e}")
            raise  # Propagate for caller to handle

    def _ensure_not_expired(self, job: Job) -> Job:
        if job.state in {JobState.queued, JobState.running} and job.expires_at <= datetime.now(datetime.UTC):
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
