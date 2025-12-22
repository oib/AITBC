"""
Service runner for executing GPU service jobs via plugins
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from .base import BaseRunner
from ...config import settings
from ...logging import get_logger

# Add plugins directory to path
plugins_path = Path(__file__).parent.parent.parent.parent / "plugins"
sys.path.insert(0, str(plugins_path))

try:
    from plugins.discovery import ServiceDiscovery
except ImportError:
    ServiceDiscovery = None

logger = get_logger(__name__)


class ServiceRunner(BaseRunner):
    """Runner for GPU service jobs using the plugin system"""
    
    def __init__(self):
        super().__init__()
        self.discovery: Optional[ServiceDiscovery] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the service discovery system"""
        if self._initialized:
            return
        
        if ServiceDiscovery is None:
            raise ImportError("ServiceDiscovery not available. Check plugin installation.")
        
        # Create service discovery
        pool_hub_url = getattr(settings, 'pool_hub_url', 'http://localhost:8001')
        miner_id = getattr(settings, 'node_id', 'miner-1')
        
        self.discovery = ServiceDiscovery(pool_hub_url, miner_id)
        await self.discovery.start()
        self._initialized = True
        
        logger.info("Service runner initialized")
    
    async def run(self, job: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
        """Execute a service job"""
        await self.initialize()
        
        job_id = job.get("job_id", "unknown")
        
        try:
            # Extract service type and parameters
            service_type = job.get("service_type")
            if not service_type:
                raise ValueError("Job missing service_type")
            
            # Get service parameters from job
            service_params = job.get("parameters", {})
            
            logger.info(f"Executing service job", extra={
                "job_id": job_id,
                "service_type": service_type
            })
            
            # Execute via plugin system
            result = await self.discovery.execute_service(service_type, service_params)
            
            # Save result to workspace
            result_file = workspace / "result.json"
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2)
            
            if result["success"]:
                logger.info(f"Service job completed successfully", extra={
                    "job_id": job_id,
                    "execution_time": result.get("execution_time")
                })
                
                # Return success result
                return {
                    "status": "completed",
                    "result": result["data"],
                    "metrics": result.get("metrics", {}),
                    "execution_time": result.get("execution_time")
                }
            else:
                logger.error(f"Service job failed", extra={
                    "job_id": job_id,
                    "error": result.get("error")
                })
                
                # Return failure result
                return {
                    "status": "failed",
                    "error": result.get("error", "Unknown error"),
                    "execution_time": result.get("execution_time")
                }
                
        except Exception as e:
            logger.exception("Service runner failed", extra={"job_id": job_id})
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        if self.discovery:
            await self.discovery.stop()
        self._initialized = False
