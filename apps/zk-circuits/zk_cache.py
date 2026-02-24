#!/usr/bin/env python3
"""
ZK Circuit Compilation Cache System

Caches compiled circuit artifacts to speed up iterative development.
Tracks file dependencies and invalidates cache when source files change.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import time

class ZKCircuitCache:
    """Cache system for ZK circuit compilation artifacts"""

    def __init__(self, cache_dir: Path = Path(".zk_cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_manifest = self.cache_dir / "manifest.json"

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        if not file_path.exists():
            return ""

        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _get_cache_key(self, circuit_file: Path, output_dir: Path) -> str:
        """Generate cache key based on circuit file and dependencies"""
        circuit_hash = self._calculate_file_hash(circuit_file)

        # Include any imported files in hash calculation
        dependencies = self._find_dependencies(circuit_file)
        dep_hashes = [self._calculate_file_hash(dep) for dep in dependencies]

        # Create composite hash
        composite = f"{circuit_hash}|{'|'.join(dep_hashes)}|{output_dir}"
        return hashlib.sha256(composite.encode()).hexdigest()[:16]

    def _find_dependencies(self, circuit_file: Path) -> List[Path]:
        """Find Circom include dependencies"""
        dependencies = []
        try:
            with open(circuit_file, 'r') as f:
                content = f.read()

            # Find include statements
            import re
            includes = re.findall(r'include\s+["\']([^"\']+)["\']', content)

            circuit_dir = circuit_file.parent
            for include in includes:
                dep_path = circuit_dir / include
                if dep_path.exists():
                    dependencies.append(dep_path)
                    # Recursively find dependencies
                    dependencies.extend(self._find_dependencies(dep_path))

        except Exception:
            pass

        return list(set(dependencies))  # Remove duplicates

    def is_cache_valid(self, circuit_file: Path, output_dir: Path) -> bool:
        """Check if cached artifacts are still valid"""
        cache_key = self._get_cache_key(circuit_file, output_dir)
        cache_entry = self._load_cache_entry(cache_key)

        if not cache_entry:
            return False

        # Check if source files have changed
        circuit_hash = self._calculate_file_hash(circuit_file)
        if circuit_hash != cache_entry.get('circuit_hash'):
            return False

        # Check dependencies
        dependencies = self._find_dependencies(circuit_file)
        cached_deps = cache_entry.get('dependencies', {})

        if len(dependencies) != len(cached_deps):
            return False

        for dep in dependencies:
            dep_hash = self._calculate_file_hash(dep)
            if dep_hash != cached_deps.get(str(dep)):
                return False

        # Check if output files exist
        expected_files = cache_entry.get('output_files', [])
        for file_path in expected_files:
            if not Path(file_path).exists():
                return False

        return True

    def _load_cache_entry(self, cache_key: str) -> Optional[Dict]:
        """Load cache entry from manifest"""
        try:
            if self.cache_manifest.exists():
                with open(self.cache_manifest, 'r') as f:
                    manifest = json.load(f)
                return manifest.get(cache_key)
        except Exception:
            pass
        return None

    def _save_cache_entry(self, cache_key: str, entry: Dict):
        """Save cache entry to manifest"""
        try:
            manifest = {}
            if self.cache_manifest.exists():
                with open(self.cache_manifest, 'r') as f:
                    manifest = json.load(f)

            manifest[cache_key] = entry

            with open(self.cache_manifest, 'w') as f:
                json.dump(manifest, f, indent=2)

        except Exception as e:
            print(f"Warning: Failed to save cache entry: {e}")

    def get_cached_artifacts(self, circuit_file: Path, output_dir: Path) -> Optional[Dict]:
        """Retrieve cached artifacts if valid"""
        if self.is_cache_valid(circuit_file, output_dir):
            cache_key = self._get_cache_key(circuit_file, output_dir)
            cache_entry = self._load_cache_entry(cache_key)
            return cache_entry
        return None

    def cache_artifacts(self, circuit_file: Path, output_dir: Path, compilation_time: float):
        """Cache successful compilation artifacts"""
        cache_key = self._get_cache_key(circuit_file, output_dir)

        # Find all output files
        output_files = []
        if output_dir.exists():
            for ext in ['.r1cs', '.wasm', '.sym', '.c', '.dat']:
                for file_path in output_dir.rglob(f'*{ext}'):
                    output_files.append(str(file_path))

        # Calculate dependency hashes
        dependencies = self._find_dependencies(circuit_file)
        dep_hashes = {str(dep): self._calculate_file_hash(dep) for dep in dependencies}

        entry = {
            'circuit_file': str(circuit_file),
            'output_dir': str(output_dir),
            'circuit_hash': self._calculate_file_hash(circuit_file),
            'dependencies': dep_hashes,
            'output_files': output_files,
            'compilation_time': compilation_time,
            'cached_at': time.time()
        }

        self._save_cache_entry(cache_key, entry)

    def clear_cache(self):
        """Clear all cached artifacts"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            if self.cache_manifest.exists():
                with open(self.cache_manifest, 'r') as f:
                    manifest = json.load(f)

                total_entries = len(manifest)
                total_size = 0

                for entry in manifest.values():
                    for file_path in entry.get('output_files', []):
                        try:
                            total_size += Path(file_path).stat().st_size
                        except:
                            pass

                return {
                    'entries': total_entries,
                    'total_size_mb': total_size / (1024 * 1024),
                    'cache_dir': str(self.cache_dir)
                }
        except Exception:
            pass

        return {'entries': 0, 'total_size_mb': 0, 'cache_dir': str(self.cache_dir)}

def main():
    """CLI interface for cache management"""
    import argparse

    parser = argparse.ArgumentParser(description='ZK Circuit Compilation Cache')
    parser.add_argument('action', choices=['stats', 'clear'], help='Action to perform')

    args = parser.parse_args()
    cache = ZKCircuitCache()

    if args.action == 'stats':
        stats = cache.get_cache_stats()
        print(f"Cache Statistics:")
        print(f"  Entries: {stats['entries']}")
        print(f"  Total Size: {stats['total_size_mb']:.2f} MB")
        print(f"  Cache Directory: {stats['cache_dir']}")

    elif args.action == 'clear':
        cache.clear_cache()
        print("Cache cleared successfully")

if __name__ == "__main__":
    main()
