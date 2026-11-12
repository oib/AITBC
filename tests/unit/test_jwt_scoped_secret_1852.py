"""#1852: per-service JWT secrets — JWT_SECRET_<SCOPE> isolation.

Pre-fix every service resolved the same fleet ``JWT_SECRET`` (written
once into ``blockchain-secrets.env`` by setup.sh), so a token minted by
agent-coordinator verified at coordinator-api and vice versa — one env
leak replayed fleet-wide. ``_service_scope`` derives a scope from the
same identity chain as iss/aud (``JWT_ISSUER`` > ``SERVICE_NAME`` >
``APP_NAME``); when set, ``JWT_SECRET_<SCOPE>`` wins over the shared
secret and rotation extras are scoped too.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from aitbc.auth.jwt import JWTAuth, JWTHandler, _resolve_secret, _service_scope  # noqa: E402

SHARED = "s" * 48
SVC_A = "a" * 48
SVC_B = "b" * 48
OLD_A = "o" * 48
NEW_A = "n" * 48

_SCOPE_VARS = ("JWT_ISSUER", "SERVICE_NAME", "APP_NAME")
_SECRET_VARS = (
    "JWT_SECRET",
    "JWT_SECRET_KEY",
    "JWT_SECRET_NEW",
    "JWT_SECRET_PREVIOUS",
    "JWT_SECRET_COORDINATOR_API",
    "JWT_SECRET_COORDINATOR_API_NEW",
    "JWT_SECRET_COORDINATOR_API_PREVIOUS",
    "JWT_SECRET_AGENT_COORDINATOR",
    "JWT_SECRET_AGENT_COORDINATOR_PREVIOUS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _SCOPE_VARS + _SECRET_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    yield


def _scoped_env(monkeypatch, issuer: str):
    monkeypatch.setenv("JWT_ISSUER", issuer)


class TestScopeResolution:
    def test_scope_from_jwt_issuer(self, monkeypatch):
        _scoped_env(monkeypatch, "coordinator-api")
        assert _service_scope() == "COORDINATOR_API"

    def test_scope_falls_back_to_service_name(self, monkeypatch):
        monkeypatch.setenv("SERVICE_NAME", "agent.coordinator")
        assert _service_scope() == "AGENT_COORDINATOR"

    def test_no_identity_means_unscoped(self):
        assert _service_scope() == ""

    def test_jwt_issuer_wins_over_service_name(self, monkeypatch):
        monkeypatch.setenv("JWT_ISSUER", "explicit-svc")
        monkeypatch.setenv("SERVICE_NAME", "other-svc")
        assert _service_scope() == "EXPLICIT_SVC"


class TestScopedSecretResolution:
    def test_scoped_secret_wins_over_shared(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        assert _resolve_secret() == SVC_A

    def test_falls_back_to_shared_when_scoped_absent(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        assert _resolve_secret() == SHARED

    def test_scoped_secret_ignored_by_other_service(self, monkeypatch):
        """A secret scoped to coordinator-api must not leak into
        agent-coordinator's resolution."""
        monkeypatch.setenv("JWT_SECRET", SHARED)
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        _scoped_env(monkeypatch, "agent-coordinator")
        assert _resolve_secret() == SHARED

    def test_weak_scoped_secret_fails_closed(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", "short")
        with pytest.raises(ValueError, match="32 characters"):
            _resolve_secret()


class TestCrossServiceReplay:
    def test_token_does_not_verify_across_services(self, monkeypatch):
        """The core #1852 property: a token minted under service A's
        scoped secret is invalid at service B."""
        monkeypatch.setenv("JWT_SECRET", SHARED)
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        monkeypatch.setenv("JWT_SECRET_AGENT_COORDINATOR", SVC_B)

        _scoped_env(monkeypatch, "coordinator-api")
        coord = JWTAuth()
        token = coord.create_token({"sub": "admin", "role": "admin"})

        _scoped_env(monkeypatch, "agent-coordinator")
        agent = JWTAuth()
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            agent.decode_token(token)

    def test_same_service_roundtrip_still_works(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        auth = JWTAuth()
        token = auth.create_token({"sub": "u1", "role": "client"})
        assert auth.decode_token(token)["sub"] == "u1"


class TestScopedRotationExtras:
    def test_scoped_previous_accepted_when_scoped_active(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API_PREVIOUS", OLD_A)
        auth = JWTAuth()
        # Token minted under the retired scoped secret still verifies.
        retired = JWTAuth(secret=OLD_A)
        token = retired.create_token({"sub": "u", "role": "client"})
        assert auth.decode_token(token)["sub"] == "u"

    def test_global_previous_ignored_when_scoped_active(self, monkeypatch):
        """Fail closed: a scoped service must not accept fleet-secret
        tokens via the shared rotation overlap."""
        monkeypatch.setenv("JWT_SECRET", SHARED)
        monkeypatch.setenv("JWT_SECRET_PREVIOUS", OLD_A)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        auth = JWTAuth()
        fleet_retired = JWTAuth(secret=OLD_A)
        token = fleet_retired.create_token({"sub": "u", "role": "client"})
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            auth.decode_token(token)

    def test_scoped_new_accepted_for_verify_not_signing(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "coordinator-api")
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API", SVC_A)
        monkeypatch.setenv("JWT_SECRET_COORDINATOR_API_NEW", NEW_A)
        auth = JWTAuth()
        assert auth.secret == SVC_A  # signing stays on primary
        incoming = JWTAuth(secret=NEW_A)
        token = incoming.create_token({"sub": "u", "role": "client"})
        assert auth.decode_token(token)["sub"] == "u"


class TestDictStyleHandler:
    def test_handler_uses_scoped_secret(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", SHARED)
        _scoped_env(monkeypatch, "agent-coordinator")
        monkeypatch.setenv("JWT_SECRET_AGENT_COORDINATOR", SVC_B)
        handler = JWTHandler()
        assert handler.secret_key == SVC_B
        result = handler.generate_token({"sub": "agent1", "role": "agent"})
        assert result["status"] == "success"
        check = handler.validate_token(result["token"])
        assert check.get("valid") or check.get("status") == "success"


class TestSecretReloadScopedVars:
    def test_scoped_var_reloads_from_env_file(self, tmp_path, monkeypatch):
        import aitbc.auth.secret_reload as secret_reload

        secret_reload._FILE_SOURCED.clear()
        f = tmp_path / "secrets.env"
        f.write_text(f"JWT_SECRET_COORDINATOR_API={SVC_A}\nJWT_SECRET={SHARED}\n")
        report = secret_reload.reload_auth_secrets(env_files=[str(f)])
        assert report.ok, report.errors
        assert os.environ["JWT_SECRET_COORDINATOR_API"] == SVC_A

    def test_weak_scoped_secret_rejected_on_reload(self, tmp_path, monkeypatch):
        import aitbc.auth.secret_reload as secret_reload

        secret_reload._FILE_SOURCED.clear()
        f = tmp_path / "secrets.env"
        f.write_text("JWT_SECRET_COORDINATOR_API=short\nJWT_SECRET=" + SHARED + "\n")
        report = secret_reload.reload_auth_secrets(env_files=[str(f)])
        assert not report.ok
        assert any("JWT_SECRET_COORDINATOR_API" in e for e in report.errors)

    def test_reload_cannot_drop_last_jwt_primary(self, tmp_path, monkeypatch):
        import aitbc.auth.secret_reload as secret_reload

        secret_reload._FILE_SOURCED.clear()
        # First load establishes JWT_SECRET as file-sourced primary.
        f1 = tmp_path / "a.env"
        f1.write_text(f"JWT_SECRET={SHARED}\n")
        assert secret_reload.reload_auth_secrets(env_files=[str(f1)]).ok
        # Second file drops it entirely -> must refuse.
        f2 = tmp_path / "b.env"
        f2.write_text("API_KEY_HASH_SECRET=" + "k" * 24 + "\n")
        report = secret_reload.reload_auth_secrets(env_files=[str(f2)])
        assert not report.ok
        assert "last JWT primary" in report.errors[0]
