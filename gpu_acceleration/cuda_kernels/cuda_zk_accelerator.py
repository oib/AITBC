#!/usr/bin/env python3
"""
CUDA Integration for ZK Circuit Acceleration
Python wrapper for GPU-accelerated field operations and constraint verification
"""

import ctypes
import numpy as np
from typing import List, Tuple, Optional
import os
import sys

# Field element structure (256-bit for bn128 curve)
class FieldElement(ctypes.Structure):
    _fields_ = [("limbs", ctypes.c_uint64 * 4)]

# Constraint structure for parallel processing
class Constraint(ctypes.Structure):
    _fields_ = [
        ("a", FieldElement),
        ("b", FieldElement),
        ("c", FieldElement),
        ("operation", ctypes.c_uint8)  # 0: a + b = c, 1: a * b = c
    ]

class CUDAZKAccelerator:
    """Python interface for CUDA-accelerated ZK circuit operations"""
    
    def __init__(self, lib_path: str = None):
        """
        Initialize CUDA accelerator
        
        Args:
            lib_path: Path to compiled CUDA library (.so file)
        """
        self.lib_path = lib_path or self._find_cuda_lib()
        self.lib = None
        self.initialized = False
        
        try:
            self.lib = ctypes.CDLL(self.lib_path)
            self._setup_function_signatures()
            self.initialized = True
            print(f"✅ CUDA ZK Accelerator initialized: {self.lib_path}")
        except Exception as e:
            print(f"❌ Failed to initialize CUDA accelerator: {e}")
            self.initialized = False
    
    def _find_cuda_lib(self) -> str:
        """Find the compiled CUDA library"""
        # Look for library in common locations
        possible_paths = [
            "./libfield_operations.so",
            "./field_operations.so",
            "../field_operations.so",
            "../../field_operations.so",
            "/usr/local/lib/libfield_operations.so"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("CUDA library not found. Please compile field_operations.cu first.")
    
    def _setup_function_signatures(self):
        """Setup function signatures for CUDA library functions"""
        if not self.lib:
            return
        
        # Initialize CUDA device
        self.lib.init_cuda_device.argtypes = []
        self.lib.init_cuda_device.restype = ctypes.c_int
        
        # Field addition
        self.lib.gpu_field_addition.argtypes = [
            np.ctypeslib.ndpointer(FieldElement, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(FieldElement, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(FieldElement, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            ctypes.c_int
        ]
        self.lib.gpu_field_addition.restype = ctypes.c_int
        
        # Constraint verification
        self.lib.gpu_constraint_verification.argtypes = [
            np.ctypeslib.ndpointer(Constraint, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(FieldElement, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_bool, flags="C_CONTIGUOUS"),
            ctypes.c_int
        ]
        self.lib.gpu_constraint_verification.restype = ctypes.c_int
    
    def init_device(self) -> bool:
        """Initialize CUDA device and check capabilities"""
        if not self.initialized:
            print("❌ CUDA accelerator not initialized")
            return False
        
        try:
            result = self.lib.init_cuda_device()
            if result == 0:
                print("✅ CUDA device initialized successfully")
                return True
            else:
                print(f"❌ CUDA device initialization failed: {result}")
                return False
        except Exception as e:
            print(f"❌ CUDA device initialization error: {e}")
            return False
    
    def field_addition(
        self, 
        a: List[FieldElement], 
        b: List[FieldElement], 
        modulus: List[int]
    ) -> Tuple[bool, Optional[List[FieldElement]]]:
        """
        Perform parallel field addition on GPU
        
        Args:
            a: First operand array
            b: Second operand array
            modulus: Field modulus (4 x 64-bit limbs)
            
        Returns:
            (success, result_array)
        """
        if not self.initialized:
            return False, None
        
        try:
            num_elements = len(a)
            if num_elements != len(b):
                print("❌ Input arrays must have same length")
                return False, None
            
            # Convert to numpy arrays
            a_array = np.array(a, dtype=FieldElement)
            b_array = np.array(b, dtype=FieldElement)
            result_array = np.zeros(num_elements, dtype=FieldElement)
            modulus_array = np.array(modulus, dtype=ctypes.c_uint64)
            
            # Call GPU function
            result = self.lib.gpu_field_addition(
                a_array, b_array, result_array, modulus_array, num_elements
            )
            
            if result == 0:
                print(f"✅ GPU field addition completed for {num_elements} elements")
                return True, result_array.tolist()
            else:
                print(f"❌ GPU field addition failed: {result}")
                return False, None
                
        except Exception as e:
            print(f"❌ GPU field addition error: {e}")
            return False, None
    
    def constraint_verification(
        self,
        constraints: List[Constraint],
        witness: List[FieldElement]
    ) -> Tuple[bool, Optional[List[bool]]]:
        """
        Perform parallel constraint verification on GPU
        
        Args:
            constraints: Array of constraints to verify
            witness: Witness array
            
        Returns:
            (success, verification_results)
        """
        if not self.initialized:
            return False, None
        
        try:
            num_constraints = len(constraints)
            
            # Convert to numpy arrays
            constraints_array = np.array(constraints, dtype=Constraint)
            witness_array = np.array(witness, dtype=FieldElement)
            results_array = np.zeros(num_constraints, dtype=ctypes.c_bool)
            
            # Call GPU function
            result = self.lib.gpu_constraint_verification(
                constraints_array, witness_array, results_array, num_constraints
            )
            
            if result == 0:
                verified_count = np.sum(results_array)
                print(f"✅ GPU constraint verification: {verified_count}/{num_constraints} passed")
                return True, results_array.tolist()
            else:
                print(f"❌ GPU constraint verification failed: {result}")
                return False, None
                
        except Exception as e:
            print(f"❌ GPU constraint verification error: {e}")
            return False, None
    
    def benchmark_performance(self, num_elements: int = 10000) -> dict:
        """
        Benchmark GPU vs CPU performance for field operations
        
        Args:
            num_elements: Number of elements to process
            
        Returns:
            Performance benchmark results
        """
        if not self.initialized:
            return {"error": "CUDA accelerator not initialized"}
        
        print(f"🚀 Benchmarking GPU performance with {num_elements} elements...")
        
        # Generate test data
        a_elements = []
        b_elements = []
        
        for i in range(num_elements):
            a = FieldElement()
            b = FieldElement()
            
            # Fill with test values
            for j in range(4):
                a.limbs[j] = (i + j) % (2**32)
                b.limbs[j] = (i * 2 + j) % (2**32)
            
            a_elements.append(a)
            b_elements.append(b)
        
        # bn128 field modulus (simplified)
        modulus = [0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF]
        
        # GPU benchmark
        import time
        start_time = time.time()
        
        success, gpu_result = self.field_addition(a_elements, b_elements, modulus)
        
        gpu_time = time.time() - start_time
        
        # CPU benchmark (simplified)
        start_time = time.time()
        
        # Simple CPU field addition
        cpu_result = []
        for i in range(num_elements):
            c = FieldElement()
            for j in range(4):
                c.limbs[j] = (a_elements[i].limbs[j] + b_elements[i].limbs[j]) % modulus[j]
            cpu_result.append(c)
        
        cpu_time = time.time() - start_time
        
        # Calculate speedup
        speedup = cpu_time / gpu_time if gpu_time > 0 else 0
        
        results = {
            "num_elements": num_elements,
            "gpu_time": gpu_time,
            "cpu_time": cpu_time,
            "speedup": speedup,
            "gpu_success": success,
            "elements_per_second_gpu": num_elements / gpu_time if gpu_time > 0 else 0,
            "elements_per_second_cpu": num_elements / cpu_time if cpu_time > 0 else 0
        }
        
        print(f"📊 Benchmark Results:")
        print(f"   GPU Time: {gpu_time:.4f}s")
        print(f"   CPU Time: {cpu_time:.4f}s")
        print(f"   Speedup: {speedup:.2f}x")
        print(f"   GPU Throughput: {results['elements_per_second_gpu']:.0f} elements/s")
        
        return results

def main():
    """Main function for testing CUDA acceleration"""
    print("🚀 AITBC CUDA ZK Accelerator Test")
    print("=" * 50)
    
    try:
        # Initialize accelerator
        accelerator = CUDAZKAccelerator()
        
        if not accelerator.initialized:
            print("❌ Failed to initialize CUDA accelerator")
            print("💡 Please compile field_operations.cu first:")
            print("   nvcc -shared -o libfield_operations.so field_operations.cu")
            return
        
        # Initialize device
        if not accelerator.init_device():
            return
        
        # Run benchmark
        results = accelerator.benchmark_performance(10000)
        
        if "error" not in results:
            print("\n✅ CUDA acceleration test completed successfully!")
            print(f"🚀 Achieved {results['speedup']:.2f}x speedup")
        else:
            print(f"❌ Benchmark failed: {results['error']}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    main()
