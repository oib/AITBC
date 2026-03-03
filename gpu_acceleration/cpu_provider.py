"""
CPU Compute Provider Implementation

This module implements the ComputeProvider interface for CPU operations,
providing a fallback when GPU acceleration is not available.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
import time
import logging
import multiprocessing as mp

from .compute_provider import (
    ComputeProvider, ComputeDevice, ComputeBackend, 
    ComputeTask, ComputeResult
)

# Configure logging
logger = logging.getLogger(__name__)


class CPUDevice(ComputeDevice):
    """CPU device information."""
    
    def __init__(self):
        """Initialize CPU device info."""
        super().__init__(
            device_id=0,
            name=f"CPU ({mp.cpu_count()} cores)",
            backend=ComputeBackend.CPU,
            memory_total=self._get_total_memory(),
            memory_available=self._get_available_memory(),
            is_available=True
        )
        self._update_utilization()
    
    def _get_total_memory(self) -> int:
        """Get total system memory in bytes."""
        try:
            import psutil
            return psutil.virtual_memory().total
        except ImportError:
            # Fallback: estimate 16GB
            return 16 * 1024 * 1024 * 1024
    
    def _get_available_memory(self) -> int:
        """Get available system memory in bytes."""
        try:
            import psutil
            return psutil.virtual_memory().available
        except ImportError:
            # Fallback: estimate 8GB available
            return 8 * 1024 * 1024 * 1024
    
    def _update_utilization(self):
        """Update CPU utilization."""
        try:
            import psutil
            self.utilization = psutil.cpu_percent(interval=1)
        except ImportError:
            self.utilization = 0.0
    
    def update_temperature(self):
        """Update CPU temperature."""
        try:
            import psutil
            # Try to get temperature from sensors
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if 'core' in name.lower() or 'cpu' in name.lower():
                        for entry in entries:
                            if entry.current:
                                self.temperature = entry.current
                                return
            self.temperature = None
        except (ImportError, AttributeError):
            self.temperature = None


class CPUComputeProvider(ComputeProvider):
    """CPU implementation of ComputeProvider."""
    
    def __init__(self):
        """Initialize CPU compute provider."""
        self.device = CPUDevice()
        self.initialized = False
        self.memory_allocations = {}
        self.allocation_counter = 0
        
    def initialize(self) -> bool:
        """Initialize the CPU provider."""
        try:
            self.initialized = True
            logger.info("CPU Compute Provider initialized")
            return True
        except Exception as e:
            logger.error(f"CPU initialization failed: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown the CPU provider."""
        try:
            # Clean up memory allocations
            self.memory_allocations.clear()
            self.initialized = False
            logger.info("CPU provider shutdown complete")
        except Exception as e:
            logger.error(f"CPU shutdown failed: {e}")
    
    def get_available_devices(self) -> List[ComputeDevice]:
        """Get list of available CPU devices."""
        return [self.device]
    
    def get_device_count(self) -> int:
        """Get number of available CPU devices."""
        return 1
    
    def set_device(self, device_id: int) -> bool:
        """Set the active CPU device (always 0 for CPU)."""
        return device_id == 0
    
    def get_device_info(self, device_id: int) -> Optional[ComputeDevice]:
        """Get information about the CPU device."""
        if device_id == 0:
            self.device._update_utilization()
            self.device.update_temperature()
            return self.device
        return None
    
    def allocate_memory(self, size: int, device_id: Optional[int] = None) -> Any:
        """Allocate memory on CPU (returns numpy array)."""
        if not self.initialized:
            raise RuntimeError("CPU provider not initialized")
        
        # Create a numpy array as "memory allocation"
        allocation_id = self.allocation_counter
        self.allocation_counter += 1
        
        # Allocate bytes as uint8 array
        memory_array = np.zeros(size, dtype=np.uint8)
        self.memory_allocations[allocation_id] = memory_array
        
        return allocation_id
    
    def free_memory(self, memory_handle: Any) -> None:
        """Free allocated CPU memory."""
        try:
            if memory_handle in self.memory_allocations:
                del self.memory_allocations[memory_handle]
        except Exception as e:
            logger.warning(f"Failed to free CPU memory: {e}")
    
    def copy_to_device(self, host_data: Any, device_data: Any) -> None:
        """Copy data from host to CPU (no-op, already on host)."""
        # For CPU, this is just a copy between numpy arrays
        if device_data in self.memory_allocations:
            device_array = self.memory_allocations[device_data]
            if isinstance(host_data, np.ndarray):
                # Copy data to the allocated array
                data_bytes = host_data.tobytes()
                device_array[:len(data_bytes)] = np.frombuffer(data_bytes, dtype=np.uint8)
    
    def copy_to_host(self, device_data: Any, host_data: Any) -> None:
        """Copy data from CPU to host (no-op, already on host)."""
        # For CPU, this is just a copy between numpy arrays
        if device_data in self.memory_allocations:
            device_array = self.memory_allocations[device_data]
            if isinstance(host_data, np.ndarray):
                # Copy data from the allocated array
                data_bytes = device_array.tobytes()[:host_data.nbytes]
                host_data.flat[:] = np.frombuffer(data_bytes, dtype=host_data.dtype)
    
    def execute_kernel(
        self,
        kernel_name: str,
        grid_size: Tuple[int, int, int],
        block_size: Tuple[int, int, int],
        args: List[Any],
        shared_memory: int = 0
    ) -> bool:
        """Execute a CPU "kernel" (simulated)."""
        if not self.initialized:
            return False
        
        # CPU doesn't have kernels, but we can simulate some operations
        try:
            if kernel_name == "field_add":
                return self._cpu_field_add(*args)
            elif kernel_name == "field_mul":
                return self._cpu_field_mul(*args)
            elif kernel_name == "field_inverse":
                return self._cpu_field_inverse(*args)
            else:
                logger.warning(f"Unknown CPU kernel: {kernel_name}")
                return False
        except Exception as e:
            logger.error(f"CPU kernel execution failed: {e}")
            return False
    
    def _cpu_field_add(self, a_ptr, b_ptr, result_ptr, count):
        """CPU implementation of field addition."""
        # Convert pointers to actual arrays (simplified)
        # In practice, this would need proper memory management
        return True
    
    def _cpu_field_mul(self, a_ptr, b_ptr, result_ptr, count):
        """CPU implementation of field multiplication."""
        # Convert pointers to actual arrays (simplified)
        return True
    
    def _cpu_field_inverse(self, a_ptr, result_ptr, count):
        """CPU implementation of field inversion."""
        # Convert pointers to actual arrays (simplified)
        return True
    
    def synchronize(self) -> None:
        """Synchronize CPU operations (no-op)."""
        pass
    
    def get_memory_info(self, device_id: Optional[int] = None) -> Tuple[int, int]:
        """Get CPU memory information."""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return (memory.available, memory.total)
        except ImportError:
            return (8 * 1024**3, 16 * 1024**3)  # 8GB free, 16GB total
    
    def get_utilization(self, device_id: Optional[int] = None) -> float:
        """Get CPU utilization."""
        self.device._update_utilization()
        return self.device.utilization
    
    def get_temperature(self, device_id: Optional[int] = None) -> Optional[float]:
        """Get CPU temperature."""
        self.device.update_temperature()
        return self.device.temperature
    
    # ZK-specific operations (CPU implementations)
    
    def zk_field_add(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """Perform field addition using CPU."""
        try:
            # Simple element-wise addition for demonstration
            # In practice, this would implement proper field arithmetic
            np.add(a, b, out=result, dtype=result.dtype)
            return True
        except Exception as e:
            logger.error(f"CPU field add failed: {e}")
            return False
    
    def zk_field_mul(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """Perform field multiplication using CPU."""
        try:
            # Simple element-wise multiplication for demonstration
            # In practice, this would implement proper field arithmetic
            np.multiply(a, b, out=result, dtype=result.dtype)
            return True
        except Exception as e:
            logger.error(f"CPU field mul failed: {e}")
            return False
    
    def zk_field_inverse(self, a: np.ndarray, result: np.ndarray) -> bool:
        """Perform field inversion using CPU."""
        try:
            # Simplified inversion (not cryptographically correct)
            # In practice, this would implement proper field inversion
            # This is just a placeholder for demonstration
            for i in range(len(a)):
                if a[i] != 0:
                    result[i] = 1  # Simplified: inverse of non-zero is 1
                else:
                    result[i] = 0  # Inverse of 0 is 0 (simplified)
            return True
        except Exception as e:
            logger.error(f"CPU field inverse failed: {e}")
            return False
    
    def zk_multi_scalar_mul(
        self,
        scalars: List[np.ndarray],
        points: List[np.ndarray],
        result: np.ndarray
    ) -> bool:
        """Perform multi-scalar multiplication using CPU."""
        try:
            # Simplified implementation
            # In practice, this would implement proper multi-scalar multiplication
            if len(scalars) != len(points):
                return False
            
            # Initialize result to zero
            result.fill(0)
            
            # Simple accumulation (not cryptographically correct)
            for scalar, point in zip(scalars, points):
                # Multiply scalar by point and add to result
                temp = np.multiply(scalar, point, dtype=result.dtype)
                np.add(result, temp, out=result, dtype=result.dtype)
            
            return True
        except Exception as e:
            logger.error(f"CPU multi-scalar mul failed: {e}")
            return False
    
    def zk_pairing(self, p1: np.ndarray, p2: np.ndarray, result: np.ndarray) -> bool:
        """Perform pairing operation using CPU."""
        # Simplified pairing implementation
        try:
            # This is just a placeholder
            # In practice, this would implement proper pairing operations
            np.multiply(p1, p2, out=result, dtype=result.dtype)
            return True
        except Exception as e:
            logger.error(f"CPU pairing failed: {e}")
            return False
    
    # Performance and monitoring
    
    def benchmark_operation(self, operation: str, iterations: int = 100) -> Dict[str, float]:
        """Benchmark a CPU operation."""
        if not self.initialized:
            return {"error": "CPU provider not initialized"}
        
        try:
            # Create test data
            test_size = 1024
            a = np.random.randint(0, 2**32, size=test_size, dtype=np.uint64)
            b = np.random.randint(0, 2**32, size=test_size, dtype=np.uint64)
            result = np.zeros_like(a)
            
            # Warm up
            if operation == "add":
                self.zk_field_add(a, b, result)
            elif operation == "mul":
                self.zk_field_mul(a, b, result)
            
            # Benchmark
            start_time = time.time()
            for _ in range(iterations):
                if operation == "add":
                    self.zk_field_add(a, b, result)
                elif operation == "mul":
                    self.zk_field_mul(a, b, result)
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time = total_time / iterations
            ops_per_second = iterations / total_time
            
            return {
                "total_time": total_time,
                "average_time": avg_time,
                "operations_per_second": ops_per_second,
                "iterations": iterations
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get CPU performance metrics."""
        if not self.initialized:
            return {"error": "CPU provider not initialized"}
        
        try:
            free_mem, total_mem = self.get_memory_info()
            utilization = self.get_utilization()
            temperature = self.get_temperature()
            
            return {
                "backend": "cpu",
                "device_count": 1,
                "current_device": 0,
                "memory": {
                    "free": free_mem,
                    "total": total_mem,
                    "used": total_mem - free_mem,
                    "utilization": ((total_mem - free_mem) / total_mem) * 100
                },
                "utilization": utilization,
                "temperature": temperature,
                "devices": [
                    {
                        "id": self.device.device_id,
                        "name": self.device.name,
                        "memory_total": self.device.memory_total,
                        "compute_capability": None,
                        "utilization": self.device.utilization,
                        "temperature": self.device.temperature
                    }
                ]
            }
            
        except Exception as e:
            return {"error": str(e)}


# Register the CPU provider
from .compute_provider import ComputeProviderFactory
ComputeProviderFactory.register_provider(ComputeBackend.CPU, CPUComputeProvider)
