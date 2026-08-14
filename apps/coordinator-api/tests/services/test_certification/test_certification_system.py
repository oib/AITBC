"""
Tests for certification system
"""

import pytest


@pytest.mark.unit
class TestCertificationSystem:
    """Test Certification System"""

    def test_certification_system_initialization(self):
        """Test certification system initialization"""
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        assert system.certification_levels is not None
        assert len(system.certification_levels) > 0
        assert system.verification_methods is not None

    def test_generate_verification_hash(self):
        """Test verification hash generation"""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        hash_value = system.generate_verification_hash(
            agent_id="agent123", level=CertificationLevel.BASIC, certification_id="cert_abc123"
        )

        assert hash_value is not None
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 produces 64 hex characters

    def test_get_special_capabilities(self):
        """Test getting special capabilities for certification level"""
        from coordinator_api.contexts.certification.domain.certification import CertificationLevel
        from coordinator_api.contexts.certification.services.certification.certification_system import CertificationSystem

        system = CertificationSystem()

        capabilities = system.get_special_capabilities(CertificationLevel.BASIC)

        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
        assert "standard_trading" in capabilities
