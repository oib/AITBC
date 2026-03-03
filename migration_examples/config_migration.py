#!/usr/bin/env python3
"""
Configuration Migration Example

Shows how to migrate configuration to use the new abstraction layer.
"""

# BEFORE (CUDA-specific config)
# cuda_config = {
#     "lib_path": "./liboptimized_field_operations.so",
#     "device_id": 0,
#     "memory_limit": 8*1024*1024*1024
# }

# AFTER (Backend-agnostic config)
from gpu_acceleration import ZKOperationConfig, GPUAccelerationManager, ComputeBackend

# Configuration for any backend
config = ZKOperationConfig(
    batch_size=2048,
    use_gpu=True,
    fallback_to_cpu=True,
    timeout=60.0,
    memory_limit=8*1024*1024*1024  # 8GB
)

# Create manager with specific backend
gpu = GPUAccelerationManager(backend=ComputeBackend.CUDA, config=config)
gpu.initialize()

# Or auto-detect with config
from gpu_acceleration import create_gpu_manager
gpu = create_gpu_manager(
    backend="cuda",  # or None for auto-detect
    batch_size=2048,
    fallback_to_cpu=True,
    timeout=60.0
)
