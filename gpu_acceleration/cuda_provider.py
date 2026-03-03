"""
CUDA Compute Provider Implementation

This module implements the ComputeProvider interface for NVIDIA CUDA GPUs,
providing optimized CUDA operations for ZK circuit acceleration.
"""

import ctypes
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
import os
import sys
import time
import logging

from .compute_provider import (
    ComputeProvider, ComputeDevice, ComputeBackend, 
    ComputeTask, ComputeResult
)

# Try to import CUDA libraries
try:
    import pycuda.driver as cuda
    import pycuda.autoinit
    from pycuda.compiler import SourceModule
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cuda = None
    SourceModule = None

# Configure logging
logger = logging.getLogger(__name__)


class CUDADevice(ComputeDevice):
    """CUDA-specific device information."""
    
    def __init__(self, device_id: int, cuda_device):
        """Initialize CUDA device info."""
        super().__init__(
            device_id=device_id,
            name=cuda_device.name().decode('utf-8'),
            backend=ComputeBackend.CUDA,
            memory_total=cuda_device.total_memory(),
            memory_available=cuda_device.total_memory(),  # Will be updated
            compute_capability=f"{cuda_device.compute_capability()[0]}.{cuda_device.compute_capability()[1]}",
            is_available=True
        )
        self.cuda_device = cuda_device
        self._update_memory_info()
    
    def _update_memory_info(self):
        """Update memory information."""
        try:
            free_mem, total_mem = cuda.mem_get_info()
            self.memory_available = free_mem
            self.memory_total = total_mem
        except Exception:
            pass
    
    def update_utilization(self):
        """Update device utilization."""
        try:
            # This would require nvidia-ml-py for real utilization
            # For now, we'll estimate based on memory usage
            self._update_memory_info()
            used_memory = self.memory_total - self.memory_available
            self.utilization = (used_memory / self.memory_total) * 100
        except Exception:
            self.utilization = 0.0
    
    def update_temperature(self):
        """Update device temperature."""
        try:
            # This would require nvidia-ml-py for real temperature
            # For now, we'll set a reasonable default
            self.temperature = 65.0  # Typical GPU temperature
        except Exception:
            self.temperature = None


class CUDAComputeProvider(ComputeProvider):
    """CUDA implementation of ComputeProvider."""
    
    def __init__(self, lib_path: Optional[str] = None):
        """
        Initialize CUDA compute provider.
        
        Args:
            lib_path: Path to compiled CUDA library
        """
        self.lib_path = lib_path or self._find_cuda_lib()
        self.lib = None
        self.devices = []
        self.current_device_id = 0
        self.context = None
        self.initialized = False
        
        # CUDA-specific
        self.cuda_contexts = {}
        self.cuda_modules = {}
        
        if not CUDA_AVAILABLE:
            logger.warning("PyCUDA not available, CUDA provider will not work")
            return
        
        try:
            if self.lib_path:
                self.lib = ctypes.CDLL(self.lib_path)
                self._setup_function_signatures()
            
            # Initialize CUDA
            cuda.init()
            self._discover_devices()
            
            logger.info(f"CUDA Compute Provider initialized with {len(self.devices)} devices")
            
        except Exception as e:
            logger.error(f"Failed to initialize CUDA provider: {e}")
    
    def _find_cuda_lib(self) -> str:
        """Find the compiled CUDA library."""
        possible_paths = [
            "./liboptimized_field_operations.so",
            "./optimized_field_operations.so",
            "../liboptimized_field_operations.so",
            "../../liboptimized_field_operations.so",
            "/usr/local/lib/liboptimized_field_operations.so",
            os.path.join(os.path.dirname(__file__), "liboptimized_field_operations.so")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("CUDA library not found")
    
    def _setup_function_signatures(self):
        """Setup function signatures for the CUDA library."""
        if not self.lib:
            return
        
        # Define function signatures
        self.lib.field_add.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),  # a
            ctypes.POINTER(ctypes.c_uint64),  # b
            ctypes.POINTER(ctypes.c_uint64),  # result
            ctypes.c_int                     # count
        ]
        self.lib.field_add.restype = ctypes.c_int
        
        self.lib.field_mul.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),  # a
            ctypes.POINTER(ctypes.c_uint64),  # b
            ctypes.POINTER(ctypes.c_uint64),  # result
            ctypes.c_int                     # count
        ]
        self.lib.field_mul.restype = ctypes.c_int
        
        self.lib.field_inverse.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),  # a
            ctypes.POINTER(ctypes.c_uint64),  # result
            ctypes.c_int                     # count
        ]
        self.lib.field_inverse.restype = ctypes.c_int
        
        self.lib.multi_scalar_mul.argtypes = [
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint64)),  # scalars
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint64)),  # points
            ctypes.POINTER(ctypes.c_uint64),                  # result
            ctypes.c_int,                                     # scalar_count
            ctypes.c_int                                      # point_count
        ]
        self.lib.multi_scalar_mul.restype = ctypes.c_int
    
    def _discover_devices(self):
        """Discover available CUDA devices."""
        self.devices = []
        for i in range(cuda.Device.count()):
            try:
                cuda_device = cuda.Device(i)
                device = CUDADevice(i, cuda_device)
                self.devices.append(device)
            except Exception as e:
                logger.warning(f"Failed to initialize CUDA device {i}: {e}")
    
    def initialize(self) -> bool:
        """Initialize the CUDA provider."""
        if not CUDA_AVAILABLE:
            logger.error("CUDA not available")
            return False
        
        try:
            # Create context for first device
            if self.devices:
                self.current_device_id = 0
                self.context = self.devices[0].cuda_device.make_context()
                self.cuda_contexts[0] = self.context
                self.initialized = True
                return True
            else:
                logger.error("No CUDA devices available")
                return False
                
        except Exception as e:
            logger.error(f"CUDA initialization failed: {e}")
            return False
    
    def shutdown(self) -> None:
        """Shutdown the CUDA provider."""
        try:
            # Clean up all contexts
            for context in self.cuda_contexts.values():
                context.pop()
            self.cuda_contexts.clear()
            
            # Clean up modules
            self.cuda_modules.clear()
            
            self.initialized = False
            logger.info("CUDA provider shutdown complete")
            
        except Exception as e:
            logger.error(f"CUDA shutdown failed: {e}")
    
    def get_available_devices(self) -> List[ComputeDevice]:
        """Get list of available CUDA devices."""
        return self.devices
    
    def get_device_count(self) -> int:
        """Get number of available CUDA devices."""
        return len(self.devices)
    
    def set_device(self, device_id: int) -> bool:
        """Set the active CUDA device."""
        if device_id >= len(self.devices):
            return False
        
        try:
            # Pop current context
            if self.context:
                self.context.pop()
            
            # Set new device and create context
            self.current_device_id = device_id
            device = self.devices[device_id]
            
            if device_id not in self.cuda_contexts:
                self.cuda_contexts[device_id] = device.cuda_device.make_context()
            
            self.context = self.cuda_contexts[device_id]
            self.context.push()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set CUDA device {device_id}: {e}")
            return False
    
    def get_device_info(self, device_id: int) -> Optional[ComputeDevice]:
        """Get information about a specific CUDA device."""
        if device_id < len(self.devices):
            device = self.devices[device_id]
            device.update_utilization()
            device.update_temperature()
            return device
        return None
    
    def allocate_memory(self, size: int, device_id: Optional[int] = None) -> Any:
        """Allocate memory on CUDA device."""
        if not self.initialized:
            raise RuntimeError("CUDA provider not initialized")
        
        if device_id is not None and device_id != self.current_device_id:
            if not self.set_device(device_id):
                raise RuntimeError(f"Failed to set device {device_id}")
        
        return cuda.mem_alloc(size)
    
    def free_memory(self, memory_handle: Any) -> None:
        """Free allocated CUDA memory."""
        try:
            memory_handle.free()
        except Exception as e:
            logger.warning(f"Failed to free CUDA memory: {e}")
    
    def copy_to_device(self, host_data: Any, device_data: Any) -> None:
        """Copy data from host to CUDA device."""
        if not self.initialized:
            raise RuntimeError("CUDA provider not initialized")
        
        cuda.memcpy_htod(device_data, host_data)
    
    def copy_to_host(self, device_data: Any, host_data: Any) -> None:
        """Copy data from CUDA device to host."""
        if not self.initialized:
            raise RuntimeError("CUDA provider not initialized")
        
        cuda.memcpy_dtoh(host_data, device_data)
    
    def execute_kernel(
        self,
        kernel_name: str,
        grid_size: Tuple[int, int, int],
        block_size: Tuple[int, int, int],
        args: List[Any],
        shared_memory: int = 0
    ) -> bool:
        """Execute a CUDA kernel."""
        if not self.initialized:
            return False
        
        try:
            # This would require loading compiled CUDA kernels
            # For now, we'll use the library functions if available
            if self.lib and hasattr(self.lib, kernel_name):
                # Convert args to ctypes
                c_args = []
                for arg in args:
                    if isinstance(arg, np.ndarray):
                        c_args.append(arg.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)))
                    else:
                        c_args.append(arg)
                
                result = getattr(self.lib, kernel_name)(*c_args)
                return result == 0  # Assuming 0 means success
            
            # Fallback: try to use PyCUDA if kernel is loaded
            if kernel_name in self.cuda_modules:
                kernel = self.cuda_modules[kernel_name].get_function(kernel_name)
                kernel(*args, grid=grid_size, block=block_size, shared=shared_memory)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Kernel execution failed: {e}")
            return False
    
    def synchronize(self) -> None:
        """Synchronize CUDA operations."""
        if self.initialized:
            cuda.Context.synchronize()
    
    def get_memory_info(self, device_id: Optional[int] = None) -> Tuple[int, int]:
        """Get CUDA memory information."""
        if device_id is not None and device_id != self.current_device_id:
            if not self.set_device(device_id):
                return (0, 0)
        
        try:
            free_mem, total_mem = cuda.mem_get_info()
            return (free_mem, total_mem)
        except Exception:
            return (0, 0)
    
    def get_utilization(self, device_id: Optional[int] = None) -> float:
        """Get CUDA device utilization."""
        device = self.get_device_info(device_id or self.current_device_id)
        return device.utilization if device else 0.0
    
    def get_temperature(self, device_id: Optional[int] = None) -> Optional[float]:
        """Get CUDA device temperature."""
        device = self.get_device_info(device_id or self.current_device_id)
        return device.temperature if device else None
    
    # ZK-specific operations
    
    def zk_field_add(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """Perform field addition using CUDA."""
        if not self.lib or not self.initialized:
            return False
        
        try:
            # Allocate device memory
            a_dev = cuda.mem_alloc(a.nbytes)
            b_dev = cuda.mem_alloc(b.nbytes)
            result_dev = cuda.mem_alloc(result.nbytes)
            
            # Copy data to device
            cuda.memcpy_htod(a_dev, a)
            cuda.memcpy_htod(b_dev, b)
            
            # Execute kernel
            success = self.lib.field_add(
                a_dev, b_dev, result_dev, len(a)
            ) == 0
            
            if success:
                # Copy result back
                cuda.memcpy_dtoh(result, result_dev)
            
            # Clean up
            a_dev.free()
            b_dev.free()
            result_dev.free()
            
            return success
            
        except Exception as e:
            logger.error(f"CUDA field add failed: {e}")
            return False
    
    def zk_field_mul(self, a: np.ndarray, b: np.ndarray, result: np.ndarray) -> bool:
        """Perform field multiplication using CUDA."""
        if not self.lib or not self.initialized:
            return False
        
        try:
            # Allocate device memory
            a_dev = cuda.mem_alloc(a.nbytes)
            b_dev = cuda.mem_alloc(b.nbytes)
            result_dev = cuda.mem_alloc(result.nbytes)
            
            # Copy data to device
            cuda.memcpy_htod(a_dev, a)
            cuda.memcpy_htod(b_dev, b)
            
            # Execute kernel
            success = self.lib.field_mul(
                a_dev, b_dev, result_dev, len(a)
            ) == 0
            
            if success:
                # Copy result back
                cuda.memcpy_dtoh(result, result_dev)
            
            # Clean up
            a_dev.free()
            b_dev.free()
            result_dev.free()
            
            return success
            
        except Exception as e:
            logger.error(f"CUDA field mul failed: {e}")
            return False
    
    def zk_field_inverse(self, a: np.ndarray, result: np.ndarray) -> bool:
        """Perform field inversion using CUDA."""
        if not self.lib or not self.initialized:
            return False
        
        try:
            # Allocate device memory
            a_dev = cuda.mem_alloc(a.nbytes)
            result_dev = cuda.mem_alloc(result.nbytes)
            
            # Copy data to device
            cuda.memcpy_htod(a_dev, a)
            
            # Execute kernel
            success = self.lib.field_inverse(
                a_dev, result_dev, len(a)
            ) == 0
            
            if success:
                # Copy result back
                cuda.memcpy_dtoh(result, result_dev)
            
            # Clean up
            a_dev.free()
            result_dev.free()
            
            return success
            
        except Exception as e:
            logger.error(f"CUDA field inverse failed: {e}")
            return False
    
    def zk_multi_scalar_mul(
        self,
        scalars: List[np.ndarray],
        points: List[np.ndarray],
        result: np.ndarray
    ) -> bool:
        """Perform multi-scalar multiplication using CUDA."""
        if not self.lib or not self.initialized:
            return False
        
        try:
            # This is a simplified implementation
            # In practice, this would require more complex memory management
            scalar_count = len(scalars)
            point_count = len(points)
            
            # Allocate device memory for all scalars and points
            scalar_ptrs = []
            point_ptrs = []
            
            for scalar in scalars:
                scalar_dev = cuda.mem_alloc(scalar.nbytes)
                cuda.memcpy_htod(scalar_dev, scalar)
                scalar_ptrs.append(ctypes.c_void_p(int(scalar_dev)))
            
            for point in points:
                point_dev = cuda.mem_alloc(point.nbytes)
                cuda.memcpy_htod(point_dev, point)
                point_ptrs.append(ctypes.c_void_p(int(point_dev)))
            
            result_dev = cuda.mem_alloc(result.nbytes)
            
            # Execute kernel
            success = self.lib.multi_scalar_mul(
                (ctypes.POINTER(ctypes.c_void64) * scalar_count)(*scalar_ptrs),
                (ctypes.POINTER(ctypes.c_void64) * point_count)(*point_ptrs),
                result_dev,
                scalar_count,
                point_count
            ) == 0
            
            if success:
                # Copy result back
                cuda.memcpy_dtoh(result, result_dev)
            
            # Clean up
            for scalar_dev in [ptr for ptr in scalar_ptrs]:
                cuda.mem_free(ptr)
            for point_dev in [ptr for ptr in point_ptrs]:
                cuda.mem_free(ptr)
            result_dev.free()
            
            return success
            
        except Exception as e:
            logger.error(f"CUDA multi-scalar mul failed: {e}")
            return False
    
    def zk_pairing(self, p1: np.ndarray, p2: np.ndarray, result: np.ndarray) -> bool:
        """Perform pairing operation using CUDA."""
        # This would require a specific pairing implementation
        # For now, return False as not implemented
        logger.warning("CUDA pairing operation not implemented")
        return False
    
    # Performance and monitoring
    
    def benchmark_operation(self, operation: str, iterations: int = 100) -> Dict[str, float]:
        """Benchmark a CUDA operation."""
        if not self.initialized:
            return {"error": "CUDA provider not initialized"}
        
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
        """Get CUDA performance metrics."""
        if not self.initialized:
            return {"error": "CUDA provider not initialized"}
        
        try:
            free_mem, total_mem = self.get_memory_info()
            utilization = self.get_utilization()
            temperature = self.get_temperature()
            
            return {
                "backend": "cuda",
                "device_count": len(self.devices),
                "current_device": self.current_device_id,
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
                        "id": device.device_id,
                        "name": device.name,
                        "memory_total": device.memory_total,
                        "compute_capability": device.compute_capability,
                        "utilization": device.utilization,
                        "temperature": device.temperature
                    }
                    for device in self.devices
                ]
            }
            
        except Exception as e:
            return {"error": str(e)}


# Register the CUDA provider
from .compute_provider import ComputeProviderFactory
ComputeProviderFactory.register_provider(ComputeBackend.CUDA, CUDAComputeProvider)
