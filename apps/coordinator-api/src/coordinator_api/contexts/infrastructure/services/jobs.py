from __future__ import annotations
import os

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc_shared import JobPayment

from ....schemas import AssignedJob, Constraints, JobCreate, JobResult, JobView
from ...payments.acceptance import deadline_from
from ...payments.provider_binding import miner_wallet_address, same_address
from ...payments.services.payments import PaymentService
from ..domain import Job, JobReceipt, Miner
from ...reputation.domain.reputation import AgentReputation
from ....contexts.marketplace.domain.provider_bond import is_provider_eligible

logger = get_logger(__name__)

# P2.3: high-value jobs require an active/locked provider performance bond.
_BOND_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_BOND_HIGH_VALUE_THRESHOLD", "10"))
_BOND_REQUIRE = os.getenv("COORDINATOR_BOND_REQUIRE", "false").lower() == "true"


def _bond_required_for(job: Job) -> bool:
    """Return True if the job requires a performance bond check."""
    constraints = Constraints(**job.constraints) if isinstance(job.constraints, dict) else Constraints()
    if constraints.bond_required:
        return True
    if _BOND_REQUIRE:
        return True
    if job.payment_amount is not None and _BOND_THRESHOLD_AIT >= 0:
        return job.payment_amount >= _BOND_THRESHOLD_AIT
    return False


# G4: a job whose escrow never locked must not be handed to a miner. The
# marketplace purchase path already refused this case -- marketplace_gpu.py checks
# for "failed"/"skipped" before it returns a job id -- but POST /v1/jobs did not,
# so an escrow failure there was recorded as payment_status="skipped" and the job
# stayed dispatchable. A provider then burned GPU time for work nobody paid for.
#
# The allowlist is deliberate. "escrowed" is the one state the rest of the payment
# path treats as funds-locked: settlement_reconciler queries it, and miner.py will
# only release from it. Anything else -- pending, skipped, failed, released,
# refunded, or a state added later -- fails closed.
_PAYMENT_DISPATCHABLE_STATES = frozenset({"escrowed"})
_PAYMENT_REQUIRE = os.getenv("COORDINATOR_REQUIRE_PAYMENT", "true").lower() == "true"


def _payment_blocks_dispatch(job: Job) -> str | None:
    """Return why a job must not be dispatched, or None if it may run.

    ``payment_status`` is None for jobs submitted without a ``payment_amount``.
    Unpriced work is still allowed through; what is refused is a job that asked to
    be paid for and was not.

    Blocked jobs stay QUEUED rather than being failed outright, so a client can
    still secure the escrow against them via POST /v1/payments. If none arrives the
    job leaves the queue on its own when its TTL expires.
    """
    if not _PAYMENT_REQUIRE:
        return None
    payment_status = (job.payment_status or "").strip().lower()
    if not payment_status:
        if job.payment_amount is not None and job.payment_amount > 0:
            return "job is priced but carries no payment record"
        return None
    if payment_status in _PAYMENT_DISPATCHABLE_STATES:
        return None
    return f"payment not secured (payment_status={payment_status})"


# G2: an escrow names its payee before any miner is chosen, and the chain pays that
# address and no other -- rpc/escrow/{job_id}/release settles to the contract's
# agent_address, and the release call cannot redirect it. Assignment is therefore the
# only point where the payee and the worker can be tied together. Without this a buyer
# could name their own address as the provider, let a real miner do the work, and take
# the money back when the job completed.
_PROVIDER_BINDING_REQUIRE = os.getenv("COORDINATOR_REQUIRE_PROVIDER_BINDING", "true").lower() == "true"


def _provider_binding_blocks_dispatch(session: Session, job: Job, miner: Miner) -> str | None:
    """Return why this miner must not take this job, or None if it may.

    Only escrowed jobs carry a payee to protect. Unpriced work has none, and every
    other payment state is already refused by :func:`_payment_blocks_dispatch`.

    It fails closed on both sides of the comparison: a miner that registered no
    wallet, and an escrow that recorded no provider, block dispatch rather than
    falling back to some default address. As with the payment gate the job stays
    QUEUED, so the miner that *is* the payee can still pick it up.
    """
    if not _PROVIDER_BINDING_REQUIRE:
        return None
    if not job.payment_id or (job.payment_status or "").strip().lower() != "escrowed":
        return None
    payment = session.get(JobPayment, job.payment_id)
    if payment is None:
        return f"payment {job.payment_id} backing the escrow is missing"
    provider = (payment.meta_data or {}).get("provider_address")
    if not provider:
        return "the escrow records no provider address to pay"
    wallet = miner_wallet_address(miner)
    if not wallet:
        return f"miner {miner.id} registered no wallet_address, so it cannot be the escrow provider"
    if not same_address(wallet, provider):
        return f"miner {miner.id} wallet {wallet} is not the escrow provider {provider}"
    return None


def _to_utc(dt: datetime | None) -> datetime | None:
    """Make a datetime timezone-aware for comparison; SQLite returns naive datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class JobService:
    def __init__(self, session: Session):
        self.session = session
        self.payment_service = PaymentService(session)

    def create_job(self, client_id: str, req: JobCreate) -> Job:
        ttl = max(req.ttl_seconds, 1)
        now = datetime.now(UTC)
        job = Job(
            client_id=client_id,
            state="QUEUED",
            payload=req.payload,
            constraints=req.constraints.model_dump(mode="json") if hasattr(req.constraints, "model_dump") else req.constraints,
            ttl_seconds=ttl,
            requested_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        if req.payment_amount and req.payment_amount > 0:
            job.payment_amount = req.payment_amount
            job.payment_token = req.payment_currency
        # G1/D3: a job bought against an offer is bound to that offer's provider,
        # not just to the price. Keep the quoted terms on the job so dispatch
        # matching can consult them without a payment lookup.
        if req.offer_id:
            job.offer_id = req.offer_id
        if req.provider_address:
            job.provider_address = req.provider_address
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

    def list_jobs(
        self,
        client_id: str | None = None,
        assigned_miner_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        **filters: Any,
    ) -> list[Job]:
        """List jobs with optional filtering"""
        query = select(Job).order_by(Job.requested_at.desc())  # type: ignore[attr-defined]
        if client_id:
            query = query.where(Job.client_id == client_id)
        if assigned_miner_id:
            query = query.where(Job.assigned_miner_id == assigned_miner_id)
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

    def _payment_for(self, job: Job) -> JobPayment | None:
        if not job.payment_id:
            return None
        return self.session.get(JobPayment, job.payment_id)

    def _build_view(self, job: Job, payment: JobPayment | None) -> JobView:
        receipt = job.receipt or {}
        zk_proof = receipt.get("zk_proof") or {}
        offer_id: str | None = None
        offer_unit_price: Decimal | None = None
        offer_price_unit: str | None = None
        offer_quantity: Decimal | None = None
        acceptance_deadline: datetime | None = None
        if payment and payment.meta_data:
            meta = payment.meta_data
            # G3: a held payment tells the customer how long they have to object.
            acceptance_deadline = deadline_from(meta)
            offer_id = meta.get("offer_id") or offer_id
            offer_price_unit = meta.get("offer_price_unit") or offer_price_unit
            raw_unit_price = meta.get("offer_unit_price")
            if raw_unit_price:
                try:
                    offer_unit_price = Decimal(str(raw_unit_price))
                except (InvalidOperation, TypeError, ValueError):
                    pass
            raw_quantity = meta.get("offer_quantity")
            if raw_quantity:
                try:
                    offer_quantity = Decimal(str(raw_quantity))
                except (InvalidOperation, TypeError, ValueError):
                    pass
        return JobView(
            job_id=job.id,
            state=job.state,
            assigned_miner_id=job.assigned_miner_id,
            requested_at=job.requested_at,
            expires_at=job.expires_at,
            error=job.error,
            payment_id=job.payment_id,
            payload=job.payload,
            result=job.result,
            payment_status=job.payment_status,
            offer_id=offer_id,
            offer_unit_price=offer_unit_price,
            offer_price_unit=offer_price_unit,
            offer_quantity=offer_quantity,
            zk_status=receipt.get("zk_status"),
            zk_proof_id=zk_proof.get("circuit_hash"),
            tee_status=receipt.get("tee_status"),
            tee_attestation_id=receipt.get("tee_attestation_id"),
            auto_reinvest_pct=(job.constraints or {}).get("auto_reinvest_pct"),
            reinvest_status=receipt.get("reinvest_status"),
            reinvest_stake_id=receipt.get("reinvest_stake_id"),
            acceptance_deadline=acceptance_deadline,
        )

    def to_view(self, job: Job) -> JobView:
        return self._build_view(job, self._payment_for(job))

    def to_views(self, jobs: list[Job]) -> list[JobView]:
        # D4: batch-load JobPayment once for the whole list instead of one
        # session.get(JobPayment, ...) per job.
        payment_ids = [job.payment_id for job in jobs if job.payment_id]
        payments: dict[str, JobPayment] = {}
        if payment_ids:
            statement = select(JobPayment).where(JobPayment.id.in_(payment_ids))  # type: ignore[attr-defined]
            payments = {p.id: p for p in self.session.execute(statement).scalars().all()}
        return [self._build_view(job, payments.get(job.payment_id) if job.payment_id else None) for job in jobs]

    def to_result(self, job: Job) -> JobResult:
        return JobResult(result=job.result, receipt=job.receipt)

    def to_assigned(self, job: Job) -> AssignedJob:
        constraints = Constraints(**job.constraints) if isinstance(job.constraints, dict) else Constraints()
        return AssignedJob(job_id=job.id, payload=job.payload, constraints=constraints)

    def acquire_next_job(self, miner: Miner) -> Job | None:
        try:
            now = datetime.now(UTC)
            statement = select(Job).where(Job.state == "QUEUED").order_by(Job.requested_at.asc())  # type: ignore[attr-defined]
            jobs = self.session.scalars(statement).all()

            # Load the pool of online miners once per dispatch decision so we can
            # route high-reputation jobs to the best available provider.
            online_miners = list(self.session.scalars(select(Miner).where(Miner.status == "ONLINE")).all())
            current_reputation = self._get_miner_reputation(miner)

            for job in jobs:
                try:
                    job = self._ensure_not_expired(job)
                    if job.state != "QUEUED":
                        continue
                    if job.expires_at:
                        expires_at = _to_utc(job.expires_at)
                        if expires_at and expires_at <= now:
                            continue
                    unpaid_reason = _payment_blocks_dispatch(job)
                    if unpaid_reason:
                        logger.info("Job %s is not dispatchable: %s", job.id, unpaid_reason)
                        continue
                    mismatch_reason = _provider_binding_blocks_dispatch(self.session, job, miner)
                    if mismatch_reason:
                        logger.info("Job %s is not dispatchable to miner %s: %s", job.id, miner.id, mismatch_reason)
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
        expires_at = _to_utc(job.expires_at)
        if job.state in {"QUEUED", "RUNNING"} and expires_at and (expires_at <= datetime.now(UTC)):
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

        # D3: G1 binds the offer to a specific provider. A job quoted against one
        # provider's offer must not be satisfied by another miner, even if that
        # miner's general capabilities happen to match the customer's constraints.
        if job.offer_id and job.provider_address:
            wallet = miner_wallet_address(miner)
            if not wallet or not same_address(wallet, job.provider_address):
                logger.info(
                    "Job %s (offer %s) is bound to provider %s; miner %s does not match",
                    job.id,
                    job.offer_id,
                    job.provider_address,
                    miner.id,
                )
                return False
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

        if _bond_required_for(job):
            eligible = is_provider_eligible(self.session, miner.id)
            if not eligible:
                logger.info("Job %s requires a performance bond; miner %s is not eligible", job.id, miner.id)
                return False

        return True

    def _get_miner_reputation(self, miner: Miner) -> float:
        """Return the reputation score for a miner.

        The score can be reported by the miner (via heartbeat/registration
        metadata), derived from the agent reputation service, or computed from
        its historical job completion ratio.  A neutral starting value of 0.5 is
        used for miners with no track record so that first-time providers are
        neither favoured nor penalised.
        """
        for source in (miner.extra_metadata or {}, miner.capabilities or {}):
            reported = source.get("reputation_score")
            if reported is not None:
                try:
                    return float(reported)
                except (TypeError, ValueError):
                    pass

        # Prefer the canonical reputation service profile when available.
        try:
            reputation = (
                self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == miner.id)).scalars().first()
            )
            if reputation and reputation.trust_score is not None:
                # trust_score is on a 0-1000 scale; normalize to 0-1.
                trust_score: float = reputation.trust_score
                return max(0.0, min(1.0, trust_score / 1000.0))
        except Exception:
            logger.debug("Could not load reputation profile for %s", miner.id, exc_info=True)

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
            job.completed_at = datetime.now(UTC)
            if job.requested_at and job.requested_at.tzinfo is None:
                # Same normalization as _to_utc, inline so the assignment target
                # keeps its non-optional datetime type.
                job.requested_at = job.requested_at.replace(tzinfo=UTC)
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
