"""
JWT Handler Tests
Tests for JWT token generation, validation, and password management
"""

from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException

from aitbc.auth import APIKeyManager, JWTAuth, JWTHandler
from aitbc.exceptions import ConfigurationError


class TestJWTHandler:
    """Test JWTHandler class"""

    def test_jwt_handler_initialization(self):
        """Test JWT handler initialization"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        assert handler.secret_key == "test_secret_key_for_testing_that_is_at_least_32_characters"
        assert handler.algorithm == "HS256"
        assert handler.token_expiry == timedelta(hours=24)
        assert handler.refresh_expiry == timedelta(days=7)

    def test_jwt_handler_default_secret(self, monkeypatch):
        """Test JWT handler with default secret in a non-production environment"""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        handler = JWTHandler()

        assert handler.secret_key is not None
        assert len(handler.secret_key) > 0

    def test_jwt_handler_requires_secret_in_production(self, monkeypatch):
        """Test that missing JWT secret raises an error in production"""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(ConfigurationError, match="JWT_SECRET"):
            JWTHandler()

    def test_jwt_handler_rejects_short_secret(self):
        """Test that an explicit short secret is rejected"""
        with pytest.raises(ValueError, match="at least 32"):
            JWTHandler("short")

    def test_jwt_handler_rejects_default_secret(self):
        """Test that known default secrets are rejected"""
        with pytest.raises(ValueError, match="default"):
            JWTHandler("change-me-in-production")

    def test_generate_token_success(self):
        """Test successful token generation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "role": "admin"}

        result = handler.generate_token(payload)

        assert result["status"] == "success"
        assert "token" in result
        assert "expires_at" in result
        assert result["token_type"] == "Bearer"

    def test_generate_token_standardizes_sub_claim(self):
        """Test token generation creates a canonical `sub` claim from legacy `user_id`"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        result = handler.generate_token({"user_id": "user123", "role": "admin"})
        validation = handler.validate_token(result["token"])

        assert validation["valid"] is True
        assert validation["payload"]["sub"] == "user123"
        assert validation["payload"]["user_id"] == "user123"

    def test_generate_token_custom_expiry(self):
        """Test token generation with custom expiry"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        custom_expiry = timedelta(hours=1)

        result = handler.generate_token(payload, expires_delta=custom_expiry)

        assert result["status"] == "success"
        assert "token" in result

    def test_generate_refresh_token_success(self):
        """Test successful refresh token generation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}

        result = handler.generate_refresh_token(payload)

        assert result["status"] == "success"
        assert "refresh_token" in result
        assert "expires_at" in result

    def test_validate_token_valid(self):
        """Test validation of valid token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "role": "admin"}
        token_result = handler.generate_token(payload)

        validation = handler.validate_token(token_result["token"])

        assert validation["status"] == "success"
        assert validation["valid"] is True
        assert "payload" in validation

    def test_validate_token_invalid(self):
        """Test validation of invalid token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        validation = handler.validate_token("invalid_token")

        assert validation["status"] == "error"
        assert validation["valid"] is False

    def test_validate_token_expired(self):
        """Test validation of expired token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        # Generate token with very short expiry
        token_result = handler.generate_token(payload, expires_delta=timedelta(seconds=-1))

        validation = handler.validate_token(token_result["token"])

        assert validation["status"] == "error"
        assert validation["valid"] is False
        assert "expired" in validation["message"].lower()

    def test_validate_token_does_not_expose_internals(self):
        """Test that invalid token validation returns a generic error message"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        validation = handler.validate_token("not.a.token")

        assert validation["status"] == "error"
        assert "PyJWT" not in validation["message"]
        assert "decode" not in validation["message"].lower()

    def test_refresh_access_token_success(self):
        """Test successful access token refresh"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "username": "testuser", "role": "admin"}
        refresh_result = handler.generate_refresh_token(payload)

        new_token = handler.refresh_access_token(refresh_result["refresh_token"])

        assert new_token["status"] == "success"
        assert "token" in new_token

    def test_refresh_access_token_invalid_refresh(self):
        """Test refresh with invalid refresh token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        result = handler.refresh_access_token("invalid_refresh_token")

        assert result["status"] == "error"

    def test_decode_token_without_validation(self):
        """Test token decoding without validation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        token_result = handler.generate_token(payload)

        decoded = handler.decode_token_without_validation(token_result["token"])

        assert decoded["status"] == "success"
        assert "payload" in decoded

    def test_cross_style_claim_compatibility(self):
        """Test tokens produced by JWTAuth are readable by JWTHandler and vice versa"""
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        auth = JWTAuth(secret=secret)
        handler = JWTHandler(secret_key=secret)

        # Exception-style token decoded by dict-style handler
        token = auth.create_token({"sub": "user1", "role": "client"})
        validation = handler.validate_token(token)
        assert validation["valid"] is True
        assert validation["payload"]["sub"] == "user1"
        assert validation["payload"]["user_id"] == "user1"

        # Dict-style token decoded by exception-style auth
        result = handler.generate_token({"user_id": "user2", "role": "admin"})
        payload = auth.decode_token(result["token"])
        assert payload["sub"] == "user2"
        assert payload["role"] == "admin"

    def test_jwt_restart_stability(self):
        """Test that a new handler instance with the same secret validates an existing token"""
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        handler1 = JWTHandler(secret_key=secret)
        token = handler1.generate_token({"user_id": "user123", "role": "admin"})["token"]

        handler2 = JWTHandler(secret_key=secret)
        validation = handler2.validate_token(token)

        assert validation["valid"] is True


class TestJWTNoExpiration:
    """Test tokens that are issued without an expiry claim."""

    def test_jwt_auth_omits_expiry_when_no_expiration_set(self, monkeypatch):
        """JWTAuth.create_token must not add an `exp` claim when expiry is 0."""
        monkeypatch.setenv("JWT_NO_EXPIRATION", "1")
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        auth = JWTAuth(secret=secret)

        assert auth.expiration_hours == 0
        token = auth.create_token({"sub": "user1", "role": "admin"})
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})

        assert "exp" not in payload
        assert payload["type"] == "access"

    def test_jwt_auth_zero_expiration_hours_omits_expiry(self, monkeypatch):
        """JWT_EXPIRATION_HOURS=0 is a synonym for non-expiring access tokens."""
        monkeypatch.setenv("JWT_EXPIRATION_HOURS", "0")
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        auth = JWTAuth(secret=secret)

        assert auth.expiration_hours == 0
        token = auth.create_token({"sub": "user1", "role": "admin"})
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})

        assert "exp" not in payload

    def test_jwt_handler_omits_expiry_when_no_expiration_set(self, monkeypatch):
        """JWTHandler.generate_token must not add an `exp` claim when expiry is 0."""
        monkeypatch.setenv("JWT_NO_EXPIRATION", "1")
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        handler = JWTHandler(secret_key=secret)

        assert handler.token_expiry == timedelta(0)
        assert handler.refresh_expiry == timedelta(0)

        result = handler.generate_token({"user_id": "user1", "role": "admin"})
        assert result["expires_at"] is None
        payload = jwt.decode(result["token"], secret, algorithms=["HS256"], options={"verify_aud": False})
        assert "exp" not in payload

        refresh = handler.generate_refresh_token({"user_id": "user1", "role": "admin"})
        assert refresh["expires_at"] is None
        refresh_payload = jwt.decode(refresh["refresh_token"], secret, algorithms=["HS256"], options={"verify_aud": False})
        assert "exp" not in refresh_payload


class TestJWTAuth:
    """Test JWTAuth exception-style API"""

    def test_verify_token_rejects_invalid_role(self):
        """Test verify_token rejects a token whose role does not match the required role"""
        auth = JWTAuth(secret="test_secret_key_for_testing_that_is_at_least_32_characters")
        token = auth.create_token({"sub": "user1", "role": "client"})

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token(token, required_role="admin")

        assert exc_info.value.status_code == 403


class TestJWTTypeSeparation:
    """AUTH-JWT-TYPE-CONFUSION-1 (#790): a refresh token must not authenticate
    where an access token is required, an access token must not refresh, and
    a token with no ``type`` claim is refused (fail closed — this code has
    always written the claim, so its absence means a foreign/forged token)."""

    SECRET = "test_secret_key_for_testing_that_is_at_least_32_characters"

    def _refresh_token(self, handler: JWTHandler) -> str:
        return handler.generate_refresh_token({"user_id": "user1", "role": "admin"})["refresh_token"]

    def test_refresh_token_refused_by_dict_validate(self):
        """The dict-style access path (get_current_user, websocket, agent_auth)."""
        handler = JWTHandler(secret_key=self.SECRET)
        validation = handler.validate_token(self._refresh_token(handler))
        assert validation["valid"] is False

    def test_refresh_token_refused_by_exception_decode(self):
        """The exception-style access path (verify_access_token, AuthMiddleware)."""
        handler = JWTHandler(secret_key=self.SECRET)
        auth = JWTAuth(secret=self.SECRET)
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(self._refresh_token(handler))
        assert exc_info.value.status_code == 401

    def test_access_token_refused_by_refresh(self):
        handler = JWTHandler(secret_key=self.SECRET)
        access = handler.generate_token({"user_id": "user1", "role": "admin"})["token"]
        result = handler.refresh_access_token(access)
        assert result["status"] == "error"

    def test_refresh_token_still_refreshes(self):
        handler = JWTHandler(secret_key=self.SECRET)
        result = handler.refresh_access_token(self._refresh_token(handler))
        assert result["status"] == "success"
        assert result["token"]

    def test_no_type_claim_refused_by_both_styles(self):
        token = jwt.encode({"sub": "user1", "role": "admin"}, self.SECRET, algorithm="HS256")
        handler = JWTHandler(secret_key=self.SECRET)
        assert handler.validate_token(token)["valid"] is False
        auth = JWTAuth(secret=self.SECRET)
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(token)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_refuses_refresh(self, monkeypatch):
        """The audit's reproduced path: a refresh token for admin_001 came
        back as role=admin before the fix."""
        from fastapi.security import HTTPAuthorizationCredentials

        from aitbc.auth import middleware
        from aitbc.auth.jwt import get_jwt_handler

        handler = get_jwt_handler()
        refresh = self._refresh_token(handler)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=refresh)
        with pytest.raises(HTTPException) as exc_info:
            await middleware.get_current_user(creds)
        assert exc_info.value.status_code == 401


class TestJWTRotationOverlap:
    """ROTATE-SECRET-SCRIPTS-BROKEN-1 (#852): rotate_jwt_secret.sh performs a
    real dual-secret overlap — JWT_SECRET_NEW and JWT_SECRET_PREVIOUS verify
    tokens but never sign them."""

    OLD = "old_secret_for_rotation_testing_at_least_32_chars"
    NEW = "new_secret_for_rotation_testing_at_least_32_chars"

    def test_new_env_secret_verifies_during_overlap(self, monkeypatch):
        """Phase 1 of the script: JWT_SECRET old + JWT_SECRET_NEW new."""
        monkeypatch.setenv("JWT_SECRET_NEW", self.NEW)
        handler = JWTHandler(secret_key=self.OLD)

        token = jwt.encode({"sub": "u1", "type": "access"}, self.NEW, algorithm="HS256")
        assert handler.validate_token(token)["valid"] is True

        auth = JWTAuth(secret=self.OLD)
        assert auth.decode_token(token)["sub"] == "u1"

    def test_previous_env_secret_verifies_after_flip(self, monkeypatch):
        """Phase 4+: JWT_SECRET new, retired secret in JWT_SECRET_PREVIOUS."""
        monkeypatch.setenv("JWT_SECRET_PREVIOUS", self.OLD)
        handler = JWTHandler(secret_key=self.NEW)

        old_token = jwt.encode({"sub": "u1", "type": "access"}, self.OLD, algorithm="HS256")
        assert handler.validate_token(old_token)["valid"] is True
        assert JWTAuth(secret=self.NEW).decode_token(old_token)["sub"] == "u1"

    def test_previous_accepts_comma_separated_list(self, monkeypatch):
        older = "older_secret_for_rotation_testing_at_least_32ch"
        monkeypatch.setenv("JWT_SECRET_PREVIOUS", f"  {self.OLD} , {older} ")
        handler = JWTHandler(secret_key=self.NEW)
        for secret in (self.OLD, older):
            token = jwt.encode({"sub": "u1", "type": "access"}, secret, algorithm="HS256")
            assert handler.validate_token(token)["valid"] is True

    def test_extras_never_sign(self, monkeypatch):
        """Tokens are always signed with the primary secret."""
        monkeypatch.setenv("JWT_SECRET_PREVIOUS", self.OLD)
        handler = JWTHandler(secret_key=self.NEW)
        token = handler.generate_token({"user_id": "u1"})["token"]
        assert jwt.decode(token, self.NEW, algorithms=["HS256"], options={"verify_aud": False})["sub"] == "u1"
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, self.OLD, algorithms=["HS256"], options={"verify_aud": False})

    def test_unknown_secret_still_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_PREVIOUS", self.OLD)
        handler = JWTHandler(secret_key=self.NEW)
        foreign = jwt.encode({"sub": "u1", "type": "access"}, "foreign_secret_at_least_32_chars_xx", algorithm="HS256")
        assert handler.validate_token(foreign)["valid"] is False
        with pytest.raises(HTTPException):
            JWTAuth(secret=self.NEW).decode_token(foreign)


class TestAPIKeyManager:
    """Test APIKeyManager class"""

    def test_api_key_manager_initialization(self):
        """Test API key manager initialization"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        assert manager.storage_path == "/tmp/test_api_keys.json"
        assert isinstance(manager.api_keys, dict)

    def test_generate_api_key_success(self):
        """Test successful API key generation"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        result = manager.generate_api_key("user123", ["read", "write"])

        assert result["status"] == "success"
        assert "api_key" in result
        assert len(result["api_key"]) > 20
        assert result["permissions"] == ["read", "write"]

    def test_generate_api_key_no_permissions(self):
        """Test API key generation without permissions"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        result = manager.generate_api_key("user123")

        assert result["status"] == "success"
        assert result["permissions"] == []

    def test_api_keys_are_not_stored_plaintext(self):
        """Test that generated API keys are stored as one-way digests"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        plaintext_key = gen_result["api_key"]
        assert plaintext_key not in manager.api_keys
        assert manager._hash_key(plaintext_key) in manager.api_keys

    def test_validate_api_key_valid(self):
        """Test validation of valid API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        validate_result = manager.validate_api_key(gen_result["api_key"])

        assert validate_result["status"] == "success"
        assert validate_result["valid"] is True
        assert validate_result["user_id"] == "user123"
        assert validate_result["permissions"] == ["read"]

    def test_validate_api_key_invalid(self):
        """Test validation of invalid API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        validate_result = manager.validate_api_key("invalid_key")

        assert validate_result["status"] == "error"
        assert validate_result["valid"] is False

    def test_revoke_api_key_success(self):
        """Test successful API key revocation"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        revoke_result = manager.revoke_api_key(gen_result["api_key"])

        assert revoke_result["status"] == "success"
        assert "revoked" in revoke_result["message"].lower()

    def test_revoke_api_key_not_found(self):
        """Test revocation of non-existent API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        revoke_result = manager.revoke_api_key("nonexistent_key")

        assert revoke_result["status"] == "error"
        assert "not found" in revoke_result["message"].lower()

    def test_api_key_usage_tracking(self):
        """Test that API key usage is tracked"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        # First validation
        manager.validate_api_key(gen_result["api_key"])
        # Second validation
        validate_result = manager.validate_api_key(gen_result["api_key"])

        assert validate_result["status"] == "success"
        # Usage count should be incremented
        assert validate_result["usage_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestAPIKeyStoreAtomicity:
    """APIKEY-STORE-ATOMIC-1 (#792): a corrupt store is refused (never read
    as empty, never overwritten), saves are atomic 0600, and a successful
    validate no longer rewrites the file."""

    SECRET_PATH_KEYS = ("user1", ["read"])

    def _manager(self, tmp_path):
        return APIKeyManager(storage_path=str(tmp_path / "api_keys.json"))

    def test_corrupt_store_is_quarantined_and_refused(self, tmp_path, caplog):
        store = tmp_path / "api_keys.json"
        store.write_text('{"abc123": {"user_id": "u", "permi')  # truncated write
        from aitbc.auth.api_key import CorruptKeyStoreError

        with pytest.raises(CorruptKeyStoreError):
            self._manager(tmp_path)
        corrupt = list(tmp_path.glob("api_keys.json*.corrupt"))
        assert corrupt, "unreadable store was not preserved"
        assert store.read_bytes() == b'{"abc123": {"user_id": "u", "permi'
        assert any(r.levelname == "CRITICAL" for r in caplog.records)

    def test_corrupt_after_construction_refuses_operations(self, tmp_path):
        manager = self._manager(tmp_path)
        gen = manager.generate_api_key("user1", ["read"])
        assert gen["status"] == "success"
        (tmp_path / "api_keys.json").write_text("{oops")
        assert manager.validate_api_key(gen["api_key"])["valid"] is False
        assert manager.generate_api_key("user2")["status"] == "error"
        assert manager.revoke_api_key(gen["api_key"])["status"] == "error"
        # …and the corrupt file is still there, not silently overwritten.
        assert (tmp_path / "api_keys.json").read_text() == "{oops"

    def test_save_is_atomic_and_0600(self, tmp_path, monkeypatch):
        import os
        import stat

        replaces = []
        real_replace = os.replace
        monkeypatch.setattr("aitbc.auth.api_key.os.replace", lambda s, d: replaces.append((s, d)) or real_replace(s, d))

        manager = self._manager(tmp_path)
        assert manager.generate_api_key("user1")["status"] == "success"

        assert replaces, "save did not go through os.replace"
        store = tmp_path / "api_keys.json"
        assert stat.S_IMODE(store.stat().st_mode) == 0o600
        assert not list(tmp_path.glob(".api_keys.*.tmp")), "temp file left behind"

    def test_validate_does_not_rewrite_the_store(self, tmp_path, monkeypatch):
        manager = self._manager(tmp_path)
        gen = manager.generate_api_key("user1")
        key = gen["api_key"]
        saves = []
        real_save = manager._save_keys
        monkeypatch.setattr(manager, "_save_keys", lambda: saves.append(1) or real_save())

        first = manager.validate_api_key(key)
        second = manager.validate_api_key(key)

        assert first["valid"] is True and second["valid"] is True
        assert second["usage_count"] == 2  # persisted + pending, monotonic
        assert saves == [], "a successful validate rewrote the key file"

    def test_pending_usage_flushes_on_interval(self, tmp_path, monkeypatch):
        import json

        manager = self._manager(tmp_path)
        key = manager.generate_api_key("user1")["api_key"]
        manager._usage_flushed_at = 0  # force the next validate to flush
        manager.validate_api_key(key)

        data = json.loads((tmp_path / "api_keys.json").read_text())
        row = next(iter(data.values()))
        assert row["usage_count"] == 1 and row["last_used"] is not None
        assert manager._usage == {}


class TestJWTIssAudBinding:
    """R12-HARDEN-1 (#1233): iss/aud claims — minted always, enforced only
    when JWT_ENFORCE_ISS_AUD is set (dormant until #1185 lands)."""

    SECRET = "test_secret_key_for_testing_that_is_at_least_32_characters"

    def _handler(self):
        return JWTHandler(self.SECRET)

    def _clean_env(self, monkeypatch):
        for var in ("JWT_ISSUER", "JWT_AUDIENCE", "JWT_EXPECTED_ISSUER", "JWT_ENFORCE_ISS_AUD", "SERVICE_NAME", "APP_NAME"):
            monkeypatch.delenv(var, raising=False)

    def test_mint_writes_iss_aud_defaults(self, monkeypatch):
        self._clean_env(monkeypatch)
        result = self._handler().generate_token({"sub": "u1", "role": "admin"})
        payload = jwt.decode(result["token"], self.SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert payload["iss"] == "aitbc" and payload["aud"] == "aitbc"

    def test_mint_honors_env_and_explicit_claims(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("SERVICE_NAME", "coordinator-api")
        monkeypatch.setenv("JWT_AUDIENCE", "aitbc-clients")
        handler = self._handler()
        result = handler.generate_token({"sub": "u1", "role": "admin"})
        payload = jwt.decode(result["token"], self.SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert payload["iss"] == "coordinator-api" and payload["aud"] == "aitbc-clients"
        # explicit claims are not overridden
        result2 = handler.generate_token({"sub": "u1", "iss": "custom", "aud": ["x"]})
        payload2 = jwt.decode(result2["token"], self.SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert payload2["iss"] == "custom" and payload2["aud"] == ["x"]

    def test_refresh_token_carries_iss_aud(self, monkeypatch):
        self._clean_env(monkeypatch)
        handler = self._handler()
        refresh = handler.generate_refresh_token({"sub": "u1", "role": "admin"})
        payload = jwt.decode(refresh["refresh_token"], self.SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert payload["iss"] == "aitbc" and payload["type"] == "refresh"
        # refreshed access token is re-minted locally -> local iss/aud
        access = handler.refresh_access_token(refresh["refresh_token"])
        ap = jwt.decode(access["token"], self.SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert ap["iss"] == "aitbc" and ap["type"] == "access"

    def test_enforcement_off_by_default_accepts_foreign_iss(self, monkeypatch):
        self._clean_env(monkeypatch)
        handler = self._handler()
        result = handler.generate_token({"sub": "u1", "role": "admin", "iss": "other-svc"})
        validation = handler.validate_token(result["token"])
        assert validation["valid"] is True

    def test_enforcement_rejects_wrong_issuer_and_audience(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "true")
        monkeypatch.setenv("JWT_ISSUER", "coordinator-api")
        monkeypatch.setenv("JWT_AUDIENCE", "coordinator-api")
        handler = self._handler()
        good = handler.generate_token({"sub": "u1", "role": "admin"})
        assert handler.validate_token(good["token"])["valid"] is True
        bad_iss = handler.generate_token({"sub": "u1", "role": "admin", "iss": "agent-coordinator"})
        assert handler.validate_token(bad_iss["token"])["valid"] is False
        bad_aud = handler.generate_token({"sub": "u1", "role": "admin", "aud": "other"})
        assert handler.validate_token(bad_aud["token"])["valid"] is False
        # legacy token with no iss/aud is refused when enforcement is on
        legacy = jwt.encode({"sub": "u1", "role": "admin", "type": "access"}, self.SECRET, algorithm="HS256")
        assert handler.validate_token(legacy)["valid"] is False

    def test_jwt_auth_exception_style_enforcement(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "true")
        monkeypatch.setenv("JWT_ISSUER", "svc-a")
        monkeypatch.setenv("JWT_AUDIENCE", "svc-a")
        auth = JWTAuth(secret=self.SECRET)
        token = auth.create_token({"sub": "u1", "role": "admin"})
        assert auth.decode_token(token)["iss"] == "svc-a"
        foreign = jwt.encode(
            {"sub": "u1", "role": "admin", "type": "access", "iss": "svc-b", "aud": "svc-b"}, self.SECRET, algorithm="HS256"
        )
        with pytest.raises(HTTPException):
            auth.decode_token(foreign)
