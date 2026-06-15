#!/usr/bin/env python3
"""
Web Vitals API endpoint for collecting performance metrics
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)

router = APIRouter()


class WebVitalsEntry(BaseModel):
    name: str
    startTime: float | None = None
    duration: float | None = None
    value: float | None = None
    hadRecentInput: bool | None = None


class WebVitalsMetric(BaseModel):
    name: str
    value: float
    id: str
    delta: float | None = None
    entries: list[WebVitalsEntry] = []
    url: str | None = None
    timestamp: str | None = None


@router.post("/web-vitals")
@rate_limit(rate=100, per=60)
async def collect_web_vitals(request: Request, metric: WebVitalsMetric) -> dict[str, Any]:
    """
    Collect Web Vitals performance metrics from the frontend.
    This endpoint receives Core Web Vitals (LCP, FID, CLS, TTFB, FCP) for monitoring.
    """
    try:
        # Filter entries to only include supported fields
        filtered_entries = []
        for entry in metric.entries:
            filtered_entry = {
                "name": entry.name,
                "startTime": entry.startTime,
                "duration": entry.duration,
                "value": entry.value,
                "hadRecentInput": entry.hadRecentInput,
            }
            # Remove None values
            filtered_entry = {k: v for k, v in filtered_entry.items() if v is not None}
            filtered_entries.append(filtered_entry)

        # Log the metric for monitoring/analysis
        logger.info(  # type: ignore[call-arg]
            "Web Vitals metric received",
            metric_name=metric.name,
            metric_value=metric.value,
            metric_id=metric.id,
            url=metric.url or "unknown",
        )

        # In a production setup, you might:
        # - Store in database for trend analysis
        # - Send to monitoring service (DataDog, New Relic, etc.)
        # - Trigger alerts for poor performance

        # For now, just acknowledge receipt
        return {"status": "received", "metric": metric.name, "value": metric.value}

    except (ValueError, AttributeError, KeyError) as e:
        logger.error("Error processing web vitals metric", error=str(e))  # type: ignore[call-arg]
        raise HTTPException(status_code=500, detail="Failed to process metric") from e


# Health check for web vitals endpoint
@router.get("/web-vitals/health")
@rate_limit(rate=1000, per=60)
async def web_vitals_health(request: Request) -> dict[str, str]:
    """Health check for web vitals collection endpoint"""
    return {"status": "healthy", "service": "web-vitals"}
