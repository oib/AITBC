from __future__ import annotations

from fastapi import APIRouter, Response

from ..prometheus import render_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Prometheus metrics")
async def metrics_endpoint() -> Response:
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
