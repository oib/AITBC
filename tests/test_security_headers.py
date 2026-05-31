"""
Tests for security headers and CORS utilities
"""


from aitbc.security_headers import (
    CORSConfig,
    CORSMiddleware,
    SecurityHeaders,
    SecurityHeadersMiddleware,
    create_development_security_headers,
    create_permissive_cors_config,
    create_production_security_headers,
    create_strict_cors_config,
)


class TestSecurityHeaders:
    """Tests for SecurityHeaders dataclass"""

    def test_default_security_headers(self):
        """Test default security headers values"""
        headers = SecurityHeaders()
        assert headers.X_Content_Type_Options == "nosniff"
        assert headers.X_Frame_Options == "DENY"
        assert headers.X_XSS_Protection == "1; mode=block"
        assert headers.Strict_Transport_Security == "max-age=31536000; includeSubDomains"
        assert headers.Content_Security_Policy == "default-src 'self'"
        assert headers.Referrer_Policy == "strict-origin-when-cross-origin"
        assert headers.Permissions_Policy == ""
        assert headers.Cache_Control == "no-cache, no-store, must-revalidate"
        assert headers.Pragma == "no-cache"

    def test_custom_security_headers(self):
        """Test custom security headers values"""
        headers = SecurityHeaders(
            X_Frame_Options="SAMEORIGIN",
            Content_Security_Policy="default-src 'self' https://example.com"
        )
        assert headers.X_Frame_Options == "SAMEORIGIN"
        assert headers.Content_Security_Policy == "default-src 'self' https://example.com"


class TestCORSConfig:
    """Tests for CORSConfig dataclass"""

    def test_default_cors_config(self):
        """Test default CORS config values"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"]
        )
        assert config.allow_origins == ["http://localhost:3000"]
        assert config.allow_methods == ["GET", "POST"]
        assert config.allow_credentials is False
        assert config.expose_headers is None
        assert config.max_age == 3600

    def test_custom_cors_config(self):
        """Test custom CORS config values"""
        config = CORSConfig(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Content-Type"],
            allow_credentials=True,
            expose_headers=["X-Custom-Header"],
            max_age=7200
        )
        assert config.allow_origins == ["*"]
        assert config.allow_credentials is True
        assert config.expose_headers == ["X-Custom-Header"]
        assert config.max_age == 7200


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware"""

    def test_initialization_with_default_headers(self):
        """Test middleware initialization with default headers"""
        middleware = SecurityHeadersMiddleware()
        assert middleware.headers is not None
        assert middleware.headers.X_Frame_Options == "DENY"

    def test_initialization_with_custom_headers(self):
        """Test middleware initialization with custom headers"""
        custom_headers = SecurityHeaders(X_Frame_Options="SAMEORIGIN")
        middleware = SecurityHeadersMiddleware(custom_headers)
        assert middleware.headers.X_Frame_Options == "SAMEORIGIN"

    def test_get_headers(self):
        """Test get_headers returns dictionary"""
        middleware = SecurityHeadersMiddleware()
        headers = middleware.get_headers()
        assert isinstance(headers, dict)
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers
        assert "X-XSS-Protection" in headers
        assert "Strict-Transport-Security" in headers
        assert "Content-Security-Policy" in headers
        assert "Referrer-Policy" in headers
        assert "Permissions-Policy" in headers
        assert "Cache-Control" in headers
        assert "Pragma" in headers

    def test_get_headers_values(self):
        """Test get_headers returns correct values"""
        middleware = SecurityHeadersMiddleware()
        headers = middleware.get_headers()
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-XSS-Protection"] == "1; mode=block"

    def test_apply_to_response(self):
        """Test apply_to_response adds security headers"""
        middleware = SecurityHeadersMiddleware()
        response_headers = {"Content-Type": "application/json"}
        result = middleware.apply_to_response(response_headers)

        assert "X-Content-Type-Options" in result
        assert "X-Frame-Options" in result
        assert result["Content-Type"] == "application/json"

    def test_apply_to_response_overwrites_existing(self):
        """Test apply_to_response overwrites existing security headers"""
        middleware = SecurityHeadersMiddleware()
        response_headers = {"X-Frame-Options": "ALLOW"}
        result = middleware.apply_to_response(response_headers)

        assert result["X-Frame-Options"] == "DENY"


class TestCORSMiddleware:
    """Tests for CORSMiddleware"""

    def test_initialization(self):
        """Test CORS middleware initialization"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        assert middleware.config == config

    def test_get_cors_headers_allowed_origin(self):
        """Test get_cors_headers with allowed origin"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        headers = middleware.get_cors_headers("http://localhost:3000")

        assert headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert headers["Access-Control-Allow-Methods"] == "GET, POST"
        assert headers["Access-Control-Allow-Headers"] == "Content-Type"
        assert headers["Access-Control-Max-Age"] == "3600"

    def test_get_cors_headers_disallowed_origin(self):
        """Test get_cors_headers with disallowed origin"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        headers = middleware.get_cors_headers("http://evil.com")

        assert headers == {}

    def test_get_cors_headers_wildcard_origin(self):
        """Test get_cors_headers with wildcard origin"""
        config = CORSConfig(
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        headers = middleware.get_cors_headers("http://any-origin.com")

        assert headers["Access-Control-Allow-Origin"] == "http://any-origin.com"

    def test_get_cors_headers_with_credentials(self):
        """Test get_cors_headers with credentials enabled"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=True
        )
        middleware = CORSMiddleware(config)
        headers = middleware.get_cors_headers("http://localhost:3000")

        assert headers["Access-Control-Allow-Credentials"] == "true"

    def test_get_cors_headers_with_expose_headers(self):
        """Test get_cors_headers with expose headers"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            expose_headers=["X-Request-ID"]
        )
        middleware = CORSMiddleware(config)
        headers = middleware.get_cors_headers("http://localhost:3000")

        assert headers["Access-Control-Expose-Headers"] == "X-Request-ID"

    def test_is_origin_allowed_wildcard(self):
        """Test _is_origin_allowed with wildcard"""
        config = CORSConfig(
            allow_origins=["*"],
            allow_methods=["GET"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        assert middleware._is_origin_allowed("http://any-origin.com") is True

    def test_is_origin_allowed_specific(self):
        """Test _is_origin_allowed with specific origin"""
        config = CORSConfig(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        assert middleware._is_origin_allowed("http://localhost:3000") is True
        assert middleware._is_origin_allowed("http://evil.com") is False

    def test_is_preflight_request(self):
        """Test is_preflight_request"""
        config = CORSConfig(
            allow_origins=["*"],
            allow_methods=["GET"],
            allow_headers=["Content-Type"]
        )
        middleware = CORSMiddleware(config)
        assert middleware.is_preflight_request("OPTIONS") is True
        assert middleware.is_preflight_request("GET") is False
        assert middleware.is_preflight_request("options") is True


class TestFactoryFunctions:
    """Tests for factory functions"""

    def test_create_production_security_headers(self):
        """Test create_production_security_headers"""
        headers = create_production_security_headers()
        assert headers.X_Frame_Options == "DENY"
        assert "preload" in headers.Strict_Transport_Security
        assert "unsafe-inline" in headers.Content_Security_Policy
        assert "geolocation=()" in headers.Permissions_Policy

    def test_create_development_security_headers(self):
        """Test create_development_security_headers"""
        headers = create_development_security_headers()
        assert headers.X_Frame_Options == "SAMEORIGIN"
        assert headers.Strict_Transport_Security == "max-age=3600"
        assert headers.Permissions_Policy == ""
        assert headers.Cache_Control == "no-cache"

    def test_create_strict_cors_config(self):
        """Test create_strict_cors_config"""
        config = create_strict_cors_config(["http://localhost:3000"])
        assert "http://localhost:3000" in config.allow_origins
        assert "GET" in config.allow_methods
        assert "POST" in config.allow_methods
        assert "PUT" in config.allow_methods
        assert "DELETE" in config.allow_methods
        assert "PATCH" in config.allow_methods
        assert config.allow_credentials is True
        assert "X-Request-ID" in config.expose_headers
        assert config.max_age == 3600

    def test_create_permissive_cors_config(self):
        """Test create_permissive_cors_config"""
        config = create_permissive_cors_config()
        assert "*" in config.allow_origins
        assert "GET" in config.allow_methods
        assert "POST" in config.allow_methods
        assert "*" in config.allow_headers
        assert config.allow_credentials is False
        assert "*" in config.expose_headers
        assert config.max_age == 86400
