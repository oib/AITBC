"""
Example router demonstrating JWT auth migration
This is a reference implementation for migrating from API key to JWT auth
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from ..auth import ClientDep  # NEW: JWT auth dependency
from ..config import settings
from ..contexts.payments.services.payments import PaymentService

# from ..deps import require_client_key  # OLD: API key auth (deprecated)
from ..schemas import JobCreate, JobPaymentCreate, JobView
from ..services import JobService
from ..storage import get_session

logger = get_logger(__name__)
router = APIRouter(tags=["client"])

if settings.debug:

    @router.post("/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED, summary="Submit a job")
    @rate_limit(rate=50, per=60)
    async def submit_job(
        req: JobCreate,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
        # OLD: client_id: Annotated[str, Depends(require_client_key())],
        # NEW: JWT auth with user info
        user: ClientDep,
    ) -> JobView:
        """
        Submit a new job to the coordinator.

        JWT auth provides:
        - user["sub"]: User ID
        - user["role"]: User role (client)
        - user["exp"]: Token expiration
        """
        # Extract client_id from JWT token
        client_id = user["sub"]

        service = JobService(session)
        job = service.create_job(client_id, req)
        if req.payment_amount and req.payment_amount > 0:
            try:
                payment_service = PaymentService(session)
                payment_create = JobPaymentCreate(
                    job_id=job.id, amount=req.payment_amount, currency=req.payment_currency, payment_method="aitbc_token"
                )
                payment = await payment_service.create_payment(job.id, payment_create)
                job.payment_id = payment.id
                job.payment_status = payment.status
                session.commit()
                session.refresh(job)
                logger.info("Payment created for job %s: %s", job.id, payment.id)
            except Exception as e:
                logger.warning("Payment creation failed for job %s, proceeding without payment: %s", job.id, e)
                job.payment_status = "skipped"
        session.commit()
        session.refresh(job)
        logger.info("Job submitted by client %s: %s", client_id, job.id)
        return job

    @router.get("/jobs/{job_id}", response_model=JobView, summary="Get job details")
    @rate_limit(rate=100, per=60)
    async def get_job(
        job_id: str,
        session: Annotated[Session, Depends(get_session)],
        # OLD: client_id: Annotated[str, Depends(require_client_key())],
        # NEW: JWT auth
        user: ClientDep,
    ) -> JobView:
        """
        Get details of a specific job.

        JWT auth ensures only the client who submitted the job can view it.
        """
        client_id = user["sub"]

        service = JobService(session)
        job = service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.client_id != client_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return job

    @router.get("/jobs", response_model=list[JobView], summary="List client jobs")
    @rate_limit(rate=100, per=60)
    async def list_jobs(
        session: Annotated[Session, Depends(get_session)],
        # OLD: client_id: Annotated[str, Depends(require_client_key())],
        # NEW: JWT auth
        user: ClientDep,
        skip: int = 0,
        limit: int = 100,
    ) -> list[JobView]:
        """
        List all jobs submitted by the client.

        JWT auth ensures clients only see their own jobs.
        """
        client_id = user["sub"]

        service = JobService(session)
        jobs = service.list_client_jobs(client_id, skip=skip, limit=limit)
        return jobs


# ============================================================================
# MIGRATION NOTES
# ============================================================================
#
# Key changes from API key to JWT auth:
#
# 1. Import change:
#    OLD: from ..deps import require_client_key
#    NEW: from ..auth import ClientDep
#
# 2. Dependency change:
#    OLD: client_id: Annotated[str, Depends(require_client_key())]
#    NEW: user: ClientDep
#
# 3. User ID extraction:
#    OLD: client_id is directly available
#    NEW: client_id = user["sub"]
#
# 4. Additional JWT benefits:
#    - user["role"]: Role verification
#    - user["exp"]: Token expiration
#    - user["iat"]: Token issued at
#    - Can add custom claims in token
#
# 5. Client code change:
#    OLD: headers = {"X-Api-Key": "your-api-key"}
#    NEW: headers = {"Authorization": f"Bearer {token}"}
#
# ============================================================================
