"""
Tests for partnership manager
"""

import pytest


@pytest.mark.unit
class TestPartnershipManager:
    """Test Partnership Manager"""

    def test_partnership_manager_initialization(self):
        """Test partnership manager initialization"""
        from coordinator_api.contexts.certification.services.certification.partnership_manager import PartnershipManager

        manager = PartnershipManager()

        assert manager.partnership_types is not None
        assert len(manager.partnership_types) > 0
