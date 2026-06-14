"""Edge serve service for Edge API Service"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import select

from ..schemas.serve import ComputeRequest, ComputeResult
from ..storage import get_session


class ServeService:
    """Service for edge serve operations"""

    async def submit_compute_request(self, gpu_id: str, model_name: str, input_data: dict[str, Any], priority: str = "normal") -> dict[str, Any]:
        """Submit compute request"""
        async with get_session() as session:
            request_id = f"req_{uuid4().hex[:8]}"

            request = ComputeRequest(
                request_id=request_id,
                gpu_id=gpu_id,
                model_name=model_name,
                input_data=input_data,
                priority=priority,
                status="queued"
            )
            session.add(request)
            await session.commit()

            return {
                "success": True,
                "request_id": request_id,
                "status": "queued",
                "message": f"Compute request {request_id} submitted"
            }

    async def get_compute_request(self, request_id: str) -> dict[str, Any] | None:
        """Get compute request details"""
        async with get_session() as session:
            result = await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))
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
                    "extra_data": req.extra_data
                }
            return None

    async def cancel_compute_request(self, request_id: str) -> bool:
        """Cancel compute request"""
        async with get_session() as session:
            result = await session.execute(select(ComputeRequest).where(ComputeRequest.request_id == request_id))
            req = result.scalar_one_or_none()

            if req and req.status in ["queued", "running"]:
                req.status = "cancelled"
                req.completed_at = datetime.utcnow()
                await session.commit()
                return True
            return False

    async def list_compute_requests(self, gpu_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List compute requests, optionally filtered"""
        async with get_session() as session:
            query = select(ComputeRequest)

            if gpu_id:
                query = query.where(ComputeRequest.gpu_id == gpu_id)
            if status:
                query = query.where(ComputeRequest.status == status)

            result = await session.execute(query)
            requests = result.scalars().all()

            return [
                {
                    "request_id": req.request_id,
                    "gpu_id": req.gpu_id,
                    "model_name": req.model_name,
                    "priority": req.priority,
                    "status": req.status,
                    "created_at": req.created_at.isoformat() if req.created_at else None
                }
                for req in requests
            ]

    async def get_compute_result(self, request_id: str) -> dict[str, Any] | None:
        """Get compute result"""
        async with get_session() as session:
            result = await session.execute(select(ComputeResult).where(ComputeResult.request_id == request_id))
            res = result.scalar_one_or_none()

            if res:
                return {
                    "result_id": res.result_id,
                    "request_id": res.request_id,
                    "output_data": res.output_data,  # type: ignore[attr-defined]
                    "metrics": res.metrics,  # type: ignore[attr-defined]
                    "status": res.status,  # type: ignore[attr-defined]
                    "created_at": res.created_at.isoformat() if res.created_at else None,
                    "extra_data": res.extra_data  # type: ignore[attr-defined]
                }
            return None
