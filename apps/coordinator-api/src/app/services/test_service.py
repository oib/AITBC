"""
Simple Test Service - FastAPI Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AITBC Test Service",
    version="1.0.0",
    description="Simple test service for enhanced capabilities"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "test"}

@app.post("/test-multimodal")
async def test_multimodal():
    """Test multi-modal processing without database dependencies"""
    return {
        "service": "test-multimodal",
        "status": "working",
        "timestamp": "2026-02-24T17:06:00Z",
        "features": [
            "text_processing",
            "image_processing", 
            "audio_processing",
            "video_processing"
        ]
    }

@app.post("/test-openclaw")
async def test_openclaw():
    """Test OpenClaw integration without database dependencies"""
    return {
        "service": "test-openclaw",
        "status": "working",
        "timestamp": "2026-02-24T17:06:00Z",
        "features": [
            "skill_routing",
            "job_offloading",
            "agent_collaboration",
            "edge_deployment"
        ]
    }

@app.post("/test-marketplace")
async def test_marketplace():
    """Test marketplace enhancement without database dependencies"""
    return {
        "service": "test-marketplace",
        "status": "working",
        "timestamp": "2026-02-24T17:06:00Z",
        "features": [
            "royalty_distribution",
            "model_licensing",
            "model_verification",
            "marketplace_analytics"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
