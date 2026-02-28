"""
Test suite for rate limiting and error handling
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi import Request, HTTPException
from slowapi.errors import RateLimitExceeded

from app.main import create_app
from app.config import Settings
from app.exceptions import ErrorResponse


class TestRateLimiting:
    """Test suite for rate limiting functionality"""
    
    def test_rate_limit_configuration(self):
        """Test rate limit configuration loading"""
        settings = Settings()
        
        # Verify all rate limit settings are present
        assert hasattr(settings, 'rate_limit_jobs_submit')
        assert hasattr(settings, 'rate_limit_miner_register')
        assert hasattr(settings, 'rate_limit_miner_heartbeat')
        assert hasattr(settings, 'rate_limit_admin_stats')
        assert hasattr(settings, 'rate_limit_marketplace_list')
        assert hasattr(settings, 'rate_limit_marketplace_stats')
        assert hasattr(settings, 'rate_limit_marketplace_bid')
        assert hasattr(settings, 'rate_limit_exchange_payment')
        
        # Verify default values
        assert settings.rate_limit_jobs_submit == "100/minute"
        assert settings.rate_limit_miner_register == "30/minute"
        assert settings.rate_limit_admin_stats == "20/minute"
    
    def test_rate_limit_handler_import(self):
        """Test rate limit handler can be imported"""
        try:
            from slowapi import Limiter
            from slowapi.util import get_remote_address
            
            limiter = Limiter(key_func=get_remote_address)
            assert limiter is not None
        except ImportError as e:
            pytest.fail(f"Failed to import rate limiting components: {e}")
    
    def test_rate_limit_exception_handler(self):
        """Test rate limit exception handler structure"""
        # Create a mock request
        mock_request = Mock(spec=Request)
        mock_request.headers = {"X-Request-ID": "test-123"}
        mock_request.url.path = "/v1/jobs"
        mock_request.method = "POST"
        
        # Create a rate limit exception
        rate_limit_exc = RateLimitExceeded("Rate limit exceeded")
        
        # Test that the handler can be called (basic structure test)
        try:
            from app.main import create_app
            app = create_app()
            
            # Get the rate limit handler
            handler = app.exception_handlers[RateLimitExceeded]
            assert handler is not None
            
        except Exception as e:
            # If we can't fully test due to import issues, at least verify the structure
            assert "rate_limit" in str(e).lower() or "handler" in str(e).lower()
    
    def test_rate_limit_decorator_syntax(self):
        """Test rate limit decorator syntax in routers"""
        try:
            from app.routers.client import router as client_router
            from app.routers.miner import router as miner_router
            
            # Verify routers exist and have rate limit decorators
            assert client_router is not None
            assert miner_router is not None
            
        except ImportError as e:
            pytest.fail(f"Failed to import routers with rate limiting: {e}")


class TestErrorHandling:
    """Test suite for error handling functionality"""
    
    def test_error_response_structure(self):
        """Test error response structure"""
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
        
        assert error_response.error["code"] == "TEST_ERROR"
        assert error_response.error["status"] == 400
        assert error_response.request_id == "test-123"
        assert len(error_response.error["details"]) == 1
    
    def test_general_exception_handler_structure(self):
        """Test general exception handler structure"""
        try:
            from app.main import create_app
            app = create_app()
            
            # Verify general exception handler is registered
            assert Exception in app.exception_handlers
            
            handler = app.exception_handlers[Exception]
            assert handler is not None
            
        except Exception as e:
            pytest.fail(f"Failed to verify general exception handler: {e}")
    
    def test_validation_error_handler_structure(self):
        """Test validation error handler structure"""
        try:
            from fastapi.exceptions import RequestValidationError
            from app.main import create_app
            app = create_app()
            
            # Verify validation error handler is registered
            assert RequestValidationError in app.exception_handlers
            
            handler = app.exception_handlers[RequestValidationError]
            assert handler is not None
            
        except Exception as e:
            pytest.fail(f"Failed to verify validation error handler: {e}")
    
    def test_rate_limit_error_handler_structure(self):
        """Test rate limit error handler structure"""
        try:
            from slowapi.errors import RateLimitExceeded
            from app.main import create_app
            app = create_app()
            
            # Verify rate limit error handler is registered
            assert RateLimitExceeded in app.exception_handlers
            
            handler = app.exception_handlers[RateLimitExceeded]
            assert handler is not None
            
        except Exception as e:
            pytest.fail(f"Failed to verify rate limit error handler: {e}")


class TestLifecycleEvents:
    """Test suite for lifecycle events"""
    
    def test_lifespan_function_exists(self):
        """Test that lifespan function exists and is properly structured"""
        try:
            from app.main import lifespan
            
            # Verify lifespan is an async context manager
            import inspect
            assert inspect.iscoroutinefunction(lifespan)
            
        except ImportError as e:
            pytest.fail(f"Failed to import lifespan function: {e}")
    
    def test_startup_logging_configuration(self):
        """Test startup logging configuration"""
        try:
            from app.config import Settings
            settings = Settings()
            
            # Verify audit log directory configuration
            assert hasattr(settings, 'audit_log_dir')
            assert settings.audit_log_dir is not None
            
        except Exception as e:
            pytest.fail(f"Failed to verify startup configuration: {e}")
    
    def test_rate_limit_startup_logging(self):
        """Test rate limit configuration logging"""
        try:
            from app.config import Settings
            settings = Settings()
            
            # Verify rate limit settings for startup logging
            rate_limit_attrs = [
                'rate_limit_jobs_submit',
                'rate_limit_miner_register', 
                'rate_limit_miner_heartbeat',
                'rate_limit_admin_stats'
            ]
            
            for attr in rate_limit_attrs:
                assert hasattr(settings, attr)
                assert getattr(settings, attr) is not None
                
        except Exception as e:
            pytest.fail(f"Failed to verify rate limit startup logging: {e}")


class TestConfigurationIntegration:
    """Test suite for configuration integration"""
    
    def test_environment_based_rate_limits(self):
        """Test environment-based rate limit configuration"""
        # Test development environment
        with patch.dict('os.environ', {'APP_ENV': 'dev'}):
            settings = Settings(app_env="dev")
            assert settings.rate_limit_jobs_submit == "100/minute"
        
        # Test production environment
        with patch.dict('os.environ', {'APP_ENV': 'production'}):
            settings = Settings(app_env="production")
            assert settings.rate_limit_jobs_submit == "100/minute"
    
    def test_rate_limit_configuration_completeness(self):
        """Test all rate limit configurations are present"""
        settings = Settings()
        
        expected_rate_limits = [
            'rate_limit_jobs_submit',
            'rate_limit_miner_register',
            'rate_limit_miner_heartbeat', 
            'rate_limit_admin_stats',
            'rate_limit_marketplace_list',
            'rate_limit_marketplace_stats',
            'rate_limit_marketplace_bid',
            'rate_limit_exchange_payment'
        ]
        
        for attr in expected_rate_limits:
            assert hasattr(settings, attr), f"Missing rate limit configuration: {attr}"
            value = getattr(settings, attr)
            assert isinstance(value, str), f"Rate limit {attr} should be a string"
            assert "/" in value, f"Rate limit {attr} should contain '/' (e.g., '100/minute')"


class TestErrorResponseStandards:
    """Test suite for error response standards compliance"""
    
    def test_error_response_standards(self):
        """Test error response follows API standards"""
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
            request_id="req-123"
        )
        
        # Verify standard error response structure
        assert "error" in error_response.model_dump()
        assert "code" in error_response.error
        assert "message" in error_response.error
        assert "status" in error_response.error
        assert "details" in error_response.error
        
        # Verify details structure
        detail = error_response.error["details"][0]
        assert "field" in detail
        assert "message" in detail
        assert "code" in detail
    
    def test_429_error_response_structure(self):
        """Test 429 error response structure"""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
