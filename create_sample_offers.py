#!/usr/bin/env python3
"""Create sample marketplace offers for testing"""

import sys
import asyncio
from datetime import UTC, datetime
from pathlib import Path

# Add paths
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/marketplace")
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(SERVICE_DIR / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from marketplace_service.domain.marketplace import SoftwareService

# Database setup - use the same path as the marketplace service
DATA_DIR = Path("/opt/aitbc/data")
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/marketplace_service.db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_sample_offers():
    """Create sample marketplace offers"""
    async with async_session() as session:
        # Sample offers
        sample_offers = [
            {
                "plugin_id": "ollama-llama3-8b",
                "service_type": "ollama",
                "model": "llama3:8b",
                "price": 0.002,
                "price_unit": "per_1k_tokens",
                "offer_id": "gpu-offer-001",
                "endpoint": "http://aitbc3:11434",
                "public_endpoint": "http://aitbc3:11434",
                "health_url": "http://aitbc3:11434/health",
                "provider_address": "aitbc3-provider",
                "node_id": "aitbc3",
                "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
                "gpu_device": "0",
                "gpu_uuid": "GPU-abc123",
                "gpu_offer_id": "gpu-001",
                "description": "Llama3 8B model inference on RTX 4060 Ti with 16GB VRAM",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.5,
                "rating_count": 12
            },
            {
                "plugin_id": "ollama-mistral-7b",
                "service_type": "ollama",
                "model": "mistral:7b",
                "price": 0.0015,
                "price_unit": "per_1k_tokens",
                "offer_id": "gpu-offer-001",
                "endpoint": "http://aitbc3:11434",
                "public_endpoint": "http://aitbc3:11434",
                "health_url": "http://aitbc3:11434/health",
                "provider_address": "aitbc3-provider",
                "node_id": "aitbc3",
                "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
                "gpu_device": "0",
                "gpu_uuid": "GPU-abc123",
                "gpu_offer_id": "gpu-001",
                "description": "Mistral 7B model for fast inference with good quality",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.2,
                "rating_count": 8
            },
            {
                "plugin_id": "whisper-large-v3",
                "service_type": "whisper",
                "model": "large-v3",
                "price": 0.01,
                "price_unit": "per_audio_min",
                "offer_id": "gpu-offer-001",
                "endpoint": "http://aitbc3:8080",
                "public_endpoint": "http://aitbc3:8080",
                "health_url": "http://aitbc3:8080/health",
                "provider_address": "aitbc3-provider",
                "node_id": "aitbc3",
                "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
                "gpu_device": "0",
                "gpu_uuid": "GPU-abc123",
                "gpu_offer_id": "gpu-001",
                "description": "High-accuracy speech recognition using Whisper Large v3",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.8,
                "rating_count": 15
            },
            {
                "plugin_id": "ffmpeg-transcode-h264",
                "service_type": "ffmpeg",
                "model": "h264-transcode",
                "price": 0.005,
                "price_unit": "per_processing_hour",
                "offer_id": "gpu-offer-001",
                "endpoint": "http://aitbc3:9000",
                "public_endpoint": "http://aitbc3:9000",
                "health_url": "http://aitbc3:9000/health",
                "provider_address": "aitbc3-provider",
                "node_id": "aitbc3",
                "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
                "gpu_device": "0",
                "gpu_uuid": "GPU-abc123",
                "gpu_offer_id": "gpu-001",
                "description": "Hardware-accelerated H.264 video transcoding using NVENC",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.0,
                "rating_count": 5
            },
            {
                "plugin_id": "peertube-pruner-v2",
                "service_type": "peertube_pruner",
                "model": "pruner-v2",
                "price": 0.003,
                "price_unit": "per_gb",
                "offer_id": "gpu-offer-001",
                "endpoint": "http://aitbc3:9500",
                "public_endpoint": "http://aitbc3:9500",
                "health_url": "http://aitbc3:9500/health",
                "provider_address": "aitbc3-provider",
                "node_id": "aitbc3",
                "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
                "gpu_device": "0",
                "gpu_uuid": "GPU-abc123",
                "gpu_offer_id": "gpu-001",
                "description": "PeerTube video pruning and optimization service",
                "status": "inactive",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 3.5,
                "rating_count": 3
            }
        ]

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Add offers
        for offer_data in sample_offers:
            offer = SoftwareService(**offer_data)
            session.add(offer)
        
        await session.commit()
        print(f"Created {len(sample_offers)} sample marketplace offers")

if __name__ == "__main__":
    asyncio.run(create_sample_offers())