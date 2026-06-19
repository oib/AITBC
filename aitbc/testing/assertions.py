"""
Test Assertions Module
Provides custom assertion helpers for testing
"""

import glob
import json
import os
import secrets
from collections.abc import Callable
from typing import Any


class TestHelpers:
    """Helper functions for testing"""

    @staticmethod
    def assert_dict_contains(subset: dict[str, Any], superset: dict[str, Any]) -> bool:
        """Check if superset contains all key-value pairs from subset"""
        for key, value in subset.items():
            if key not in superset:
                return False
            if superset[key] != value:
                return False
        return True

    @staticmethod
    def assert_lists_equal_unordered(list1: list[Any], list2: list[Any]) -> bool:
        """Check if two lists contain the same elements regardless of order"""
        return sorted(list1) == sorted(list2)

    @staticmethod
    def compare_json_objects(obj1: Any, obj2: Any) -> bool:
        """Compare two JSON-serializable objects"""
        return json.dumps(obj1, sort_keys=True) == json.dumps(obj2, sort_keys=True)

    @staticmethod
    def wait_for_condition(condition: Callable[[], bool], timeout: float = 10.0, interval: float = 0.1) -> bool:
        """Wait for a condition to become true"""
        import time

        start = time.time()
        while time.time() - start < timeout:
            if condition():
                return True
            time.sleep(interval)
        return False

    @staticmethod
    def measure_execution_time(func: Callable, *args, **kwargs) -> tuple[Any, float]:
        """Measure execution time of a function"""
        import time

        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed

    @staticmethod
    def generate_test_file_path(extension: str = ".tmp") -> str:
        """Generate a unique test file path"""
        return f"/tmp/test_{secrets.token_hex(8)}{extension}"

    @staticmethod
    def cleanup_test_files(prefix: str = "test_") -> int:
        """Clean up test files in /tmp"""
        count = 0
        for file_path in glob.glob(f"/tmp/{prefix}*"):
            try:
                os.remove(file_path)
                count += 1
            except OSError:
                pass
        return count
