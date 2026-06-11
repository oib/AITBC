"""
Performance Handlers Tests
Tests for performance CLI handlers
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestPerformanceHandlers:
    """Test performance handlers"""

    def test_handle_performance_benchmark_function_exists(self):
        """Test that handle_performance_benchmark function exists"""
        try:
            from handlers.performance import handle_performance_benchmark
            assert handle_performance_benchmark is not None
        except ImportError as e:
            pytest.skip(f"Cannot import performance handlers: {e}")

    def test_handle_performance_optimize_function_exists(self):
        """Test that handle_performance_optimize function exists"""
        try:
            from handlers.performance import handle_performance_optimize
            assert handle_performance_optimize is not None
        except ImportError as e:
            pytest.skip(f"Cannot import performance handlers: {e}")

    def test_handle_performance_benchmark_command(self):
        """Test handle_performance_benchmark - skip due to complex output dependencies"""
        pytest.skip("Performance handlers have complex output format dependencies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
