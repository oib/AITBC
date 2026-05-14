"""GPU service client for Edge API Service"""

import httpx
from typing import Dict, List

from ..config import settings


class GPUServiceClient:
    """Client for GPU service communication"""
    
    def __init__(self):
        self.base_url = f"http://{settings.gpu_service_host}:{settings.gpu_service_port}"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def scan_gpus(self, miner_id: str) -> Dict:
        """Scan GPUs via GPU service - TODO: Implement in Phase 3"""
        # TODO: Call GPU service endpoint /v1/marketplace/edge-gpu/scan/{miner_id}
        return {"message": "scan_gpus via GPU service - to be implemented in Phase 3"}
    
    async def get_gpu_profiles(self) -> List[Dict]:
        """Get GPU profiles via GPU service - TODO: Implement in Phase 3"""
        # TODO: Call GPU service endpoint /v1/marketplace/edge-gpu/profiles
        return [{"message": "get_gpu_profiles via GPU service - to be implemented in Phase 3"}]
    
    async def get_gpu_metrics(self, gpu_id: str) -> Dict:
        """Get GPU metrics via GPU service - TODO: Implement in Phase 3"""
        # TODO: Call GPU service endpoint /v1/marketplace/edge-gpu/metrics/{gpu_id}
        return {"message": "get_gpu_metrics via GPU service - to be implemented in Phase 3"}
