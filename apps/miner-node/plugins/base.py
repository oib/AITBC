"""
Base plugin interface for GPU service execution
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import asyncio


@dataclass
class PluginResult:
    """Result from plugin execution"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None


class ServicePlugin(ABC):
    """Base class for all service plugins"""
    
    def __init__(self):
        self.service_id = None
        self.name = None
        self.version = "1.0.0"
        self.description = ""
        self.capabilities = []
    
    @abstractmethod
    async def execute(self, request: Dict[str, Any]) -> PluginResult:
        """Execute the service with given parameters"""
        pass
    
    @abstractmethod
    def validate_request(self, request: Dict[str, Any]) -> List[str]:
        """Validate request parameters, return list of errors"""
        pass
    
    @abstractmethod
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Get hardware requirements for this plugin"""
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get plugin-specific metrics"""
        return {
            "service_id": self.service_id,
            "name": self.name,
            "version": self.version
        }
    
    async def health_check(self) -> bool:
        """Check if plugin dependencies are available"""
        return True
    
    def setup(self) -> None:
        """Initialize plugin resources"""
        pass
    
    def cleanup(self) -> None:
        """Cleanup plugin resources"""
        pass


class GPUPlugin(ServicePlugin):
    """Base class for GPU-accelerated plugins"""
    
    def __init__(self):
        super().__init__()
        self.gpu_available = False
        self.vram_gb = 0
        self.cuda_available = False
    
    def setup(self) -> None:
        """Check GPU availability"""
        self._detect_gpu()
    
    def _detect_gpu(self) -> None:
        """Detect GPU and VRAM"""
        try:
            import torch
            if torch.cuda.is_available():
                self.gpu_available = True
                self.cuda_available = True
                self.vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        except ImportError:
            pass
        
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                self.gpu_available = True
                self.vram_gb = gpus[0].memoryTotal / 1024
        except ImportError:
            pass
    
    def get_hardware_requirements(self) -> Dict[str, Any]:
        """Default GPU requirements"""
        return {
            "gpu": "any",
            "vram_gb": 4,
            "cuda": "recommended"
        }
    
    async def health_check(self) -> bool:
        """Check GPU health"""
        return self.gpu_available
