"""
KYC/AML Providers Tests
Tests for KYC/AML provider integration
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestKYCProvider:
    """Test KYCProvider enum"""

    def test_kyc_provider_values(self):
        """Test KYCProvider enum values"""
        from utils.kyc_aml_providers import KYCProvider

        assert KYCProvider.CHAINALYSIS.value == "chainalysis"
        assert KYCProvider.SUMSUB.value == "sumsub"
        assert KYCProvider.ONFIDO.value == "onfido"
        assert KYCProvider.JUMIO.value == "jumio"
        assert KYCProvider.VERIFF.value == "veriff"


class TestKYCStatus:
    """Test KYCStatus enum"""

    def test_kyc_status_values(self):
        """Test KYCStatus enum values"""
        from utils.kyc_aml_providers import KYCStatus

        assert KYCStatus.PENDING.value == "pending"
        assert KYCStatus.APPROVED.value == "approved"
        assert KYCStatus.REJECTED.value == "rejected"
        assert KYCStatus.FAILED.value == "failed"
        assert KYCStatus.EXPIRED.value == "expired"


class TestAMLRiskLevel:
    """Test AMLRiskLevel enum"""

    def test_aml_risk_level_values(self):
        """Test AMLRiskLevel enum values"""
        from utils.kyc_aml_providers import AMLRiskLevel

        assert AMLRiskLevel.LOW.value == "low"
        assert AMLRiskLevel.MEDIUM.value == "medium"
        assert AMLRiskLevel.HIGH.value == "high"
        assert AMLRiskLevel.CRITICAL.value == "critical"


class TestKYCRequest:
    """Test KYCRequest dataclass"""

    def test_kyc_request_creation(self):
        """Test creating KYCRequest"""
        from utils.kyc_aml_providers import KYCProvider, KYCRequest

        request = KYCRequest(
            user_id="user123",
            provider=KYCProvider.CHAINALYSIS,
            customer_data={"name": "John Doe"}
        )

        assert request.user_id == "user123"
        assert request.provider == KYCProvider.CHAINALYSIS
        assert request.customer_data == {"name": "John Doe"}
        assert request.verification_level == "standard"


class TestKYCResponse:
    """Test KYCResponse dataclass"""

    def test_kyc_response_creation(self):
        """Test creating KYCResponse"""
        from datetime import datetime

        from utils.kyc_aml_providers import KYCProvider, KYCResponse, KYCStatus

        response = KYCResponse(
            request_id="req123",
            user_id="user123",
            provider=KYCProvider.CHAINALYSIS,
            status=KYCStatus.APPROVED,
            risk_score=0.05,
            verification_data={"verified": True},
            created_at=datetime.now()
        )

        assert response.request_id == "req123"
        assert response.user_id == "user123"
        assert response.status == KYCStatus.APPROVED
        assert response.risk_score == 0.05


class TestAMLCheck:
    """Test AMLCheck dataclass"""

    def test_aml_check_creation(self):
        """Test creating AMLCheck"""
        from datetime import datetime

        from utils.kyc_aml_providers import AMLCheck, AMLRiskLevel

        check = AMLCheck(
            check_id="check123",
            user_id="user123",
            provider="chainalysis",
            risk_level=AMLRiskLevel.LOW,
            risk_score=0.15,
            sanctions_hits=[],
            pep_hits=[],
            adverse_media=[],
            checked_at=datetime.now()
        )

        assert check.check_id == "check123"
        assert check.risk_level == AMLRiskLevel.LOW
        assert check.risk_score == 0.15


class TestSimpleKYCProvider:
    """Test SimpleKYCProvider class"""

    def test_init(self):
        """Test SimpleKYCProvider initialization"""
        from utils.kyc_aml_providers import KYCProvider, SimpleKYCProvider

        provider = SimpleKYCProvider()

        assert KYCProvider.CHAINALYSIS in provider.base_urls
        assert provider.base_urls[KYCProvider.CHAINALYSIS] == "https://api.chainalysis.com"

    def test_set_api_key(self):
        """Test setting API key"""
        from utils.kyc_aml_providers import KYCProvider, SimpleKYCProvider

        provider = SimpleKYCProvider()
        provider.set_api_key(KYCProvider.CHAINALYSIS, "test_key")

        assert provider.api_keys[KYCProvider.CHAINALYSIS] == "test_key"

    def test_submit_kyc_verification_no_api_key(self):
        """Test submitting KYC without API key"""
        from utils.kyc_aml_providers import KYCProvider, KYCRequest, SimpleKYCProvider

        provider = SimpleKYCProvider()
        request = KYCRequest(
            user_id="user123",
            provider=KYCProvider.CHAINALYSIS,
            customer_data={"name": "John Doe"}
        )

        with pytest.raises(ValueError, match="No API key configured"):
            provider.submit_kyc_verification(request)

    def test_submit_kyc_verification_success(self):
        """Test successful KYC submission"""
        from utils.kyc_aml_providers import KYCProvider, KYCRequest, SimpleKYCProvider

        provider = SimpleKYCProvider()
        provider.set_api_key(KYCProvider.CHAINALYSIS, "test_key")

        request = KYCRequest(
            user_id="user123",
            provider=KYCProvider.CHAINALYSIS,
            customer_data={"name": "John Doe"}
        )

        response = provider.submit_kyc_verification(request)

        assert response.user_id == "user123"
        assert response.provider == KYCProvider.CHAINALYSIS

    def test_check_kyc_status(self):
        """Test checking KYC status"""
        from utils.kyc_aml_providers import KYCProvider, SimpleKYCProvider

        provider = SimpleKYCProvider()

        # Use proper request_id format: provider_user_timestamp
        response = provider.check_kyc_status("chainalysis_user123_1234567890", KYCProvider.CHAINALYSIS)

        assert response.request_id == "chainalysis_user123_1234567890"
        assert response.provider == KYCProvider.CHAINALYSIS
        assert response.status is not None


class TestSimpleAMLProvider:
    """Test SimpleAMLProvider class"""

    def test_init(self):
        """Test SimpleAMLProvider initialization"""
        from utils.kyc_aml_providers import SimpleAMLProvider

        provider = SimpleAMLProvider()

        assert provider.api_keys == {}

    def test_set_api_key(self):
        """Test setting AML API key"""
        from utils.kyc_aml_providers import SimpleAMLProvider

        provider = SimpleAMLProvider()
        provider.set_api_key("chainalysis", "test_key")

        assert provider.api_keys["chainalysis"] == "test_key"

    def test_screen_user(self):
        """Test screening user for AML"""
        from utils.kyc_aml_providers import SimpleAMLProvider

        provider = SimpleAMLProvider()

        check = provider.screen_user("user123", {"email": "test@example.com"})

        assert check.user_id == "user123"
        assert check.risk_level is not None
        assert check.risk_score >= 0
        assert check.risk_score <= 1


class TestCLIInterfaceFunctions:
    """Test CLI interface functions"""

    def test_submit_kyc_verification(self):
        """Test submit_kyc_verification CLI function"""
        from utils.kyc_aml_providers import submit_kyc_verification

        result = submit_kyc_verification("user123", "chainalysis", {"name": "John Doe"})

        assert "request_id" in result
        assert "user_id" in result
        assert "provider" in result
        assert "status" in result
        assert result["user_id"] == "user123"
        assert result["provider"] == "chainalysis"

    def test_check_kyc_status(self):
        """Test check_kyc_status CLI function"""
        from utils.kyc_aml_providers import check_kyc_status

        # Use proper request_id format: provider_user_timestamp
        result = check_kyc_status("chainalysis_user123_1234567890", "chainalysis")

        assert "request_id" in result
        assert "user_id" in result
        assert "status" in result
        assert "risk_score" in result

    def test_perform_aml_screening(self):
        """Test perform_aml_screening CLI function"""
        from utils.kyc_aml_providers import perform_aml_screening

        result = perform_aml_screening("user123", {"email": "test@example.com"})

        assert "check_id" in result
        assert "user_id" in result
        assert "risk_level" in result
        assert "risk_score" in result
        assert result["user_id"] == "user123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
