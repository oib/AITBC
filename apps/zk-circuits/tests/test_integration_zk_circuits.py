"""Integration tests for ZK circuit cache system"""

from pathlib import Path

import pytest
from compile_cached import compile_circuit_cached
from zk_cache import ZKCircuitCache


@pytest.mark.integration
def test_full_cache_workflow():
    """Test complete cache workflow: cache, validate, retrieve"""
    cache = ZKCircuitCache()

    # Create a test circuit file
    test_file = Path("/tmp/test_workflow.circom")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
    test_file.write_text("pragma circom 2.0.0;")

    output_dir = Path("/tmp/build/test_workflow")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create a dummy output file
    output_file = output_dir / "test_workflow.r1cs"
    output_file.write_text("dummy r1cs content")

    try:
        # Cache artifacts
        cache.cache_artifacts(test_file, output_dir, 2.5)

        # Validate cache
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is True

        # Retrieve cached artifacts
        cached = cache.get_cached_artifacts(test_file, output_dir)
        assert cached is not None
        assert cached["compilation_time"] == 2.5
        assert len(cached["output_files"]) > 0
    finally:
        test_file.unlink()
        import shutil

        shutil.rmtree(output_dir.parent)
        cache.clear_cache()


@pytest.mark.integration
def test_cache_invalidation():
    """Test cache invalidation when source changes"""
    cache = ZKCircuitCache()

    test_file = Path("/tmp/test_invalidation.circom")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
    test_file.write_text("pragma circom 2.0.0;")

    output_dir = Path("/tmp/build/test_invalidation")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "test_invalidation.r1cs"
    output_file.write_text("dummy content")

    try:
        # Cache initial version
        cache.cache_artifacts(test_file, output_dir, 1.0)
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is True

        # Modify source file
        test_file.write_text('pragma circom 2.0.0;\ninclude "new.circom"')

        # Cache should be invalid
        is_valid = cache.is_cache_valid(test_file, output_dir)
        assert is_valid is False
    finally:
        test_file.unlink()
        import shutil

        shutil.rmtree(output_dir.parent)
        cache.clear_cache()


@pytest.mark.integration
def test_cache_stats_with_entries():
    """Test cache statistics with multiple entries"""
    cache = ZKCircuitCache()

    # Create multiple cache entries
    for i in range(3):
        test_file = Path(f"/tmp/test_stats_{i}.circom")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
        test_file.write_text(f"pragma circom 2.0.0; /* test {i} */")

        output_dir = Path(f"/tmp/build/test_stats_{i}")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"test_stats_{i}.r1cs"
        output_file.write_text(f"dummy content {i}")

        cache.cache_artifacts(test_file, output_dir, 1.0 + i)

    try:
        stats = cache.get_cache_stats()
        assert stats["entries"] == 3
        assert stats["total_size_mb"] > 0
    finally:
        for i in range(3):
            test_file = Path(f"/tmp/test_stats_{i}.circom")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
            if test_file.exists():
                test_file.unlink()
        import shutil

        if Path("/tmp/build").exists():  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
            shutil.rmtree("/tmp/build")  # nosec B108 - test fixture using a fixed literal path, not production temp-file handling
        cache.clear_cache()


@pytest.mark.integration
def test_compile_circuit_cached_file_not_found():
    """Test compile_circuit_cached with nonexistent file"""
    with pytest.raises(FileNotFoundError):
        compile_circuit_cached("/nonexistent/file.circom", use_cache=False)
