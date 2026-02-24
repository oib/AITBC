#!/usr/bin/env python3
"""
High-Performance CUDA ZK Accelerator with Optimized Kernels
Implements optimized CUDA kernels with memory coalescing, vectorization, and shared memory
"""

import ctypes
import numpy as np
from typing import List, Tuple, Optional
import os
import sys
import time

# Optimized field element structure for flat array access
class OptimizedFieldElement(ctypes.Structure):
    _fields_ = [("limbs", ctypes.c_uint64 * 4)]

class HighPerformanceCUDAZKAccelerator:
    """High-performance Python interface for optimized CUDA ZK operations"""
    
    def __init__(self, lib_path: str = None):
        """
        Initialize high-performance CUDA accelerator
        
        Args:
            lib_path: Path to compiled optimized CUDA library (.so file)
        """
        self.lib_path = lib_path or self._find_optimized_cuda_lib()
        self.lib = None
        self.initialized = False
        
        try:
            self.lib = ctypes.CDLL(self.lib_path)
            self._setup_function_signatures()
            self.initialized = True
            print(f"✅ High-Performance CUDA ZK Accelerator initialized: {self.lib_path}")
        except Exception as e:
            print(f"❌ Failed to initialize CUDA accelerator: {e}")
            self.initialized = False
    
    def _find_optimized_cuda_lib(self) -> str:
        """Find the compiled optimized CUDA library"""
        possible_paths = [
            "./liboptimized_field_operations.so",
            "./optimized_field_operations.so",
            "../liboptimized_field_operations.so",
            "../../liboptimized_field_operations.so",
            "/usr/local/lib/liboptimized_field_operations.so"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("Optimized CUDA library not found. Please compile optimized_field_operations.cu first.")
    
    def _setup_function_signatures(self):
        """Setup function signatures for optimized CUDA library functions"""
        if not self.lib:
            return
        
        # Initialize optimized CUDA device
        self.lib.init_optimized_cuda_device.argtypes = []
        self.lib.init_optimized_cuda_device.restype = ctypes.c_int
        
        # Optimized field addition with flat arrays
        self.lib.gpu_optimized_field_addition.argtypes = [
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            ctypes.c_int
        ]
        self.lib.gpu_optimized_field_addition.restype = ctypes.c_int
        
        # Vectorized field addition
        self.lib.gpu_vectorized_field_addition.argtypes = [
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),  # field_vector_t
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            ctypes.c_int
        ]
        self.lib.gpu_vectorized_field_addition.restype = ctypes.c_int
        
        # Shared memory field addition
        self.lib.gpu_shared_memory_field_addition.argtypes = [
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            np.ctypeslib.ndpointer(ctypes.c_uint64, flags="C_CONTIGUOUS"),
            ctypes.c_int
        ]
        self.lib.gpu_shared_memory_field_addition.restype = ctypes.c_int
    
    def init_device(self) -> bool:
        """Initialize optimized CUDA device and check capabilities"""
        if not self.initialized:
            print("❌ CUDA accelerator not initialized")
            return False
        
        try:
            result = self.lib.init_optimized_cuda_device()
            if result == 0:
                print("✅ Optimized CUDA device initialized successfully")
                return True
            else:
                print(f"❌ CUDA device initialization failed: {result}")
                return False
        except Exception as e:
            print(f"❌ CUDA device initialization error: {e}")
            return False
    
    def benchmark_optimized_kernels(self, max_elements: int = 10000000) -> dict:
        """
        Benchmark all optimized CUDA kernels and compare performance
        
        Args:
            max_elements: Maximum number of elements to test
            
        Returns:
            Comprehensive performance benchmark results
        """
        if not self.initialized:
            return {"error": "CUDA accelerator not initialized"}
        
        print(f"🚀 High-Performance CUDA Kernel Benchmark (up to {max_elements:,} elements)")
        print("=" * 80)
        
        # Test different dataset sizes
        test_sizes = [
            1000,      # 1K elements
            10000,     # 10K elements  
            100000,    # 100K elements
            1000000,   # 1M elements
            5000000,   # 5M elements
            10000000,  # 10M elements
        ]
        
        results = {
            "test_sizes": [],
            "optimized_flat": [],
            "vectorized": [],
            "shared_memory": [],
            "cpu_baseline": [],
            "performance_summary": {}
        }
        
        for size in test_sizes:
            if size > max_elements:
                break
                
            print(f"\n📊 Benchmarking {size:,} elements...")
            
            # Generate test data as flat arrays for optimal memory access
            a_flat, b_flat = self._generate_flat_test_data(size)
            
            # bn128 field modulus (simplified)
            modulus = [0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF]
            
            # Benchmark optimized flat array kernel
            flat_result = self._benchmark_optimized_flat_kernel(a_flat, b_flat, modulus, size)
            
            # Benchmark vectorized kernel
            vec_result = self._benchmark_vectorized_kernel(a_flat, b_flat, modulus, size)
            
            # Benchmark shared memory kernel
            shared_result = self._benchmark_shared_memory_kernel(a_flat, b_flat, modulus, size)
            
            # Benchmark CPU baseline
            cpu_result = self._benchmark_cpu_baseline(a_flat, b_flat, modulus, size)
            
            # Store results
            results["test_sizes"].append(size)
            results["optimized_flat"].append(flat_result)
            results["vectorized"].append(vec_result)
            results["shared_memory"].append(shared_result)
            results["cpu_baseline"].append(cpu_result)
            
            # Print comparison
            print(f"   Optimized Flat:   {flat_result['time']:.4f}s, {flat_result['throughput']:.0f} elem/s")
            print(f"   Vectorized:       {vec_result['time']:.4f}s, {vec_result['throughput']:.0f} elem/s")
            print(f"   Shared Memory:    {shared_result['time']:.4f}s, {shared_result['throughput']:.0f} elem/s")
            print(f"   CPU Baseline:     {cpu_result['time']:.4f}s, {cpu_result['throughput']:.0f} elem/s")
            
            # Calculate speedups
            flat_speedup = cpu_result['time'] / flat_result['time'] if flat_result['time'] > 0 else 0
            vec_speedup = cpu_result['time'] / vec_result['time'] if vec_result['time'] > 0 else 0
            shared_speedup = cpu_result['time'] / shared_result['time'] if shared_result['time'] > 0 else 0
            
            print(f"   Speedups - Flat: {flat_speedup:.2f}x, Vec: {vec_speedup:.2f}x, Shared: {shared_speedup:.2f}x")
        
        # Calculate performance summary
        results["performance_summary"] = self._calculate_performance_summary(results)
        
        # Print final summary
        self._print_performance_summary(results["performance_summary"])
        
        return results
    
    def _benchmark_optimized_flat_kernel(self, a_flat: np.ndarray, b_flat: np.ndarray, 
                                        modulus: List[int], num_elements: int) -> dict:
        """Benchmark optimized flat array kernel"""
        try:
            result_flat = np.zeros_like(a_flat)
            modulus_array = np.array(modulus, dtype=np.uint64)
            
            # Multiple runs for consistency
            times = []
            for run in range(3):
                start_time = time.time()
                success = self.lib.gpu_optimized_field_addition(
                    a_flat, b_flat, result_flat, modulus_array, num_elements
                )
                run_time = time.time() - start_time
                
                if success == 0:  # Success
                    times.append(run_time)
            
            if not times:
                return {"time": float('inf'), "throughput": 0, "success": False}
            
            avg_time = sum(times) / len(times)
            throughput = num_elements / avg_time if avg_time > 0 else 0
            
            return {"time": avg_time, "throughput": throughput, "success": True}
            
        except Exception as e:
            print(f"   ❌ Optimized flat kernel error: {e}")
            return {"time": float('inf'), "throughput": 0, "success": False}
    
    def _benchmark_vectorized_kernel(self, a_flat: np.ndarray, b_flat: np.ndarray, 
                                    modulus: List[int], num_elements: int) -> dict:
        """Benchmark vectorized kernel"""
        try:
            # Convert flat arrays to vectorized format (uint4)
            # For simplicity, we'll reuse the flat array kernel as vectorized
            # In practice, would convert to proper vector format
            result_flat = np.zeros_like(a_flat)
            modulus_array = np.array(modulus, dtype=np.uint64)
            
            times = []
            for run in range(3):
                start_time = time.time()
                success = self.lib.gpu_vectorized_field_addition(
                    a_flat, b_flat, result_flat, modulus_array, num_elements
                )
                run_time = time.time() - start_time
                
                if success == 0:
                    times.append(run_time)
            
            if not times:
                return {"time": float('inf'), "throughput": 0, "success": False}
            
            avg_time = sum(times) / len(times)
            throughput = num_elements / avg_time if avg_time > 0 else 0
            
            return {"time": avg_time, "throughput": throughput, "success": True}
            
        except Exception as e:
            print(f"   ❌ Vectorized kernel error: {e}")
            return {"time": float('inf'), "throughput": 0, "success": False}
    
    def _benchmark_shared_memory_kernel(self, a_flat: np.ndarray, b_flat: np.ndarray, 
                                       modulus: List[int], num_elements: int) -> dict:
        """Benchmark shared memory kernel"""
        try:
            result_flat = np.zeros_like(a_flat)
            modulus_array = np.array(modulus, dtype=np.uint64)
            
            times = []
            for run in range(3):
                start_time = time.time()
                success = self.lib.gpu_shared_memory_field_addition(
                    a_flat, b_flat, result_flat, modulus_array, num_elements
                )
                run_time = time.time() - start_time
                
                if success == 0:
                    times.append(run_time)
            
            if not times:
                return {"time": float('inf'), "throughput": 0, "success": False}
            
            avg_time = sum(times) / len(times)
            throughput = num_elements / avg_time if avg_time > 0 else 0
            
            return {"time": avg_time, "throughput": throughput, "success": True}
            
        except Exception as e:
            print(f"   ❌ Shared memory kernel error: {e}")
            return {"time": float('inf'), "throughput": 0, "success": False}
    
    def _benchmark_cpu_baseline(self, a_flat: np.ndarray, b_flat: np.ndarray, 
                                modulus: List[int], num_elements: int) -> dict:
        """Benchmark CPU baseline for comparison"""
        try:
            start_time = time.time()
            
            # Simple CPU field addition
            result_flat = np.zeros_like(a_flat)
            for i in range(num_elements):
                base_idx = i * 4
                for j in range(4):
                    result_flat[base_idx + j] = (a_flat[base_idx + j] + b_flat[base_idx + j]) % modulus[j]
            
            cpu_time = time.time() - start_time
            throughput = num_elements / cpu_time if cpu_time > 0 else 0
            
            return {"time": cpu_time, "throughput": throughput, "success": True}
            
        except Exception as e:
            print(f"   ❌ CPU baseline error: {e}")
            return {"time": float('inf'), "throughput": 0, "success": False}
    
    def _generate_flat_test_data(self, num_elements: int) -> Tuple[np.ndarray, np.ndarray]:
        """Generate flat array test data for optimal memory access"""
        # Generate flat arrays (num_elements * 4 limbs)
        flat_size = num_elements * 4
        
        # Use numpy for fast generation
        a_flat = np.random.randint(0, 2**32, size=flat_size, dtype=np.uint64)
        b_flat = np.random.randint(0, 2**32, size=flat_size, dtype=np.uint64)
        
        return a_flat, b_flat
    
    def _calculate_performance_summary(self, results: dict) -> dict:
        """Calculate performance summary statistics"""
        summary = {}
        
        # Find best performing kernel for each size
        best_speedups = []
        best_throughputs = []
        
        for i, size in enumerate(results["test_sizes"]):
            cpu_time = results["cpu_baseline"][i]["time"]
            
            # Calculate speedups
            flat_speedup = cpu_time / results["optimized_flat"][i]["time"] if results["optimized_flat"][i]["time"] > 0 else 0
            vec_speedup = cpu_time / results["vectorized"][i]["time"] if results["vectorized"][i]["time"] > 0 else 0
            shared_speedup = cpu_time / results["shared_memory"][i]["time"] if results["shared_memory"][i]["time"] > 0 else 0
            
            best_speedup = max(flat_speedup, vec_speedup, shared_speedup)
            best_speedups.append(best_speedup)
            
            # Find best throughput
            best_throughput = max(
                results["optimized_flat"][i]["throughput"],
                results["vectorized"][i]["throughput"],
                results["shared_memory"][i]["throughput"]
            )
            best_throughputs.append(best_throughput)
        
        if best_speedups:
            summary["best_speedup"] = max(best_speedups)
            summary["average_speedup"] = sum(best_speedups) / len(best_speedups)
            summary["best_speedup_size"] = results["test_sizes"][best_speedups.index(max(best_speedups))]
        
        if best_throughputs:
            summary["best_throughput"] = max(best_throughputs)
            summary["average_throughput"] = sum(best_throughputs) / len(best_throughputs)
            summary["best_throughput_size"] = results["test_sizes"][best_throughputs.index(max(best_throughputs))]
        
        return summary
    
    def _print_performance_summary(self, summary: dict):
        """Print comprehensive performance summary"""
        print(f"\n🎯 High-Performance CUDA Summary:")
        print("=" * 50)
        
        if "best_speedup" in summary:
            print(f"   Best Speedup: {summary['best_speedup']:.2f}x at {summary.get('best_speedup_size', 'N/A'):,} elements")
            print(f"   Average Speedup: {summary['average_speedup']:.2f}x across all tests")
        
        if "best_throughput" in summary:
            print(f"   Best Throughput: {summary['best_throughput']:.0f} elements/s at {summary.get('best_throughput_size', 'N/A'):,} elements")
            print(f"   Average Throughput: {summary['average_throughput']:.0f} elements/s")
        
        # Performance classification
        if summary.get("best_speedup", 0) > 5:
            print("   🚀 Performance: EXCELLENT - Significant GPU acceleration achieved")
        elif summary.get("best_speedup", 0) > 2:
            print("   ✅ Performance: GOOD - Measurable GPU acceleration achieved")
        elif summary.get("best_speedup", 0) > 1:
            print("   ⚠️  Performance: MODERATE - Limited GPU acceleration")
        else:
            print("   ❌ Performance: POOR - No significant GPU acceleration")
    
    def analyze_memory_bandwidth(self, num_elements: int = 1000000) -> dict:
        """Analyze memory bandwidth performance"""
        print(f"🔍 Analyzing Memory Bandwidth Performance ({num_elements:,} elements)...")
        
        a_flat, b_flat = self._generate_flat_test_data(num_elements)
        modulus = [0xFFFFFFFFFFFFFFFF] * 4
        
        # Test different kernels
        flat_result = self._benchmark_optimized_flat_kernel(a_flat, b_flat, modulus, num_elements)
        vec_result = self._benchmark_vectorized_kernel(a_flat, b_flat, modulus, num_elements)
        shared_result = self._benchmark_shared_memory_kernel(a_flat, b_flat, modulus, num_elements)
        
        # Calculate theoretical bandwidth
        data_size = num_elements * 4 * 8 * 3  # 3 arrays, 4 limbs, 8 bytes
        
        analysis = {
            "data_size_gb": data_size / (1024**3),
            "flat_bandwidth_gb_s": data_size / (flat_result['time'] * 1024**3) if flat_result['time'] > 0 else 0,
            "vectorized_bandwidth_gb_s": data_size / (vec_result['time'] * 1024**3) if vec_result['time'] > 0 else 0,
            "shared_bandwidth_gb_s": data_size / (shared_result['time'] * 1024**3) if shared_result['time'] > 0 else 0,
        }
        
        print(f"   Data Size: {analysis['data_size_gb']:.2f} GB")
        print(f"   Flat Kernel: {analysis['flat_bandwidth_gb_s']:.2f} GB/s")
        print(f"   Vectorized Kernel: {analysis['vectorized_bandwidth_gb_s']:.2f} GB/s")
        print(f"   Shared Memory Kernel: {analysis['shared_bandwidth_gb_s']:.2f} GB/s")
        
        return analysis

def main():
    """Main function for testing high-performance CUDA acceleration"""
    print("🚀 AITBC High-Performance CUDA ZK Accelerator Test")
    print("=" * 60)
    
    try:
        # Initialize high-performance accelerator
        accelerator = HighPerformanceCUDAZKAccelerator()
        
        if not accelerator.initialized:
            print("❌ Failed to initialize CUDA accelerator")
            return
        
        # Initialize device
        if not accelerator.init_device():
            return
        
        # Run comprehensive benchmark
        results = accelerator.benchmark_optimized_kernels(10000000)
        
        # Analyze memory bandwidth
        bandwidth_analysis = accelerator.analyze_memory_bandwidth(1000000)
        
        print("\n✅ High-Performance CUDA acceleration test completed!")
        
        if results.get("performance_summary", {}).get("best_speedup", 0) > 1:
            print(f"🚀 Optimization successful: {results['performance_summary']['best_speedup']:.2f}x speedup achieved")
        else:
            print("⚠️  Further optimization needed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    main()
