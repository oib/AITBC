"""
Focused test suite for rate limiting and error handling components
"""

import pytest
from unittest.mock import Mock, patch


class TestRateLimitingComponents:
    """Test rate limiting components without full app import"""
    
    def test_settings_rate_limit_configuration(self):
        """Test rate limit configuration in settings"""
        from app.config import Settings
        
        settings = Settings()
        
        # Verify all rate limit settings are present
        rate_limit_attrs = [
            'rate_limit_jobs_submit',
            'rate_limit_miner_register',
            'rate_limit_miner_heartbeat',
            'rate_limit_admin_stats',
            'rate_limit_marketplace_list',
            'rate_limit_marketplace_stats',
            'rate_limit_marketplace_bid',
            'rate_limit_exchange_payment'
        ]
        
        for attr in rate_limit_attrs:
            assert hasattr(settings, attr), f"Missing rate limit configuration: {attr}"
            value = getattr(settings, attr)
            assert isinstance(value, str), f"Rate limit {attr} should be a string"
            assert "/" in value, f"Rate limit {attr} should contain '/' (e.g., '100/minute')"
    
    def test_rate_limit_default_values(self):
        """Test rate limit default values"""
        from app.config import Settings
        
        settings = Settings()
        
        # Verify default values
        assert settings.rate_limit_jobs_submit == "100/minute"
        assert settings.rate_limit_miner_register == "30/minute"
        assert settings.rate_limit_miner_heartbeat == "60/minute"
        assert settings.rate_limit_admin_stats == "20/minute"
        assert settings.rate_limit_marketplace_list == "100/minute"
        assert settings.rate_limit_marketplace_stats == "50/minute"
        assert settings.rate_limit_marketplace_bid == "30/minute"
        assert settings.rate_limit_exchange_payment == "20/minute"
    
    def test_slowapi_import(self):
        """Test slowapi components can be imported"""
        try:
            from slowapi import Limiter
            from slowapi.util import get_remote_address
            from slowapi.errors import RateLimitExceeded
            
            # Test limiter creation
            limiter = Limiter(key_func=get_remote_address)
            assert limiter is not None
            
            # Test exception creation
            exc = RateLimitExceeded("Test rate limit")
            assert exc is not None
            
        except ImportError as e:
            pytest.fail(f"Failed to import slowapi components: {e}")
    
    def test_rate_limit_decorator_creation(self):
        """Test rate limit decorator creation"""
        try:
            from slowapi import Limiter
            from slowapi.util import get_remote_address
            
            limiter = Limiter(key_func=get_remote_address)
            
            # Test different rate limit strings
            rate_limits = [
                "100/minute",
                "30/minute", 
                "20/minute",
                "50/minute"
            ]
            
            for rate_limit in rate_limits:
                decorator = limiter.limit(rate_limit)
                assert decorator is not None
                
        except Exception as e:
            pytest.fail(f"Failed to create rate limit decorators: {e}")


class TestErrorHandlingComponents:
    """Test error handling components without full app import"""
    
    def test_error_response_model(self):
        """Test error response model structure"""
        try:
            from app.exceptions import ErrorResponse
            
            error_response = ErrorResponse(
                error={
                    "code": "TEST_ERROR",
                    "message": "Test error message",
                    "status": 400,
                    "details": [{
                        "field": "test_field",
                        "message": "Test detail",
                        "code": "test_code"
                    }]
                },
                request_id="test-123"
            )
            
            # Verify structure
            assert error_response.error["code"] == "TEST_ERROR"
            assert error_response.error["status"] == 400
            assert error_response.request_id == "test-123"
            assert len(error_response.error["details"]) == 1
            
            # Test model dump
            data = error_response.model_dump()
            assert "error" in data
            assert "request_id" in data
            
        except ImportError as e:
            pytest.fail(f"Failed to import ErrorResponse: {e}")
    
    def test_429_error_response_structure(self):
        """Test 429 error response structure"""
        try:
            from app.exceptions import ErrorResponse
            
            error_response = ErrorResponse(
                error={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                    "status": 429,
                    "details": [{
                        "field": "rate_limit",
                        "message": "100/minute",
                        "code": "too_many_requests",
                        "retry_after": 60
                    }]
                },
                request_id="req-123"
            )
            
            assert error_response.error["status"] == 429
            assert error_response.error["code"] == "RATE_LIMIT_EXCEEDED"
            assert "retry_after" in error_response.error["details"][0]
            
        except ImportError as e:
            pytest.fail(f"Failed to create 429 error response: {e}")
    
    def test_validation_error_structure(self):
        """Test validation error response structure"""
        try:
            from app.exceptions import ErrorResponse
            
            error_response = ErrorResponse(
                error={
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "status": 422,
                    "details": [{
                        "field": "test.field",
                        "message": "Field is required",
                        "code": "required"
                    }]
                },
                request_id="req-456"
            )
            
            assert error_response.error["status"] == 422
            assert error_response.error["code"] == "VALIDATION_ERROR"
            
            detail = error_response.error["details"][0]
            assert detail["field"] == "test.field"
            assert detail["code"] == "required"
            
        except ImportError as e:
            pytest.fail(f"Failed to create validation error response: {e}")


class TestConfigurationValidation:
    """Test configuration validation for rate limiting"""
    
    def test_rate_limit_format_validation(self):
        """Test rate limit format validation"""
        from app.config import Settings
        
        settings = Settings()
        
        # Test valid formats
        valid_formats = [
            "100/minute",
            "30/minute",
            "20/minute",
            "50/minute",
            "100/hour",
            "1000/day"
        ]
        
        for rate_limit in valid_formats:
            assert "/" in rate_limit, f"Rate limit {rate_limit} should contain '/'"
            parts = rate_limit.split("/")
            assert len(parts) == 2, f"Rate limit {rate_limit} should have format 'number/period'"
            assert parts[0].isdigit(), f"Rate limit {rate_limit} should start with number"
    
    def test_environment_based_configuration(self):
        """Test environment-based configuration"""
        from app.config import Settings
        
        # Test development environment
        with patch.dict('os.environ', {'APP_ENV': 'dev'}):
            settings = Settings(app_env="dev")
            assert settings.app_env == "dev"
            assert settings.rate_limit_jobs_submit == "100/minute"
        
        # Test production environment  
        with patch.dict('os.environ', {'APP_ENV': 'production'}):
            settings = Settings(app_env="production")
            assert settings.app_env == "production"
            assert settings.rate_limit_jobs_submit == "100/minute"


class TestLoggingIntegration:
    """Test logging integration for rate limiting and errors"""
    
    def test_shared_logging_import(self):
        """Test shared logging import"""
        try:
            from aitbc.logging import get_logger
            
            logger = get_logger("test")
            assert logger is not None
            assert hasattr(logger, 'info')
            assert hasattr(logger, 'warning')
            assert hasattr(logger, 'error')
            
        except ImportError as e:
            pytest.fail(f"Failed to import shared logging: {e}")
    
    def test_audit_log_configuration(self):
        """Test audit log configuration"""
        from app.config import Settings
        
        settings = Settings()
        
        # Verify audit log directory configuration
        assert hasattr(settings, 'audit_log_dir')
        assert isinstance(settings.audit_log_dir, str)
        assert len(settings.audit_log_dir) > 0


class TestRateLimitTierStrategy:
    """Test rate limit tier strategy"""
    
    def test_tiered_rate_limits(self):
        """Test tiered rate limit strategy"""
        from app.config import Settings
        
        settings = Settings()
        
        # Verify tiered approach: financial operations have stricter limits
        assert int(settings.rate_limit_exchange_payment.split("/")[0]) < int(settings.rate_limit_marketplace_list.split("/")[0])
        assert int(settings.rate_limit_marketplace_bid.split("/")[0]) < int(settings.rate_limit_marketplace_list.split("/")[0])
        assert int(settings.rate_limit_admin_stats.split("/")[0]) < int(settings.rate_limit_marketplace_list.split("/")[0])
        
        # Verify reasonable limits for different operations
        jobs_submit = int(settings.rate_limit_jobs_submit.split("/")[0])
        miner_heartbeat = int(settings.rate_limit_miner_heartbeat.split("/")[0])
        marketplace_list = int(settings.rate_limit_marketplace_list.split("/")[0])
        
        assert jobs_submit >= 50, "Job submission should allow reasonable rate"
        assert miner_heartbeat >= 30, "Miner heartbeat should allow reasonable rate"
        assert marketplace_list >= 50, "Marketplace browsing should allow reasonable rate"
    
    def test_security_focused_limits(self):
        """Test security-focused rate limits"""
        from app.config import Settings
        
        settings = Settings()
        
        # Financial operations should have strictest limits
        exchange_payment = int(settings.rate_limit_exchange_payment.split("/")[0])
        marketplace_bid = int(settings.rate_limit_marketplace_bid.split("/")[0])
        admin_stats = int(settings.rate_limit_admin_stats.split("/")[0])
        
        # Exchange payment should be most restrictive
        assert exchange_payment <= marketplace_bid
        assert exchange_payment <= admin_stats
        
        # All should be reasonable for security
        assert exchange_payment <= 30, "Exchange payment should be rate limited for security"
        assert marketplace_bid <= 50, "Marketplace bid should be rate limited for security"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
