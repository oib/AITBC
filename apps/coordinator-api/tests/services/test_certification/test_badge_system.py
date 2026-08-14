"""
Tests for badge system
"""

import pytest


@pytest.mark.unit
class TestBadgeSystem:
    """Test Badge System"""

    def test_badge_system_initialization(self):
        """Test badge system initialization"""
        from coordinator_api.contexts.certification.services.certification.badge_system import BadgeSystem

        system = BadgeSystem()

        assert system.badge_categories is not None
        assert len(system.badge_categories) > 0
        assert "performance" in system.badge_categories
        assert "reliability" in system.badge_categories
