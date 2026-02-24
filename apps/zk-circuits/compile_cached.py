#!/usr/bin/env python3
"""
Cached ZK Circuit Compiler

Uses the ZK cache system to speed up iterative circuit development.
Only recompiles when source files have changed.
"""

import subprocess
import sys
import time
from pathlib import Path
from zk_cache import ZKCircuitCache

def compile_circuit_cached(circuit_file: str, output_dir: str = None, use_cache: bool = True) -> dict:
    """
    Compile a ZK circuit with caching support

    Args:
        circuit_file: Path to the .circom circuit file
        output_dir: Output directory for compiled artifacts (auto-generated if None)
        use_cache: Whether to use caching

    Returns:
        Dict with compilation results
    """
    circuit_path = Path(circuit_file)
    if not circuit_path.exists():
        raise FileNotFoundError(f"Circuit file not found: {circuit_file}")

    # Auto-generate output directory if not specified
    if output_dir is None:
        circuit_name = circuit_path.stem
        output_dir = f"build/{circuit_name}"

    output_path = Path(output_dir)

    cache = ZKCircuitCache()
    result = {
        'cached': False,
        'compilation_time': 0.0,
        'cache_hit': False,
        'circuit_file': str(circuit_path),
        'output_dir': str(output_path)
    }

    # Check cache first
    if use_cache:
        cached_result = cache.get_cached_artifacts(circuit_path, output_path)
        if cached_result:
            print(f"✅ Cache hit for {circuit_file} - skipping compilation")
            result['cache_hit'] = True
            result['compilation_time'] = cached_result.get('compilation_time', 0.0)
            return result

    print(f"🔧 Compiling {circuit_file}...")

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Build circom command
    cmd = [
        "circom", str(circuit_path),
        "--r1cs", "--wasm", "--sym", "--c",
        "-o", str(output_path)
    ]

    # Execute compilation
    start_time = time.time()
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        compilation_time = time.time() - start_time

        # Cache successful compilation
        if use_cache:
            cache.cache_artifacts(circuit_path, output_path, compilation_time)

        result['cached'] = True
        result['compilation_time'] = compilation_time
        print(f"✅ Compiled successfully in {compilation_time:.3f}s")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Compilation failed: {e}")
        result['error'] = str(e)
        result['cached'] = False

    return result

def main():
    """CLI interface for cached circuit compilation"""
    import argparse

    parser = argparse.ArgumentParser(description='Cached ZK Circuit Compiler')
    parser.add_argument('circuit_file', help='Path to the .circom circuit file')
    parser.add_argument('--output-dir', '-o', help='Output directory for compiled artifacts')
    parser.add_argument('--no-cache', action='store_true', help='Disable caching')
    parser.add_argument('--stats', action='store_true', help='Show cache statistics')

    args = parser.parse_args()

    if args.stats:
        cache = ZKCircuitCache()
        stats = cache.get_cache_stats()
        print(f"Cache Statistics:")
        print(f"  Entries: {stats['entries']}")
        print(f"  Total Size: {stats['total_size_mb']:.2f} MB")
        print(f"  Cache Directory: {stats['cache_dir']}")
        return

    # Compile circuit
    result = compile_circuit_cached(
        args.circuit_file,
        args.output_dir,
        not args.no_cache
    )

    if result.get('cached') or result.get('cache_hit'):
        if result.get('cache_hit'):
            print("🎯 Used cached compilation")
        else:
            print(f"✅ Compiled successfully in {result['compilation_time']:.3f}s")
    else:
        print("❌ Compilation failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
