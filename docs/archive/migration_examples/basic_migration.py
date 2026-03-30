#!/usr/bin/env python3
"""
Basic Migration Example

Shows how to migrate from direct CUDA calls to the new abstraction layer.
"""

# BEFORE (Direct CUDA)
# from high_performance_cuda_accelerator import HighPerformanceCUDAZKAccelerator
# 
# accelerator = HighPerformanceCUDAZKAccelerator()
# if accelerator.initialized:
#     result = accelerator.field_add_cuda(a, b)

# AFTER (Abstraction Layer)
import numpy as np
from gpu_acceleration import GPUAccelerationManager, create_gpu_manager

# Method 1: Auto-detect backend
gpu = create_gpu_manager()
gpu.initialize()

a = np.array([1, 2, 3, 4], dtype=np.uint64)
b = np.array([5, 6, 7, 8], dtype=np.uint64)

result = gpu.field_add(a, b)
print(f"Field addition result: {result}")

# Method 2: Context manager (recommended)
from gpu_acceleration import GPUAccelerationContext

with GPUAccelerationContext() as gpu:
    result = gpu.field_mul(a, b)
    print(f"Field multiplication result: {result}")

# Method 3: Quick functions
from gpu_acceleration import quick_field_add

result = quick_field_add(a, b)
print(f"Quick field addition: {result}")
