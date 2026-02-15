#!/usr/bin/env python3
"""
Web Vitals API endpoint for collecting performance metrics
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

router = APIRouter()

class WebVitalsEntry(BaseModel):
    name: str
    startTime: Optional[float] = None
    duration: Optional[float] = None

class WebVitalsMetric(BaseModel):
    name: str
    value: float
    id: str
    delta: Optional[float] = None
    entries: List[WebVitalsEntry] = []
    url: Optional[str] = None
    timestamp: Optional[str] = None

@router.post("/web-vitals")
async def collect_web_vitals(metric: WebVitalsMetric):
    """
    Collect Web Vitals performance metrics from the frontend.
    This endpoint receives Core Web Vitals (LCP, FID, CLS, TTFB, FCP) for monitoring.
    """
    try:
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
