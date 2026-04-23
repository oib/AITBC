"""Edge case and error handling tests for ZK circuit cache system"""

import pytest
import sys
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json


from zk_cache import ZKCircuitCache


@pytest.mark.unit
def test_is_cache_valid_no_cache_entry():
    """Test cache validation with no cache entry"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_circuit.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test")
    
    try:
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is False
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_is_cache_valid_missing_output_files():
    """Test cache validation when output files are missing"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_circuit.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test_missing")
    
    # Create a cache entry with non-existent output files
    cache_key = cache._get_cache_key(test_file, output_dir)
    test_entry = {
        'circuit_file': str(test_file),
        'circuit_hash': cache._calculate_file_hash(test_file),
        'dependencies': {},
        'output_files': ['/nonexistent/file.r1cs']
    }
    cache._save_cache_entry(cache_key, test_entry)
    
    try:
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is False
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_is_cache_valid_changed_source():
    """Test cache validation when source file has changed"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_circuit_change.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test_change")
    
    # Create a cache entry
    cache_key = cache._get_cache_key(test_file, output_dir)
    original_hash = cache._calculate_file_hash(test_file)
    test_entry = {
        'circuit_file': str(test_file),
        'circuit_hash': original_hash,
        'dependencies': {},
        'output_files': []
    }
    cache._save_cache_entry(cache_key, test_entry)
    
    # Modify the source file
    test_file.write_text('pragma circom 2.0.0;\ninclude "new_dep.circom"')
    
    try:
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is False
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_cache_artifacts_with_missing_files():
    """Test caching artifacts when output directory is empty"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_cache_empty.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        cache.cache_artifacts(test_file, output_dir, 1.5)
        
        cache_key = cache._get_cache_key(test_file, output_dir)
        entry = cache._load_cache_entry(cache_key)
        assert entry is not None
        assert entry['output_files'] == []
    finally:
        test_file.unlink()
        import shutil
        shutil.rmtree(output_dir.parent)


@pytest.mark.unit
def test_get_cached_artifacts_invalid():
    """Test getting cached artifacts when cache is invalid"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_cache_invalid.circom")
    test_file.write_text('pragma circom 2.0.0;')
    
    output_dir = Path("/tmp/build/test_invalid")
    
    try:
        result = cache.get_cached_artifacts(test_file, output_dir)
        assert result is None
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_save_cache_entry_json_error():
    """Test saving cache entry with JSON error"""
    cache = ZKCircuitCache()
    
    # Mock json.dump to raise an exception
    with patch('json.dump', side_effect=Exception("JSON error")):
        test_entry = {'circuit_file': '/test.circom'}
        cache._save_cache_entry("test_key", test_entry)
        # Should not raise exception, just print warning


@pytest.mark.unit
def test_load_cache_entry_json_error():
    """Test loading cache entry with JSON error"""
    cache = ZKCircuitCache()
    
    # Create a malformed manifest
    cache.cache_manifest.write_text("invalid json")
    
    entry = cache._load_cache_entry("test_key")
    assert entry is None
    
    cache.cache_manifest.unlink()


@pytest.mark.unit
def test_find_dependencies_file_read_error():
    """Test dependency finding with file read error"""
    cache = ZKCircuitCache()
    
    test_file = Path("/tmp/test_deps_error.circom")
    test_file.write_text('include "dep.circom"')
    
    # Make file unreadable
    test_file.chmod(0o000)
    
    try:
        deps = cache._find_dependencies(test_file)
        # Should return empty list on error
        assert isinstance(deps, list)
    finally:
        test_file.chmod(0o644)
        test_file.unlink()


@pytest.mark.unit
def test_get_cache_stats_file_stat_error():
    """Test cache stats with file stat errors"""
    cache = ZKCircuitCache()
    
    # Add a cache entry with non-existent files
    test_entry = {
        'output_files': ['/nonexistent/file.r1cs']
    }
    cache._save_cache_entry("test_key", test_entry)
    
    stats = cache.get_cache_stats()
    # Should handle missing files gracefully
    assert stats['entries'] == 1
    assert stats['total_size_mb'] >= 0


@pytest.mark.unit
def test_clear_cache_nonexistent_dir():
    """Test clearing cache when directory doesn't exist"""
    cache = ZKCircuitCache()
    
    # Remove cache directory
    if cache.cache_dir.exists():
        import shutil
        shutil.rmtree(cache.cache_dir)
    
    # Clear should recreate directory
    cache.clear_cache()
    assert cache.cache_dir.exists()
