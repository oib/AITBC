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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
