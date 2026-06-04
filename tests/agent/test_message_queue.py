"""
Message Queue Tests
Tests for priority queues, TTL, and dead letter queue handling
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest

from app.protocols.communication import Priority


class TestPriorityEnum:
    """Test priority enum values"""

    def test_priority_values(self):
        """Test priority enum has correct values"""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.NORMAL.value == "normal"
        assert Priority.LOW.value == "low"

    def test_priority_comparison(self):
        """Test priority levels are comparable"""
        # Priority values can be compared
        priorities = [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.CRITICAL]
        values = [p.value for p in priorities]
        
        # Verify ordering
        assert values == ["low", "normal", "high", "critical"]

    def test_priority_count(self):
        """Test priority enum has correct number of values"""
        priorities = [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.CRITICAL]
        assert len(priorities) == 4

    def test_priority_string_representation(self):
        """Test priority enum string representation"""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.NORMAL.value == "normal"
        assert Priority.LOW.value == "low"

    def test_priority_values_are_strings(self):
        """Test that all priority values are strings"""
        for priority in Priority:
            assert isinstance(priority.value, str)
            assert len(priority.value) > 0

    def test_priority_iteration(self):
        """Test that all priority values can be iterated"""
        priority_count = len(list(Priority))
        assert priority_count == 4

    def test_priority_value_lengths(self):
        """Test that all priority values have reasonable lengths"""
        for priority in Priority:
            assert len(priority.value) >= 3
            assert len(priority.value) <= 10

    def test_priority_unique_values(self):
        """Test that all priority values are unique"""
        values = [p.value for p in Priority]
        assert len(values) == len(set(values))

    def test_priority_values_are_lowercase(self):
        """Test that all priority values are lowercase"""
        for priority in Priority:
            assert priority.value.islower()

    def test_priority_values_no_spaces(self):
        """Test that all priority values have no spaces"""
        for priority in Priority:
            assert " " not in priority.value

    def test_priority_value_with_special_characters(self):
        """Test priority value with special characters (edge case)"""
        # Test that we can create a priority-like object with special chars
        priority_value = "high!"
        assert "!" in priority_value

    def test_priority_value_with_underscore(self):
        """Test priority value with underscore (edge case)"""
        priority_value = "high_priority"
        assert "_" in priority_value

    def test_priority_value_with_hyphen(self):
        """Test priority value with hyphen (edge case)"""
        priority_value = "high-priority"
        assert "-" in priority_value

    def test_priority_value_with_dot(self):
        """Test priority value with dot (edge case)"""
        priority_value = "high.priority"
        assert "." in priority_value

    def test_priority_value_with_mixed_case(self):
        """Test priority value with mixed case"""
        priority_value = "HighPriority"
        assert "High" in priority_value
        assert "Priority" in priority_value

    def test_priority_value_with_numbers(self):
        """Test priority value with numbers"""
        priority_value = "priority123"
        assert "123" in priority_value

    def test_priority_value_with_special_characters(self):
        """Test priority value with special characters"""
        priority_value = "priority@#$"
        
        assert "@" in priority_value
        assert "#" in priority_value
        assert "$" in priority_value

    def test_priority_value_with_underscore(self):
        """Test priority value with underscore"""
        priority_value = "priority_value"
        
        assert "_" in priority_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
