#!/usr/bin/env python3
"""Create sample marketplace offers for testing (MOCK DATA - NOT ON BLOCKCHAIN)"""

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
from sqlalchemy import select
from sqlmodel import SQLModel

from marketplace_service.domain.marketplace import SoftwareService

# Database setup - use the same path as the marketplace service
DATA_DIR = Path("/opt/aitbc/data/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/marketplace_service.db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_sample_offers():
    """Create sample marketplace offers (MOCK DATA - NOT ON BLOCKCHAIN)"""
    async with async_session() as session:
        # Sample offers with public endpoints using nginx proxy paths
        # Using proxy paths for customer accessibility through standard HTTP
        # NOTE: These are MOCK offers for testing - they are NOT on the blockchain
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
                "description": "Llama3 8B model inference on RTX 4060 Ti with 16GB VRAM (MOCK DATA)",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.5,
                "rating_count": 12
                # Note: Blockchain verification fields are added by marketplace service
                # when querying blockchain data, not stored in local database
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
                "description": "Mistral 7B model for fast inference with good quality (MOCK DATA)",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.2,
                "rating_count": 8
                # Note: Blockchain verification fields are added by marketplace service
                # when querying blockchain data, not stored in local database
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
                "description": "High-accuracy speech recognition using Whisper Large v3 (MOCK DATA)",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.8,
                "rating_count": 15
                # Note: Blockchain verification fields are added by marketplace service
                # when querying blockchain data, not stored in local database
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
                "description": "Hardware-accelerated H.264 video transcoding using NVENC (MOCK DATA)",
                "status": "active",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 4.0,
                "rating_count": 5
                # Note: Blockchain verification fields are added by marketplace service
                # when querying blockchain data, not stored in local database
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
                "description": "PeerTube video pruning and optimization service (MOCK DATA)",
                "status": "inactive",
                "registered_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "avg_rating": 3.5,
                "rating_count": 3
                # Note: Blockchain verification fields are added by marketplace service
                # when querying blockchain data, not stored in local database
            }
        ]

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Add or update offers
        for offer_data in sample_offers:
            plugin_id = offer_data["plugin_id"]
            # Check if offer exists
            from sqlalchemy import select
            result = await session.execute(
                select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
            )
            existing_offer = result.scalar_one_or_none()
            
            if existing_offer:
                # Update existing offer
                for key, value in offer_data.items():
                    setattr(existing_offer, key, value)
                print(f"Updated existing offer: {plugin_id}")
            else:
                # Create new offer
                offer = SoftwareService(**offer_data)
                session.add(offer)
                print(f"Created new offer: {plugin_id}")
        
        await session.commit()
        print(f"Processed {len(sample_offers)} marketplace offers (MOCK DATA - NOT ON BLOCKCHAIN)")
        print("⚠️  WARNING: These are mock offers for testing only - they are NOT confirmed on the blockchain")
        print("⚠️  For real marketplace functionality, offers should be submitted via blockchain transactions")

if __name__ == "__main__":
    asyncio.run(create_sample_offers())