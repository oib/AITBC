"""
Edge GPU service for managing GPU operations
"""

import subprocess
from typing import Any

from sqlmodel import Session, select

from aitbc import get_logger

from ..domain.gpu_marketplace import ConsumerGPUProfile, EdgeGPUMetrics, GPUArchitecture, GPURegistry

logger = get_logger(__name__)


class EdgeGPUService:
    def __init__(self, session: Session):
        self.session = session

    async def list_profiles(
        self, architecture: GPUArchitecture | None = None, edge_optimized: bool | None = None, min_memory_gb: int | None = None
    ) -> list[ConsumerGPUProfile]:
        """List consumer GPU profiles with optional filters"""
        try:
            await self.seed_profiles()
            stmt = select(ConsumerGPUProfile)
            if architecture:
                stmt = stmt.where(ConsumerGPUProfile.architecture == architecture)
            if edge_optimized is not None:
                stmt = stmt.where(ConsumerGPUProfile.edge_optimized == edge_optimized)
            if min_memory_gb is not None:
                stmt = stmt.where(ConsumerGPUProfile.memory_gb >= min_memory_gb)
            result = self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error("Failed to list GPU profiles: %s", e)
            return []

    async def list_metrics(self, gpu_id: str, limit: int = 100) -> list[EdgeGPUMetrics]:
        """List edge GPU metrics for a specific GPU"""
        try:
            stmt = (
                select(EdgeGPUMetrics)
                .where(EdgeGPUMetrics.gpu_id == gpu_id)
                .order_by(EdgeGPUMetrics.timestamp.desc())
                .limit(limit)
            )
            result = self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error("Failed to list GPU metrics for %s: %s", gpu_id, e)
            return []

    def create_metric(self, payload: dict[str, Any]) -> EdgeGPUMetrics:
        metric = EdgeGPUMetrics(**payload)
        self.session.add(metric)
        self.session.commit()
        self.session.refresh(metric)
        return metric

    async def seed_profiles(self) -> None:
        """Seed consumer GPU profiles into database"""
        try:
            result = self.session.execute(select(ConsumerGPUProfile.gpu_model))
            existing_models = {row[0] for row in result.all()}
            created = 0
            for profile in CONSUMER_GPU_PROFILES.values():
                if profile["gpu_model"] in existing_models:
                    continue
                self.session.add(ConsumerGPUProfile(**profile))
                created += 1
            if created:
                self.session.commit()
        except Exception as e:
            self.session.rollback()
            logger.warning("Failed to seed GPU profiles: %s", e)

    def _discover_gpus_via_nvidia_smi(self) -> list[dict[str, Any]]:
        """Discover GPUs using nvidia-smi command"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("nvidia-smi failed: %s", result.stderr)
                return []
            gpus = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append(
                        {
                            "index": int(parts[0]),
                            "name": parts[1],
                            "memory_mb": int(parts[2]),
                            "driver_version": parts[3] if len(parts) > 3 else "unknown",
                        }
                    )
            return gpus
        except FileNotFoundError:
            logger.warning("nvidia-smi not found - GPU discovery skipped")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timeout - GPU discovery skipped")
            return []
        except Exception as e:
            logger.error("Error running nvidia-smi: %s", e)
            return []

    async def discover_and_register_edge_gpus(self, miner_id: str) -> dict[str, Any]:
        """Scan and register edge GPUs for a miner"""
        try:
            discovered_gpus = self._discover_gpus_via_nvidia_smi()
            if not discovered_gpus:
                logger.info("No GPUs discovered via nvidia-smi for miner %s", miner_id)
                stmt = select(GPURegistry).where(GPURegistry.miner_id == miner_id)
                result = self.session.execute(stmt)
                existing_gpus = result.scalars().all()
                gpu_list = [
                    {
                        "id": gpu.id,
                        "model": gpu.model,
                        "memory_gb": gpu.memory_gb,
                        "region": gpu.region,
                        "status": gpu.status,
                        "capabilities": gpu.capabilities,
                    }
                    for gpu in existing_gpus
                ]
                return {
                    "miner_id": miner_id,
                    "gpus": gpu_list,
                    "registered": len(existing_gpus),
                    "edge_optimized": 0,
                    "discovery_method": "database_fallback",
                }
            registered_count = 0
            gpu_list = []
            for gpu_info in discovered_gpus:
                gpu_id = f"gpu_{miner_id}_{gpu_info['index']}"
                stmt = select(GPURegistry).where(GPURegistry.id == gpu_id)
                result = self.session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    existing.model = gpu_info["name"]
                    existing.memory_gb = gpu_info["memory_mb"] // 1024
                    existing.cuda_version = gpu_info["driver_version"]
                    existing.status = "available"
                    gpu_list.append(
                        {
                            "id": existing.id,
                            "model": existing.model,
                            "memory_gb": existing.memory_gb,
                            "region": existing.region,
                            "status": existing.status,
                            "capabilities": existing.capabilities,
                        }
                    )
                else:
                    new_gpu = GPURegistry(
                        id=gpu_id,
                        miner_id=miner_id,
                        model=gpu_info["name"],
                        memory_gb=gpu_info["memory_mb"] // 1024,
                        cuda_version=gpu_info["driver_version"],
                        status="available",
                        capabilities=["edge", "inference"],
                    )
                    self.session.add(new_gpu)
                    gpu_list.append(
                        {
                            "id": new_gpu.id,
                            "model": new_gpu.model,
                            "memory_gb": new_gpu.memory_gb,
                            "region": new_gpu.region,
                            "status": new_gpu.status,
                            "capabilities": new_gpu.capabilities,
                        }
                    )
                    registered_count += 1
            self.session.commit()
            return {
                "miner_id": miner_id,
                "gpus": gpu_list,
                "registered": registered_count,
                "edge_optimized": len(gpu_list),
                "discovery_method": "nvidia_smi",
            }
        except Exception as e:
            self.session.rollback()
            logger.error("Failed to discover GPUs for miner %s: %s", miner_id, e)
            return {"miner_id": miner_id, "gpus": [], "registered": 0, "edge_optimized": 0, "error": str(e)}

    async def optimize_inference_for_edge(self, gpu_id: str, model_name: str, request_data: dict[str, Any]) -> dict[str, Any]:
        """Optimize ML inference request for edge GPU"""
        return {"gpu_id": gpu_id, "model_name": model_name, "optimized": True, "latency_reduction": 0.0}
