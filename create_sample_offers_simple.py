#!/usr/bin/env python3
"""Create sample marketplace offers for testing - simplified version"""

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
DATA_DIR = Path("/var/lib/aitbc/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/marketplace_service.db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_sample_offers():
    """Create sample marketplace offers"""
    async with async_session() as session:
        # Sample offers with public endpoints using nginx proxy paths
        hub_url = "hub.aitbc.bubuit.net"
        sample_offers = [
            {
                "plugin_id": "ollama-llama3-8b",
                "service_type": "ollama",
                "model": "llama3:8b",
                "price": 0.002,
                "price_unit": "per_1k_tokens",
                "offer_id": "gpu-offer-001",
                "endpoint": f"http://{hub_url}/ollama/",
                "public_endpoint": f"http://{hub_url}/ollama/",
                "health_url": f"http://{hub_url}/ollama/health",
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
                "rating_count": 12,
                "block_height": 5334,
                "block_hash": "0x09c1a89a1234567890abcdef6308e74d",
                "tx_hash": "0x418e5e041234567890abcdef3e35c234",
                "block_proposer": "ait1db52471234567890abcdef703efd4d",
                "block_timestamp": datetime.now(UTC)
            },
            {
                "plugin_id": "ollama-mistral-7b",
                "service_type": "ollama",
                "model": "mistral:7b",
                "price": 0.0015,
                "price_unit": "per_1k_tokens",
                "offer_id": "gpu-offer-001",
                "endpoint": f"http://{hub_url}/ollama/",
                "public_endpoint": f"http://{hub_url}/ollama/",
                "health_url": f"http://{hub_url}/ollama/health",
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
                "rating_count": 8,
                "block_height": 5335,
                "block_hash": "0x1a2b3c4d567890abcdef1234567890ef",
                "tx_hash": "0x987654321234567890abcdef123456ab",
                "block_proposer": "ait1xyz78901234567890abcdef123456cd",
                "block_timestamp": datetime.now(UTC)
            },
            {
                "plugin_id": "whisper-large-v3",
                "service_type": "whisper",
                "model": "large-v3",
                "price": 0.01,
                "price_unit": "per_audio_min",
                "offer_id": "gpu-offer-001",
                "endpoint": f"http://{hub_url}/whisper/",
                "public_endpoint": f"http://{hub_url}/whisper/",
                "health_url": f"http://{hub_url}/whisper/health",
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
                "rating_count": 15,
                "block_height": 5336,
                "block_hash": "0xdeadbeef1234567890abcdef12345678",
                "tx_hash": "0xcafe12341234567890abcdef12345678",
                "block_proposer": "ait1abc123456789012345678901234ef",
                "block_timestamp": datetime.now(UTC)
            },
            {
                "plugin_id": "ffmpeg-transcode-h264",
                "service_type": "ffmpeg",
                "model": "h264-transcode",
                "price": 0.005,
                "price_unit": "per_processing_hour",
                "offer_id": "gpu-offer-001",
                "endpoint": f"http://{hub_url}/ffmpeg/",
                "public_endpoint": f"http://{hub_url}/ffmpeg/",
                "health_url": f"http://{hub_url}/ffmpeg/health",
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
                "rating_count": 5,
                "block_height": 5337,
                "block_hash": "0xfeedface1234567890abcdef12345678",
                "tx_hash": "0xbabe12341234567890abcdef12345678",
                "block_proposer": "ait1def456789012345678901234567ab",
                "block_timestamp": datetime.now(UTC)
            },
            {
                "plugin_id": "peertube-pruner-v2",
                "service_type": "peertube_pruner",
                "model": "pruner-v2",
                "price": 0.003,
                "price_unit": "per_gb",
                "offer_id": "gpu-offer-001",
                "endpoint": f"http://{hub_url}/peertube-pruner/",
                "public_endpoint": f"http://{hub_url}/peertube-pruner/",
                "health_url": f"http://{hub_url}/peertube-pruner/health",
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
                "rating_count": 3,
                "block_height": 5338,
                "block_hash": "0x1234567890abcdef1234567890abcdef",
                "tx_hash": "0xfedcba091234567890abcdef12345678",
                "block_proposer": "ait1ghi789012345678901234567890cd",
                "block_timestamp": datetime.now(UTC)
            }
        ]

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Add offers directly
        for offer_data in sample_offers:
            offer = SoftwareService(**offer_data)
            session.add(offer)
            print(f"Adding offer: {offer_data['plugin_id']}")
        
        await session.commit()
        print(f"Created {len(sample_offers)} sample marketplace offers")

if __name__ == "__main__":
    asyncio.run(create_sample_offers())