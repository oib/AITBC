"""
ZK Circuit Compilation Cache System

Caches compiled circuit artifacts to speed up iterative development.
Tracks file dependencies and invalidates cache when source files change.
"""

import hashlib
import json
import time
from pathlib import Path

import click

from aitbc import get_logger

logger = get_logger(__name__)


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
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _get_cache_key(self, circuit_file: Path, output_dir: Path) -> str:
        """Generate cache key based on circuit file and dependencies"""
        circuit_hash = self._calculate_file_hash(circuit_file)
        dependencies = self._find_dependencies(circuit_file)
        dep_hashes = [self._calculate_file_hash(dep) for dep in dependencies]
        composite = f"{circuit_hash}|{'|'.join(dep_hashes)}|{output_dir}"
        return hashlib.sha256(composite.encode()).hexdigest()[:16]

    def _find_dependencies(self, circuit_file: Path) -> list[Path]:
        """Find Circom include dependencies"""
        dependencies = []
        try:
            with open(circuit_file) as f:
                content = f.read()
            import re

            includes = re.findall("include\\s+[\"\\']([^\"\\']+)[\"\\']", content)
            circuit_dir = circuit_file.parent
            for include in includes:
                dep_path = circuit_dir / include
                if dep_path.exists():
                    dependencies.append(dep_path)
                    dependencies.extend(self._find_dependencies(dep_path))
        except Exception:  # nosec B110 - intentional silent failure
            pass
        return list(set(dependencies))

    def is_cache_valid(self, circuit_file: Path, output_dir: Path) -> bool:
        """Check if cached artifacts are still valid"""
        cache_key = self._get_cache_key(circuit_file, output_dir)
        cache_entry = self._load_cache_entry(cache_key)
        if not cache_entry:
            return False
        circuit_hash = self._calculate_file_hash(circuit_file)
        if circuit_hash != cache_entry.get("circuit_hash"):
            return False
        dependencies = self._find_dependencies(circuit_file)
        cached_deps = cache_entry.get("dependencies", {})
        if len(dependencies) != len(cached_deps):
            return False
        for dep in dependencies:
            dep_hash = self._calculate_file_hash(dep)
            if dep_hash != cached_deps.get(str(dep)):
                return False
        expected_files = cache_entry.get("output_files", [])
        for file_path in expected_files:
            if not Path(file_path).exists():
                return False
        return True

    def _load_cache_entry(self, cache_key: str) -> dict | None:
        """Load cache entry from manifest"""
        try:
            if self.cache_manifest.exists():
                with open(self.cache_manifest) as f:
                    manifest = json.load(f)
                return manifest.get(cache_key)
        except Exception:  # nosec B110 - intentional silent failure
            pass
        return None

    def _save_cache_entry(self, cache_key: str, entry: dict):
        """Save cache entry to manifest"""
        try:
            manifest = {}
            if self.cache_manifest.exists():
                with open(self.cache_manifest) as f:
                    manifest = json.load(f)
            manifest[cache_key] = entry
            with open(self.cache_manifest, "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save cache entry: %s", e)

    def get_cached_artifacts(self, circuit_file: Path, output_dir: Path) -> dict | None:
        """Retrieve cached artifacts if valid"""
        if self.is_cache_valid(circuit_file, output_dir):
            cache_key = self._get_cache_key(circuit_file, output_dir)
            cache_entry = self._load_cache_entry(cache_key)
            return cache_entry
        return None

    def cache_artifacts(self, circuit_file: Path, output_dir: Path, compilation_time: float):
        """Cache successful compilation artifacts"""
        cache_key = self._get_cache_key(circuit_file, output_dir)
        output_files = []
        if output_dir.exists():
            for ext in [".r1cs", ".wasm", ".sym", ".c", ".dat"]:
                for file_path in output_dir.rglob(f"*{ext}"):
                    output_files.append(str(file_path))
        dependencies = self._find_dependencies(circuit_file)
        dep_hashes = {str(dep): self._calculate_file_hash(dep) for dep in dependencies}
        entry = {
            "circuit_file": str(circuit_file),
            "output_dir": str(output_dir),
            "circuit_hash": self._calculate_file_hash(circuit_file),
            "dependencies": dep_hashes,
            "output_files": output_files,
            "compilation_time": compilation_time,
            "cached_at": time.time(),
        }
        self._save_cache_entry(cache_key, entry)

    def clear_cache(self):
        """Clear all cached artifacts"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        try:
            if self.cache_manifest.exists():
                with open(self.cache_manifest) as f:
                    manifest = json.load(f)
                total_entries = len(manifest)
                total_size = 0
                for entry in manifest.values():
                    for file_path in entry.get("output_files", []):
                        try:
                            total_size += Path(file_path).stat().st_size
                        except (OSError, FileNotFoundError):
                            pass
                return {
                    "entries": total_entries,
                    "total_size_mb": total_size / (1024 * 1024),
                    "cache_dir": str(self.cache_dir),
                }
        except Exception:  # nosec B110 - intentional silent failure
            pass
        return {"entries": 0, "total_size_mb": 0, "cache_dir": str(self.cache_dir)}


def main():
    """CLI interface for cache management"""
    import argparse

    parser = argparse.ArgumentParser(description="ZK Circuit Compilation Cache")
    parser.add_argument("action", choices=["stats", "clear"], help="Action to perform")
    args = parser.parse_args()
    cache = ZKCircuitCache()
    if args.action == "stats":
        stats = cache.get_cache_stats()
        click.echo("Cache Statistics:")
        click.echo(f"  Entries: {stats['entries']}")
        click.echo(f"  Total Size: {stats['total_size_mb']:.2f} MB")
        click.echo(f"  Cache Directory: {stats['cache_dir']}")
    elif args.action == "clear":
        cache.clear_cache()
        click.echo("Cache cleared successfully")


if __name__ == "__main__":
    main()
