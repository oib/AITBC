"""Unit tests for ZK circuit cache system"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json


from zk_cache import ZKCircuitCache


@pytest.mark.unit
def test_cache_initialization():
    """Test that ZKCircuitCache initializes correctly"""
    cache = ZKCircuitCache()
    assert cache.cache_dir.exists()
    assert cache.cache_manifest.name == "manifest.json"


@pytest.mark.unit
def test_cache_initialization_custom_dir():
    """Test ZKCircuitCache with custom cache directory"""
    custom_dir = Path("/tmp/test_zk_cache")
    cache = ZKCircuitCache(cache_dir=custom_dir)
    assert cache.cache_dir == custom_dir


@pytest.mark.unit
def test_calculate_file_hash():
    """Test file hash calculation"""
    cache = ZKCircuitCache()
    
    # Create a temporary file
    test_file = Path("/tmp/test_hash.txt")
    test_file.write_text("test content")
    
    try:
        hash1 = cache._calculate_file_hash(test_file)
        hash2 = cache._calculate_file_hash(test_file)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex chars
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_calculate_file_hash_nonexistent():
    """Test file hash calculation for nonexistent file"""
    cache = ZKCircuitCache()
    hash_value = cache._calculate_file_hash(Path("/nonexistent/file.txt"))
    assert hash_value == ""


@pytest.mark.unit
def test_find_dependencies():
    """Test dependency finding"""
    cache = ZKCircuitCache()
    
    # Create a test circuit file with includes
    test_file = Path("/tmp/test_circuit.circom")
    test_file.write_text('include "dependency.circom"')
    
    dep_file = Path("/tmp/dependency.circom")
    dep_file.write_text('pragma circom 2.0.0;')
    
    try:
        deps = cache._find_dependencies(test_file)
        assert len(deps) == 1
        assert dep_file in deps
    finally:
        test_file.unlink()
        dep_file.unlink()


@pytest.mark.unit
def test_find_dependencies_none():
    """Test dependency finding with no includes"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_circuit_no_deps.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    try:
        deps = cache._find_dependencies(test_file)
        assert len(deps) == 0
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_find_dependencies_recursive():
    """Test recursive dependency finding"""
    cache = ZKCircuitCache()
    
    # Create a chain of dependencies
    test_file = Path("/tmp/test_main.circom")
    test_file.write_text('include "dep1.circom"')
    
    dep1 = Path("/tmp/dep1.circom")
    dep1.write_text('include "dep2.circom"')
    
    dep2 = Path("/tmp/dep2.circom")
    dep2.write_text('pragma circom 2.0.0;')
    
    try:
        deps = cache._find_dependencies(test_file)
        assert len(deps) == 2
        assert dep1 in deps
        assert dep2 in deps
    finally:
        test_file.unlink()
        dep1.unlink()
        dep2.unlink()


@pytest.mark.unit
def test_get_cache_key():
    """Test cache key generation"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_circuit.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test")
    
    try:
        key1 = cache._get_cache_key(test_file, output_dir)
        key2 = cache._get_cache_key(test_file, output_dir)
        assert key1 == key2
        assert len(key1) == 16  # Truncated to 16 chars
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_load_cache_entry_nonexistent():
    """Test loading cache entry when manifest doesn't exist"""
    cache = ZKCircuitCache()
    entry = cache._load_cache_entry("test_key")
    assert entry is None


@pytest.mark.unit
def test_save_and_load_cache_entry():
    """Test saving and loading cache entry"""
    cache = ZKCircuitCache()
    
    test_entry = {
        'circuit_file': '/test.circom',
        'output_dir': '/build',
        'circuit_hash': 'abc123',
        'dependencies': {},
        'output_files': [],
        'compilation_time': 1.5,
        'cached_at': 1234567890
    }
    
    cache._save_cache_entry("test_key", test_entry)
    loaded = cache._load_cache_entry("test_key")
    
    assert loaded is not None
    assert loaded['circuit_file'] == '/test.circom'
    assert loaded['compilation_time'] == 1.5


@pytest.mark.unit
def test_get_cache_stats_empty():
    """Test cache stats with empty cache"""
    cache = ZKCircuitCache()
    cache.clear_cache()  # Clear any existing entries
    stats = cache.get_cache_stats()
    assert stats['entries'] == 0
    assert stats['total_size_mb'] == 0


@pytest.mark.unit
def test_clear_cache():
    """Test clearing cache"""
    cache = ZKCircuitCache()
    
    # Add a test entry
    test_entry = {'circuit_file': '/test.circom'}
    cache._save_cache_entry("test_key", test_entry)
    
    # Clear cache
    cache.clear_cache()
    
    # Verify cache is empty
    stats = cache.get_cache_stats()
    assert stats['entries'] == 0
