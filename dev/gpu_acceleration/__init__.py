"""
GPU Acceleration Module

This module provides a clean, backend-agnostic interface for GPU acceleration
in the AITBC project. It automatically selects the best available backend
(CUDA, Apple Silicon, CPU) and provides unified ZK operations.

Usage:
    from gpu_acceleration import GPUAccelerationManager, create_gpu_manager
    
    # Auto-detect and initialize
    with GPUAccelerationContext() as gpu:
        result = gpu.field_add(a, b)
        metrics = gpu.get_performance_metrics()
    
    # Or specify backend
    gpu = create_gpu_manager(backend="cuda")
    result = gpu.field_mul(a, b)
"""

# Public API
from .gpu_manager import (
    GPUAccelerationManager,
    GPUAccelerationContext,
    create_gpu_manager,
    get_available_backends,
    auto_detect_best_backend,
    ZKOperationConfig
)

# Backend enumeration
from .compute_provider import ComputeBackend, ComputeDevice

# Version information
__version__ = "1.0.0"
__author__ = "AITBC Team"
__email__ = "dev@aitbc.dev"

# Initialize logging
import logging
logger = logging.getLogger(__name__)

# Auto-detect available backends on import
try:
    AVAILABLE_BACKENDS = get_available_backends()
    BEST_BACKEND = auto_detect_best_backend()
    logger.info(f"GPU Acceleration Module loaded")
    logger.info(f"Available backends: {AVAILABLE_BACKENDS}")
    logger.info(f"Best backend: {BEST_BACKEND}")
except Exception as e:
    logger.warning(f"GPU backend auto-detection failed: {e}")
    AVAILABLE_BACKENDS = ["cpu"]
    BEST_BACKEND = "cpu"

# Convenience functions for quick usage
def quick_field_add(a, b, backend=None):
    """Quick field addition with auto-initialization."""
    with GPUAccelerationContext(backend=backend) as gpu:
        return gpu.field_add(a, b)

def quick_field_mul(a, b, backend=None):
    """Quick field multiplication with auto-initialization."""
    with GPUAccelerationContext(backend=backend) as gpu:
        return gpu.field_mul(a, b)

def quick_field_inverse(a, backend=None):
    """Quick field inversion with auto-initialization."""
    with GPUAccelerationContext(backend=backend) as gpu:
        return gpu.field_inverse(a)

def quick_multi_scalar_mul(scalars, points, backend=None):
    """Quick multi-scalar multiplication with auto-initialization."""
    with GPUAccelerationContext(backend=backend) as gpu:
        return gpu.multi_scalar_mul(scalars, points)

# Export all public components
__all__ = [
    # Main classes
    "GPUAccelerationManager",
    "GPUAccelerationContext",
    
    # Factory functions
    "create_gpu_manager",
    "get_available_backends",
    "auto_detect_best_backend",
    
    # Configuration
    "ZKOperationConfig",
    "ComputeBackend",
    "ComputeDevice",
    
    # Quick functions
    "quick_field_add",
    "quick_field_mul",
    "quick_field_inverse",
    "quick_multi_scalar_mul",
    
    # Module info
    "__version__",
    "AVAILABLE_BACKENDS",
    "BEST_BACKEND"
]

# Module initialization check
def is_available():
    """Check if GPU acceleration is available."""
    return len(AVAILABLE_BACKENDS) > 0

def is_gpu_available():
    """Check if any GPU backend is available."""
    gpu_backends = ["cuda", "apple_silicon", "rocm", "opencl"]
    return any(backend in AVAILABLE_BACKENDS for backend in gpu_backends)

def get_system_info():
    """Get system information for GPU acceleration."""
    return {
        "version": __version__,
        "available_backends": AVAILABLE_BACKENDS,
        "best_backend": BEST_BACKEND,
        "gpu_available": is_gpu_available(),
        "cpu_available": "cpu" in AVAILABLE_BACKENDS
    }

# Initialize module with system info
logger.info(f"GPU Acceleration System Info: {get_system_info()}")
