"""Edge serve service for Edge API Service"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from ..schemas.serve import ComputeRequest, ComputeResult
from ..storage import get_session


class EscrowAlreadyUsedError(Exception):
    """The escrow key is already bound to a compute request (#1668).

    Raised instead of letting the unique constraint surface as a bare
    IntegrityError -> HTTP 500; the router maps it to 409.
    """


class ServeService:
    """Service for edge serve operations"""

    async def _escrow_in_use(self, escrow_id: str) -> bool:
        """True when any compute request already carries this escrow key."""
        async with get_session() as session:
            result = await session.execute(select(ComputeRequest.id).where(ComputeRequest.escrow_id == escrow_id))
            return result.scalar_one_or_none() is not None

    async def submit_compute_request(
        self,
        gpu_id: str,
        model_name: str,
        input_data: dict[str, Any],
        priority: str = "normal",
        owner_id: str | None = None,
        escrow_id: str | None = None,
        escrow_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        """Submit compute request.

        ``escrow_id``/``escrow_amount`` bind the request to the escrow the
        router verified (#1668). The binding is single-use: the unique
        ``escrow_id`` column plus the pre-check below mean one locked escrow
        authorizes exactly one request, and a second submission gets
        ``EscrowAlreadyUsedError`` instead of a silent reuse.
        """
        if escrow_id and await self._escrow_in_use(escrow_id):
            raise EscrowAlreadyUsedError(escrow_id)
        async with get_session() as session:
            # request_id is the public lookup key and is unique-constrained
            # (#1685): a collision surfaces as IntegrityError, so regenerate
            # and retry a bounded number of times before giving up.
            for attempt in range(3):
                request_id = f"req_{uuid4().hex}"
                request = ComputeRequest(
                    request_id=request_id,
                    gpu_id=gpu_id,
                    model_name=model_name,
                    input_data=input_data,
                    priority=priority,
                    status="queued",
                    owner_id=owner_id,
                    escrow_id=escrow_id,
                    escrow_amount=escrow_amount,
                )
                session.add(request)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    # escrow_id has its own unique constraint (#1668): an
                    # IntegrityError caused by a concurrent claim of the same
                    # escrow is not a request_id collision — report it as
                    # reuse instead of burning the request_id retries.
                    if escrow_id and await self._escrow_in_use(escrow_id):
                        raise EscrowAlreadyUsedError(escrow_id) from None
                    if attempt == 2:
                        raise
                else:
                    return {
                        "success": True,
                        "request_id": request_id,
                        "status": "queued",
                        "message": f"Compute request {request_id} submitted",
                    }
            raise RuntimeError("unreachable")

    async def get_compute_request(self, request_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        """Get compute request details.

        ``owner_id`` restricts the lookup to requests owned by that caller
        (non-admin path); ``None`` means admin/unrestricted.
        """
        async with get_session() as session:
            query = select(ComputeRequest).where(ComputeRequest.request_id == request_id)
            if owner_id is not None:
                query = query.where(ComputeRequest.owner_id == owner_id)
            result = await session.execute(query)
            req = result.scalar_one_or_none()

            if req:
                return {
                    "request_id": req.request_id,
                    "gpu_id": req.gpu_id,
                    "model_name": req.model_name,
                    "input_data": req.input_data,
                    "priority": req.priority,
                    "status": req.status,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                    "started_at": req.started_at.isoformat() if req.started_at else None,
                    "completed_at": req.completed_at.isoformat() if req.completed_at else None,
                    "error": req.error,
                    "extra_data": req.extra_data,
                    "escrow_id": req.escrow_id,
                    "escrow_amount": str(req.escrow_amount) if req.escrow_amount is not None else None,
                }
            return None

    async def cancel_compute_request(self, request_id: str, owner_id: str | None = None) -> bool:
        """Cancel compute request.

        ``owner_id`` restricts the cancel to the caller's own requests;
        ``None`` means admin/unrestricted.
        """
        async with get_session() as session:
            query = select(ComputeRequest).where(ComputeRequest.request_id == request_id)
            if owner_id is not None:
                query = query.where(ComputeRequest.owner_id == owner_id)
            result = await session.execute(query)
            req = result.scalar_one_or_none()

            if req and req.status in ["queued", "running"]:
                req.status = "cancelled"
                req.completed_at = datetime.now(UTC)
                await session.commit()
                return True
            return False

    async def list_compute_requests(
        self,
        gpu_id: str | None = None,
        status: str | None = None,
        owner_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List compute requests, optionally filtered.

        ``owner_id`` restricts results to the caller's own requests;
        ``None`` means admin/unrestricted. ``limit`` bounds the read —
        the table only grows, so an unbounded select is a memory/IO
        hazard (#1642).
        """
        bounded = max(1, min(int(limit), 1000))
        async with get_session() as session:
            query = select(ComputeRequest).order_by(col(ComputeRequest.created_at).desc()).limit(bounded)

            if gpu_id:
                query = query.where(ComputeRequest.gpu_id == gpu_id)
            if status:
                query = query.where(ComputeRequest.status == status)
            if owner_id is not None:
                query = query.where(ComputeRequest.owner_id == owner_id)

            result = await session.execute(query)
            requests = result.scalars().all()

            return [
                {
                    "request_id": req.request_id,
                    "gpu_id": req.gpu_id,
                    "model_name": req.model_name,
                    "priority": req.priority,
                    "status": req.status,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                }
                for req in requests
            ]

    async def get_compute_result(self, request_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        """Get compute result.

        ``owner_id`` restricts the result to requests owned by that caller;
        ``None`` means admin/unrestricted. Ownership is checked on the parent
        ComputeRequest — ComputeResult carries no owner column.
        """
        async with get_session() as session:
            if owner_id is not None:
                req_check = await session.execute(
                    select(ComputeRequest.id).where(
                        ComputeRequest.request_id == request_id,
                        ComputeRequest.owner_id == owner_id,
                    )
                )
                if req_check.scalar_one_or_none() is None:
                    return None
            # Enforce the advertised cache TTL: expired results are ignored
            # (the worker stamps expires_at = created + cache_ttl). Rows
            # written before the aware-datetime fix carry naive UTC values;
            # the column is a naive DateTime storing UTC wall-clock, so the
            # aware bound param compares correctly on both sqlite and PG.
            result = await session.execute(
                select(ComputeResult)
                .where(
                    ComputeResult.request_id == request_id,
                    ComputeResult.expires_at > datetime.now(UTC),
                )
                # More than one fresh result can exist for a request (retries,
                # pre-#1685 rows); newest wins instead of MultipleResultsFound.
                .order_by(col(ComputeResult.created_at).desc())
                .limit(1)
            )
            res = result.scalar_one_or_none()

            if res:
                return {
                    "result_id": res.result_id,
                    "request_id": res.request_id,
                    "output_data": res.output_data,
                    "metrics": res.metrics,
                    "status": res.status,
                    "created_at": res.created_at.isoformat() if res.created_at else None,
                    "extra_data": res.extra_data,
                }
            return None
