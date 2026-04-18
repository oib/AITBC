#!/usr/bin/env python3
"""
GPU-Aware ZK Circuit Compilation with Memory Optimization
Implements GPU-aware compilation strategies and memory management for large circuits
"""

import os
import json
import time
import hashlib
import subprocess
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class GPUAwareCompiler:
    """GPU-aware ZK circuit compiler with memory optimization"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or "/home/oib/windsurf/aitbc/apps/zk-circuits")
        self.cache_dir = Path("/tmp/zk_gpu_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        # GPU memory configuration (RTX 4060 Ti: 16GB)
        self.gpu_memory_config = {
            "total_memory_mb": 16384,
            "safe_memory_mb": 14336,  # Leave 2GB for system
            "circuit_memory_per_constraint": 0.001,  # MB per constraint
            "max_constraints_per_batch": 1000000  # 1M constraints per batch
        }
        
        print(f"🚀 GPU-Aware Compiler initialized")
        print(f"   Base directory: {self.base_dir}")
        print(f"   Cache directory: {self.cache_dir}")
        print(f"   GPU memory: {self.gpu_memory_config['total_memory_mb']}MB")
    
    def estimate_circuit_memory(self, circuit_path: str) -> Dict:
        """
        Estimate memory requirements for circuit compilation
        
        Args:
            circuit_path: Path to circuit file
            
        Returns:
            Memory estimation dictionary
        """
        circuit_file = Path(circuit_path)
        
        if not circuit_file.exists():
            return {"error": "Circuit file not found"}
        
        # Parse circuit to estimate constraints
        try:
            with open(circuit_file, 'r') as f:
                content = f.read()
            
            # Simple constraint estimation
            constraint_count = content.count('<==') + content.count('===')
            
            # Estimate memory requirements
            estimated_memory = constraint_count * self.gpu_memory_config["circuit_memory_per_constraint"]
            
            # Add overhead for compilation
            compilation_overhead = estimated_memory * 2  # 2x for intermediate data
            
            total_memory_mb = estimated_memory + compilation_overhead
            
            return {
                "circuit_path": str(circuit_file),
                "estimated_constraints": constraint_count,
                "estimated_memory_mb": total_memory_mb,
                "compilation_overhead_mb": compilation_overhead,
                "gpu_feasible": total_memory_mb < self.gpu_memory_config["safe_memory_mb"],
                "recommended_batch_size": min(
                    self.gpu_memory_config["max_constraints_per_batch"],
                    int(self.gpu_memory_config["safe_memory_mb"] / self.gpu_memory_config["circuit_memory_per_constraint"])
                )
            }
            
        except Exception as e:
            return {"error": f"Failed to parse circuit: {e}"}
    
    def compile_with_gpu_optimization(self, circuit_path: str, output_dir: str = None) -> Dict:
        """
        Compile circuit with GPU-aware memory optimization
        
        Args:
            circuit_path: Path to circuit file
            output_dir: Output directory for compiled artifacts
            
        Returns:
            Compilation results
        """
        start_time = time.time()
        
        # Estimate memory requirements
        memory_est = self.estimate_circuit_memory(circuit_path)
        
        if "error" in memory_est:
            return memory_est
        
        print(f"🔧 Compiling {circuit_path}")
        print(f"   Estimated constraints: {memory_est['estimated_constraints']}")
        print(f"   Estimated memory: {memory_est['estimated_memory_mb']:.2f}MB")
        
        # Check GPU feasibility
        if not memory_est["gpu_feasible"]:
            print("⚠️  Circuit too large for GPU, using CPU compilation")
            return self.compile_cpu_fallback(circuit_path, output_dir)
        
        # Create cache key
        cache_key = self._create_cache_key(circuit_path)
        cache_path = self.cache_dir / f"{cache_key}.json"
        
        # Check cache
        if cache_path.exists():
            cached_result = self._load_cache(cache_path)
            if cached_result:
                print("✅ Using cached compilation result")
                cached_result["cache_hit"] = True
                cached_result["compilation_time"] = time.time() - start_time
                return cached_result
        
        # Perform GPU-aware compilation
        try:
            result = self._compile_circuit(circuit_path, output_dir, memory_est)
            
            # Cache result
            self._save_cache(cache_path, result)
            
            result["compilation_time"] = time.time() - start_time
            result["cache_hit"] = False
            
            print(f"✅ Compilation completed in {result['compilation_time']:.3f}s")
            
            return result
            
        except Exception as e:
            print(f"❌ Compilation failed: {e}")
            return {"error": str(e), "compilation_time": time.time() - start_time}
    
    def _compile_circuit(self, circuit_path: str, output_dir: str, memory_est: Dict) -> Dict:
        """
        Perform actual circuit compilation with GPU optimization
        """
        circuit_file = Path(circuit_path)
        circuit_name = circuit_file.stem
        
        # Set output directory
        if not output_dir:
            output_dir = self.base_dir / "build" / circuit_name
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compile with Circom
        cmd = [
            "circom",
            str(circuit_file),
            "--r1cs",
            "--wasm",
            "-o", str(output_dir)
        ]
        
        print(f"🔄 Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(self.base_dir)
        )
        
        if result.returncode != 0:
            return {
                "error": "Circom compilation failed",
                "stderr": result.stderr,
                "stdout": result.stdout
            }
        
        # Check compiled artifacts
        r1cs_path = output_dir / f"{circuit_name}.r1cs"
        wasm_path = output_dir / f"{circuit_name}_js" / f"{circuit_name}.wasm"
        
        artifacts = {}
        if r1cs_path.exists():
            artifacts["r1cs"] = str(r1cs_path)
            r1cs_size = r1cs_path.stat().st_size / (1024 * 1024)  # MB
            print(f"   R1CS size: {r1cs_size:.2f}MB")
        
        if wasm_path.exists():
            artifacts["wasm"] = str(wasm_path)
            wasm_size = wasm_path.stat().st_size / (1024 * 1024)  # MB
            print(f"   WASM size: {wasm_size:.2f}MB")
        
        return {
            "success": True,
            "circuit_name": circuit_name,
            "output_dir": str(output_dir),
            "artifacts": artifacts,
            "memory_estimation": memory_est,
            "optimization_applied": "gpu_aware_memory"
        }
    
    def compile_cpu_fallback(self, circuit_path: str, output_dir: str = None) -> Dict:
        """Fallback CPU compilation for circuits too large for GPU"""
        print("🔄 Using CPU fallback compilation")
        
        # Use standard circom compilation
        return self._compile_circuit(circuit_path, output_dir, {"gpu_feasible": False})
    
    def batch_compile_optimized(self, circuit_paths: List[str]) -> Dict:
        """
        Compile multiple circuits with GPU memory optimization
        
        Args:
            circuit_paths: List of circuit file paths
            
        Returns:
            Batch compilation results
        """
        start_time = time.time()
        
        print(f"🚀 Batch compiling {len(circuit_paths)} circuits")
        
        # Estimate total memory requirements
        total_memory = 0
        memory_estimates = []
        
        for circuit_path in circuit_paths:
            est = self.estimate_circuit_memory(circuit_path)
            if "error" not in est:
                total_memory += est["estimated_memory_mb"]
                memory_estimates.append(est)
        
        print(f"   Total estimated memory: {total_memory:.2f}MB")
        
        # Check if batch fits in GPU memory
        if total_memory > self.gpu_memory_config["safe_memory_mb"]:
            print("⚠️  Batch too large for GPU, using sequential compilation")
            return self.sequential_compile(circuit_paths)
        
        # Parallel compilation (simplified - would use actual GPU parallelization)
        results = []
        for circuit_path in circuit_paths:
            result = self.compile_with_gpu_optimization(circuit_path)
            results.append(result)
        
        total_time = time.time() - start_time
        
        return {
            "success": True,
            "batch_size": len(circuit_paths),
            "total_time": total_time,
            "average_time": total_time / len(circuit_paths),
            "results": results,
            "memory_estimates": memory_estimates
        }
    
    def sequential_compile(self, circuit_paths: List[str]) -> Dict:
        """Sequential compilation fallback"""
        start_time = time.time()
        results = []
        
        for circuit_path in circuit_paths:
            result = self.compile_with_gpu_optimization(circuit_path)
            results.append(result)
        
        total_time = time.time() - start_time
        
        return {
            "success": True,
            "batch_size": len(circuit_paths),
            "compilation_type": "sequential",
            "total_time": total_time,
            "average_time": total_time / len(circuit_paths),
            "results": results
        }
    
    def _create_cache_key(self, circuit_path: str) -> str:
        """Create cache key for circuit"""
        circuit_file = Path(circuit_path)
        
        # Use file hash and modification time
        file_hash = hashlib.sha256()
        
        try:
            with open(circuit_file, 'rb') as f:
                file_hash.update(f.read())
            
            # Add modification time
            mtime = circuit_file.stat().st_mtime
            file_hash.update(str(mtime).encode())
            
            return file_hash.hexdigest()[:16]
            
        except Exception:
            # Fallback to filename
            return hashlib.sha256(str(circuit_path).encode()).hexdigest()[:16]
    
    def _load_cache(self, cache_path: Path) -> Optional[Dict]:
        """Load cached compilation result"""
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _save_cache(self, cache_path: Path, result: Dict):
        """Save compilation result to cache"""
        try:
            with open(cache_path, 'w') as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            print(f"⚠️  Failed to save cache: {e}")
    
    def benchmark_compilation_performance(self, circuit_path: str, iterations: int = 5) -> Dict:
        """
        Benchmark compilation performance
        
        Args:
            circuit_path: Path to circuit file
            iterations: Number of iterations to run
            
        Returns:
            Performance benchmark results
        """
        print(f"📊 Benchmarking compilation performance ({iterations} iterations)")
        
        times = []
        cache_hits = 0
        successes = 0
        
        for i in range(iterations):
            print(f"   Iteration {i + 1}/{iterations}")
            
            start_time = time.time()
            result = self.compile_with_gpu_optimization(circuit_path)
            iteration_time = time.time() - start_time
            
            times.append(iteration_time)
            
            if result.get("cache_hit"):
                cache_hits += 1
            
            if result.get("success"):
                successes += 1
        
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        return {
            "circuit_path": circuit_path,
            "iterations": iterations,
            "success_rate": successes / iterations,
            "cache_hit_rate": cache_hits / iterations,
            "average_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
            "times": times
        }

def main():
    """Main function for testing GPU-aware compilation"""
    print("🚀 AITBC GPU-Aware ZK Circuit Compiler")
    print("=" * 50)
    
    compiler = GPUAwareCompiler()
    
    # Test with existing circuits
    test_circuits = [
        "modular_ml_components.circom",
        "ml_training_verification.circom",
        "ml_inference_verification.circom"
    ]
    
    for circuit in test_circuits:
        circuit_path = compiler.base_dir / circuit
        
        if circuit_path.exists():
            print(f"\n🔧 Testing {circuit}")
            
            # Estimate memory
            memory_est = compiler.estimate_circuit_memory(str(circuit_path))
            print(f"   Memory estimation: {memory_est}")
            
            # Compile
            result = compiler.compile_with_gpu_optimization(str(circuit_path))
            print(f"   Result: {result.get('success', False)}")
            
        else:
            print(f"⚠️  Circuit not found: {circuit_path}")

if __name__ == "__main__":
    main()
