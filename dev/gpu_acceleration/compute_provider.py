"""
GPU Compute Provider Abstract Interface

This module defines the abstract interface for GPU compute providers,
allowing different backends (CUDA, ROCm, Apple Silicon, CPU) to be
swapped seamlessly without changing business logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np


class ComputeBackend(Enum):
    """Available compute backends"""
    CUDA = "cuda"
    ROCM = "rocm"
    APPLE_SILICON = "apple_silicon"
    CPU = "cpu"
    OPENCL = "opencl"


@dataclass
class ComputeDevice:
    """Information about a compute device"""
    device_id: int
    name: str
    backend: ComputeBackend
    memory_total: int  # in bytes
    memory_available: int  # in bytes
    compute_capability: Optional[str] = None
    is_available: bool = True
    temperature: Optional[float] = None  # in Celsius
    utilization: Optional[float] = None  # percentage


@dataclass
class ComputeTask:
    """A compute task to be executed"""
    task_id: str
    operation: str
    data: Any
    parameters: Dict[str, Any]
    priority: int = 0
    timeout: Optional[float] = None


@dataclass
class ComputeResult:
    """Result of a compute task"""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    memory_used: int = 0  # in bytes


class ComputeProvider(ABC):
    """
    Abstract base class for GPU compute providers.
    
    This interface defines the contract that all GPU compute providers
    must implement, allowing for seamless backend swapping.
    """
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the compute provider.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the compute provider and clean up resources."""
        pass
    
    @abstractmethod
    def get_available_devices(self) -> List[ComputeDevice]:
        """
        Get list of available compute devices.
        
        Returns:
            List[ComputeDevice]: Available compute devices
        """
        pass
    
    @abstractmethod
    def get_device_count(self) -> int:
        """
        Get the number of available devices.
        
        Returns:
            int: Number of available devices
        """
        pass
    
    @abstractmethod
    def set_device(self, device_id: int) -> bool:
        """
        Set the active compute device.
        
        Args:
            device_id: ID of the device to set as active
            
        Returns:
            bool: True if device set successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def get_device_info(self, device_id: int) -> Optional[ComputeDevice]:
        """
        Get information about a specific device.
        
        Args:
            device_id: ID of the device
            
        Returns:
            Optional[ComputeDevice]: Device information or None if not found
        """
        pass
    
    @abstractmethod
    def allocate_memory(self, size: int, device_id: Optional[int] = None) -> Any:
        """
        Allocate memory on the compute device.
        
        Args:
            size: Size of memory to allocate in bytes
            device_id: Device ID (None for current device)
            
        Returns:
            Any: Memory handle or pointer
        """
        pass
    
    @abstractmethod
    def free_memory(self, memory_handle: Any) -> None:
        """
        Free allocated memory.
        
        Args:
            memory_handle: Memory handle to free
        """
        pass
    
    @abstractmethod
    def copy_to_device(self, host_data: Any, device_data: Any) -> None:
        """
        Copy data from host to device.
        
        Args:
            host_data: Host data to copy
            device_data: Device memory destination
        """
        pass
    
    @abstractmethod
    def copy_to_host(self, device_data: Any, host_data: Any) -> None:
        """
        Copy data from device to host.
        
        Args:
            device_data: Device data to copy
            host_data: Host memory destination
        """
        pass
    
    @abstractmethod
    def execute_kernel(
        self,
        kernel_name: str,
        grid_size: Tuple[int, int, int],
        block_size: Tuple[int, int, int],
        args: List[Any],
        shared_memory: int = 0
    ) -> bool:
        """
        Execute a compute kernel.
        
        Args:
            kernel_name: Name of the kernel to execute
            grid_size: Grid dimensions (x, y, z)
            block_size: Block dimensions (x, y, z)
            args: Kernel arguments
            shared_memory: Shared memory size in bytes
            
        Returns:
            bool: True if execution successful, False otherwise
        """
        pass
    
    @abstractmethod
    def synchronize(self) -> None:
        """Synchronize device operations."""
        pass
    
    @abstractmethod
    def get_memory_info(self, device_id: Optional[int] = None) -> Tuple[int, int]:
        """
        Get memory information for a device.
        
        Args:
            device_id: Device ID (None for current device)
            
        Returns:
            Tuple[int, int]: (free_memory, total_memory) in bytes
        """
        pass
    
    @abstractmethod
    def get_utilization(self, device_id: Optional[int] = None) -> float:
        """
        Get device utilization percentage.
        
        Args:
            device_id: Device ID (None for current device)
            
        Returns:
            float: Utilization percentage (0-100)
        """
        pass
    
    @abstractmethod
    def get_temperature(self, device_id: Optional[int] = None) -> Optional[float]:
        """
        Get device temperature.
        
        Args:
            device_id: Device ID (None for current device)
            
        Returns:
            Optional[float]: Temperature in Celsius or None if unavailable
        """
        pass
    
    # ZK-specific operations (can be implemented by specialized providers)
    
    @abstractmethod
    def zk_field_add(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """
        Perform field addition for ZK operations.
        
        Args:
            a: First operand
            b: Second operand
            result: Result array
            
        Returns:
            bool: True if operation successful
        """
        pass
    
    @abstractmethod
    def zk_field_mul(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """
        Perform field multiplication for ZK operations.
        
        Args:
            a: First operand
            b: Second operand
            result: Result array
            
        Returns:
            bool: True if operation successful
        """
        pass
    
    @abstractmethod
    def zk_field_inverse(self, a: np.ndarray, result: np.ndarray) -> bool:
        """
        Perform field inversion for ZK operations.
        
        Args:
            a: Operand to invert
            result: Result array
            
        Returns:
            bool: True if operation successful
        """
        pass
    
    @abstractmethod
    def zk_multi_scalar_mul(
        self,
        scalars: List[np.ndarray],
        points: List[np.ndarray],
        result: np.ndarray
    ) -> bool:
        """
        Perform multi-scalar multiplication for ZK operations.
        
        Args:
            scalars: List of scalar operands
            points: List of point operands
            result: Result array
            
        Returns:
            bool: True if operation successful
        """
        pass
    
    @abstractmethod
    def zk_pairing(self, p1: np.ndarray, p2: np.ndarray, result: np.ndarray) -> bool:
        """
        Perform pairing operation for ZK operations.
        
        Args:
            p1: First point
            p2: Second point
            result: Result array
            
        Returns:
            bool: True if operation successful
        """
        pass
    
    # Performance and monitoring
    
    @abstractmethod
    def benchmark_operation(self, operation: str, iterations: int = 100) -> Dict[str, float]:
        """
        Benchmark a specific operation.
        
        Args:
            operation: Operation name to benchmark
            iterations: Number of iterations to run
            
        Returns:
            Dict[str, float]: Performance metrics
        """
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for the provider.
        
        Returns:
            Dict[str, Any]: Performance metrics
        """
        pass


class ComputeProviderFactory:
    """Factory for creating compute providers."""
    
    _providers = {}
    
    @classmethod
    def register_provider(cls, backend: ComputeBackend, provider_class):
        """Register a compute provider class."""
        cls._providers[backend] = provider_class
    
    @classmethod
    def create_provider(cls, backend: ComputeBackend, **kwargs) -> ComputeProvider:
        """
        Create a compute provider instance.
        
        Args:
            backend: The compute backend to create
            **kwargs: Additional arguments for provider initialization
            
        Returns:
            ComputeProvider: The created provider instance
            
        Raises:
            ValueError: If backend is not supported
        """
        if backend not in cls._providers:
            raise ValueError(f"Unsupported compute backend: {backend}")
        
        provider_class = cls._providers[backend]
        return provider_class(**kwargs)
    
    @classmethod
    def get_available_backends(cls) -> List[ComputeBackend]:
        """Get list of available backends."""
        return list(cls._providers.keys())
    
    @classmethod
    def auto_detect_backend(cls) -> ComputeBackend:
        """
        Auto-detect the best available backend.
        
        Returns:
            ComputeBackend: The detected backend
        """
        # Try backends in order of preference
        preference_order = [
            ComputeBackend.CUDA,
            ComputeBackend.ROCM,
            ComputeBackend.APPLE_SILICON,
            ComputeBackend.OPENCL,
            ComputeBackend.CPU
        ]
        
        for backend in preference_order:
            if backend in cls._providers:
                try:
                    provider = cls.create_provider(backend)
                    if provider.initialize():
                        provider.shutdown()
                        return backend
                except Exception:
                    continue
        
        # Fallback to CPU
        return ComputeBackend.CPU


class ComputeManager:
    """High-level manager for compute operations."""
    
    def __init__(self, backend: Optional[ComputeBackend] = None):
        """
        Initialize the compute manager.
        
        Args:
            backend: Specific backend to use, or None for auto-detection
        """
        self.backend = backend or ComputeProviderFactory.auto_detect_backend()
        self.provider = ComputeProviderFactory.create_provider(self.backend)
        self.initialized = False
        
    def initialize(self) -> bool:
        """Initialize the compute manager."""
        try:
            self.initialized = self.provider.initialize()
            if self.initialized:
                print(f"✅ Compute Manager initialized with {self.backend.value} backend")
            else:
                print(f"❌ Failed to initialize {self.backend.value} backend")
            return self.initialized
        except Exception as e:
            print(f"❌ Compute Manager initialization failed: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown the compute manager."""
        if self.initialized:
            self.provider.shutdown()
            self.initialized = False
            print(f"🔄 Compute Manager shutdown ({self.backend.value})")
    
    def get_provider(self) -> ComputeProvider:
        """Get the underlying compute provider."""
        return self.provider
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend."""
        return {
            "backend": self.backend.value,
            "initialized": self.initialized,
            "device_count": self.provider.get_device_count() if self.initialized else 0,
            "available_devices": [
                device.name for device in self.provider.get_available_devices()
            ] if self.initialized else []
        }
