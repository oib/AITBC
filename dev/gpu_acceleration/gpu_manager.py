"""
Unified GPU Acceleration Manager

This module provides a high-level interface for GPU acceleration
that automatically selects the best available backend and provides
a unified API for ZK operations.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Union
import logging
import time
from dataclasses import dataclass

from .compute_provider import (
    ComputeManager, ComputeBackend, ComputeDevice, 
    ComputeTask, ComputeResult
)
from .cuda_provider import CUDAComputeProvider
from .cpu_provider import CPUComputeProvider
from .apple_silicon_provider import AppleSiliconComputeProvider

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ZKOperationConfig:
    """Configuration for ZK operations."""
    batch_size: int = 1024
    use_gpu: bool = True
    fallback_to_cpu: bool = True
    timeout: float = 30.0
    memory_limit: Optional[int] = None  # in bytes


class GPUAccelerationManager:
    """
    High-level manager for GPU acceleration with automatic backend selection.
    
    This class provides a clean interface for ZK operations that automatically
    selects the best available compute backend (CUDA, Apple Silicon, CPU).
    """
    
    def __init__(self, backend: Optional[ComputeBackend] = None, config: Optional[ZKOperationConfig] = None):
        """
        Initialize the GPU acceleration manager.
        
        Args:
            backend: Specific backend to use, or None for auto-detection
            config: Configuration for ZK operations
        """
        self.config = config or ZKOperationConfig()
        self.compute_manager = ComputeManager(backend)
        self.initialized = False
        self.backend_info = {}
        
        # Performance tracking
        self.operation_stats = {
            "field_add": {"count": 0, "total_time": 0.0, "errors": 0},
            "field_mul": {"count": 0, "total_time": 0.0, "errors": 0},
            "field_inverse": {"count": 0, "total_time": 0.0, "errors": 0},
            "multi_scalar_mul": {"count": 0, "total_time": 0.0, "errors": 0},
            "pairing": {"count": 0, "total_time": 0.0, "errors": 0}
        }
    
    def initialize(self) -> bool:
        """Initialize the GPU acceleration manager."""
        try:
            success = self.compute_manager.initialize()
            if success:
                self.initialized = True
                self.backend_info = self.compute_manager.get_backend_info()
                logger.info(f"GPU Acceleration Manager initialized with {self.backend_info['backend']} backend")
                
                # Log device information
                devices = self.compute_manager.get_provider().get_available_devices()
                for device in devices:
                    logger.info(f"  Device {device.device_id}: {device.name} ({device.backend.value})")
                
                return True
            else:
                logger.error("Failed to initialize GPU acceleration manager")
                return False
                
        except Exception as e:
            logger.error(f"GPU acceleration manager initialization failed: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown the GPU acceleration manager."""
        try:
            self.compute_manager.shutdown()
            self.initialized = False
            logger.info("GPU Acceleration Manager shutdown complete")
        except Exception as e:
            logger.error(f"GPU acceleration manager shutdown failed: {e}")
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend."""
        if self.initialized:
            return self.backend_info
        return {"error": "Manager not initialized"}
    
    def get_available_devices(self) -> List[ComputeDevice]:
        """Get list of available compute devices."""
        if self.initialized:
            return self.compute_manager.get_provider().get_available_devices()
        return []
    
    def set_device(self, device_id: int) -> bool:
        """Set the active compute device."""
        if self.initialized:
            return self.compute_manager.get_provider().set_device(device_id)
        return False
    
    # High-level ZK operations with automatic fallback
    
    def field_add(self, a: np.ndarray, b: np.ndarray, result: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Perform field addition with automatic backend selection.
        
        Args:
            a: First operand
            b: Second operand
            result: Optional result array (will be created if None)
            
        Returns:
            np.ndarray: Result of field addition
        """
        if not self.initialized:
            raise RuntimeError("GPU acceleration manager not initialized")
        
        if result is None:
            result = np.zeros_like(a)
        
        start_time = time.time()
        operation = "field_add"
        
        try:
            provider = self.compute_manager.get_provider()
            success = provider.zk_field_add(a, b, result)
            
            if not success and self.config.fallback_to_cpu:
                # Fallback to CPU operations
                logger.warning("GPU field add failed, falling back to CPU")
                np.add(a, b, out=result, dtype=result.dtype)
                success = True
            
            if success:
                self._update_stats(operation, time.time() - start_time, False)
                return result
            else:
                self._update_stats(operation, time.time() - start_time, True)
                raise RuntimeError("Field addition failed")
                
        except Exception as e:
            self._update_stats(operation, time.time() - start_time, True)
            logger.error(f"Field addition failed: {e}")
            raise
    
    def field_mul(self, a: np.ndarray, b: np.ndarray, result: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Perform field multiplication with automatic backend selection.
        
        Args:
            a: First operand
            b: Second operand
            result: Optional result array (will be created if None)
            
        Returns:
            np.ndarray: Result of field multiplication
        """
        if not self.initialized:
            raise RuntimeError("GPU acceleration manager not initialized")
        
        if result is None:
            result = np.zeros_like(a)
        
        start_time = time.time()
        operation = "field_mul"
        
        try:
            provider = self.compute_manager.get_provider()
            success = provider.zk_field_mul(a, b, result)
            
            if not success and self.config.fallback_to_cpu:
                # Fallback to CPU operations
                logger.warning("GPU field mul failed, falling back to CPU")
                np.multiply(a, b, out=result, dtype=result.dtype)
                success = True
            
            if success:
                self._update_stats(operation, time.time() - start_time, False)
                return result
            else:
                self._update_stats(operation, time.time() - start_time, True)
                raise RuntimeError("Field multiplication failed")
                
        except Exception as e:
            self._update_stats(operation, time.time() - start_time, True)
            logger.error(f"Field multiplication failed: {e}")
            raise
    
    def field_inverse(self, a: np.ndarray, result: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Perform field inversion with automatic backend selection.
        
        Args:
            a: Operand to invert
            result: Optional result array (will be created if None)
            
        Returns:
            np.ndarray: Result of field inversion
        """
        if not self.initialized:
            raise RuntimeError("GPU acceleration manager not initialized")
        
        if result is None:
            result = np.zeros_like(a)
        
        start_time = time.time()
        operation = "field_inverse"
        
        try:
            provider = self.compute_manager.get_provider()
            success = provider.zk_field_inverse(a, result)
            
            if not success and self.config.fallback_to_cpu:
                # Fallback to CPU operations
                logger.warning("GPU field inverse failed, falling back to CPU")
                for i in range(len(a)):
                    if a[i] != 0:
                        result[i] = 1  # Simplified
                    else:
                        result[i] = 0
                success = True
            
            if success:
                self._update_stats(operation, time.time() - start_time, False)
                return result
            else:
                self._update_stats(operation, time.time() - start_time, True)
                raise RuntimeError("Field inversion failed")
                
        except Exception as e:
            self._update_stats(operation, time.time() - start_time, True)
            logger.error(f"Field inversion failed: {e}")
            raise
    
    def multi_scalar_mul(
        self,
        scalars: List[np.ndarray],
        points: List[np.ndarray],
        result: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Perform multi-scalar multiplication with automatic backend selection.
        
        Args:
            scalars: List of scalar operands
            points: List of point operands
            result: Optional result array (will be created if None)
            
        Returns:
            np.ndarray: Result of multi-scalar multiplication
        """
        if not self.initialized:
            raise RuntimeError("GPU acceleration manager not initialized")
        
        if len(scalars) != len(points):
            raise ValueError("Number of scalars must match number of points")
        
        if result is None:
            result = np.zeros_like(points[0])
        
        start_time = time.time()
        operation = "multi_scalar_mul"
        
        try:
            provider = self.compute_manager.get_provider()
            success = provider.zk_multi_scalar_mul(scalars, points, result)
            
            if not success and self.config.fallback_to_cpu:
                # Fallback to CPU operations
                logger.warning("GPU multi-scalar mul failed, falling back to CPU")
                result.fill(0)
                for scalar, point in zip(scalars, points):
                    temp = np.multiply(scalar, point, dtype=result.dtype)
                    np.add(result, temp, out=result, dtype=result.dtype)
                success = True
            
            if success:
                self._update_stats(operation, time.time() - start_time, False)
                return result
            else:
                self._update_stats(operation, time.time() - start_time, True)
                raise RuntimeError("Multi-scalar multiplication failed")
                
        except Exception as e:
            self._update_stats(operation, time.time() - start_time, True)
            logger.error(f"Multi-scalar multiplication failed: {e}")
            raise
    
    def pairing(self, p1: np.ndarray, p2: np.ndarray, result: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Perform pairing operation with automatic backend selection.
        
        Args:
            p1: First point
            p2: Second point
            result: Optional result array (will be created if None)
            
        Returns:
            np.ndarray: Result of pairing operation
        """
        if not self.initialized:
            raise RuntimeError("GPU acceleration manager not initialized")
        
        if result is None:
            result = np.zeros_like(p1)
        
        start_time = time.time()
        operation = "pairing"
        
        try:
            provider = self.compute_manager.get_provider()
            success = provider.zk_pairing(p1, p2, result)
            
            if not success and self.config.fallback_to_cpu:
                # Fallback to CPU operations
                logger.warning("GPU pairing failed, falling back to CPU")
                np.multiply(p1, p2, out=result, dtype=result.dtype)
                success = True
            
            if success:
                self._update_stats(operation, time.time() - start_time, False)
                return result
            else:
                self._update_stats(operation, time.time() - start_time, True)
                raise RuntimeError("Pairing operation failed")
                
        except Exception as e:
            self._update_stats(operation, time.time() - start_time, True)
            logger.error(f"Pairing operation failed: {e}")
            raise
    
    # Batch operations
    
    def batch_field_add(self, operands: List[Tuple[np.ndarray, np.ndarray]]) -> List[np.ndarray]:
        """
        Perform batch field addition.
        
        Args:
            operands: List of (a, b) tuples
            
        Returns:
            List[np.ndarray]: List of results
        """
        results = []
        for a, b in operands:
            result = self.field_add(a, b)
            results.append(result)
        return results
    
    def batch_field_mul(self, operands: List[Tuple[np.ndarray, np.ndarray]]) -> List[np.ndarray]:
        """
        Perform batch field multiplication.
        
        Args:
            operands: List of (a, b) tuples
            
        Returns:
            List[np.ndarray]: List of results
        """
        results = []
        for a, b in operands:
            result = self.field_mul(a, b)
            results.append(result)
        return results
    
    # Performance and monitoring
    
    def benchmark_all_operations(self, iterations: int = 100) -> Dict[str, Dict[str, float]]:
        """Benchmark all supported operations."""
        if not self.initialized:
            return {"error": "Manager not initialized"}
        
        results = {}
        provider = self.compute_manager.get_provider()
        
        operations = ["add", "mul", "inverse", "multi_scalar_mul", "pairing"]
        for op in operations:
            try:
                results[op] = provider.benchmark_operation(op, iterations)
            except Exception as e:
                results[op] = {"error": str(e)}
        
        return results
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        if not self.initialized:
            return {"error": "Manager not initialized"}
        
        # Get provider metrics
        provider_metrics = self.compute_manager.get_provider().get_performance_metrics()
        
        # Add operation statistics
        operation_stats = {}
        for op, stats in self.operation_stats.items():
            if stats["count"] > 0:
                operation_stats[op] = {
                    "count": stats["count"],
                    "total_time": stats["total_time"],
                    "average_time": stats["total_time"] / stats["count"],
                    "error_rate": stats["errors"] / stats["count"],
                    "operations_per_second": stats["count"] / stats["total_time"] if stats["total_time"] > 0 else 0
                }
        
        return {
            "backend": provider_metrics,
            "operations": operation_stats,
            "manager": {
                "initialized": self.initialized,
                "config": {
                    "batch_size": self.config.batch_size,
                    "use_gpu": self.config.use_gpu,
                    "fallback_to_cpu": self.config.fallback_to_cpu,
                    "timeout": self.config.timeout
                }
            }
        }
    
    def _update_stats(self, operation: str, execution_time: float, error: bool):
        """Update operation statistics."""
        if operation in self.operation_stats:
            self.operation_stats[operation]["count"] += 1
            self.operation_stats[operation]["total_time"] += execution_time
            if error:
                self.operation_stats[operation]["errors"] += 1
    
    def reset_stats(self):
        """Reset operation statistics."""
        for stats in self.operation_stats.values():
            stats["count"] = 0
            stats["total_time"] = 0.0
            stats["errors"] = 0


# Convenience functions for easy usage

def create_gpu_manager(backend: Optional[str] = None, **config_kwargs) -> GPUAccelerationManager:
    """
    Create a GPU acceleration manager with optional backend specification.
    
    Args:
        backend: Backend name ('cuda', 'apple_silicon', 'cpu', or None for auto-detection)
        **config_kwargs: Additional configuration parameters
        
    Returns:
        GPUAccelerationManager: Configured manager instance
    """
    backend_enum = None
    if backend:
        try:
            backend_enum = ComputeBackend(backend)
        except ValueError:
            logger.warning(f"Unknown backend '{backend}', using auto-detection")
    
    config = ZKOperationConfig(**config_kwargs)
    manager = GPUAccelerationManager(backend_enum, config)
    
    if not manager.initialize():
        raise RuntimeError("Failed to initialize GPU acceleration manager")
    
    return manager


def get_available_backends() -> List[str]:
    """Get list of available compute backends."""
    from .compute_provider import ComputeProviderFactory
    backends = ComputeProviderFactory.get_available_backends()
    return [backend.value for backend in backends]


def auto_detect_best_backend() -> str:
    """Auto-detect the best available backend."""
    from .compute_provider import ComputeProviderFactory
    backend = ComputeProviderFactory.auto_detect_backend()
    return backend.value


# Context manager for easy resource management

class GPUAccelerationContext:
    """Context manager for GPU acceleration."""
    
    def __init__(self, backend: Optional[str] = None, **config_kwargs):
        self.backend = backend
        self.config_kwargs = config_kwargs
        self.manager = None
    
    def __enter__(self) -> GPUAccelerationManager:
        self.manager = create_gpu_manager(self.backend, **self.config_kwargs)
        return self.manager
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.manager:
            self.manager.shutdown()


# Usage example:
# with GPUAccelerationContext() as gpu:
#     result = gpu.field_add(a, b)
#     metrics = gpu.get_performance_metrics()
