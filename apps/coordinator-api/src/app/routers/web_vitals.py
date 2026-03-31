#!/usr/bin/env python3
"""
Web Vitals API endpoint for collecting performance metrics
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
async def collect_web_vitals(metric: WebVitalsMetric):
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
        logging.info(f"Web Vitals - {metric.name}: {metric.value}ms (ID: {metric.id}) from {metric.url or 'unknown'}")

        # In a production setup, you might:
        # - Store in database for trend analysis
        # - Send to monitoring service (DataDog, New Relic, etc.)
        # - Trigger alerts for poor performance

        # For now, just acknowledge receipt
        return {"status": "received", "metric": metric.name, "value": metric.value}

    except Exception as e:
        logging.error(f"Error processing web vitals metric: {e}")
        raise HTTPException(status_code=500, detail="Failed to process metric")


# Health check for web vitals endpoint
@router.get("/web-vitals/health")
async def web_vitals_health():
    """Health check for web vitals collection endpoint"""
    return {"status": "healthy", "service": "web-vitals"}
