"""Tests for SECRET-RELOAD-1 (#1776): in-process auth-secret reload."""

import os
import signal
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from aitbc.auth.jwt import JWTAuth, JWTHandler, get_jwt_auth  # noqa: E402
import aitbc.auth.secret_reload as secret_reload  # noqa: E402
from aitbc.auth.secret_reload import (  # noqa: E402
    AUTH_SECRET_VARS,
    reload_auth_secrets,
)

SECRET_A = "a" * 48
SECRET_B = "b" * 48
SECRET_C = "c" * 48


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in AUTH_SECRET_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("AITBC_AUTH_ENV_FILES", raising=False)
    monkeypatch.delenv("AITBC_SECRETS_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    secret_reload._FILE_SOURCED.clear()
    yield
    secret_reload._FILE_SOURCED.clear()


def _write_env(path, lines):
    path.write_text("\n".join(lines))
    return str(path)


class TestEnvFileParsing:
    def test_parses_comments_quotes_export_last_wins(self, tmp_path):
        f = _write_env(
            tmp_path / "secrets.env",
            [
                "# comment",
                "export JWT_SECRET='" + SECRET_A + "'",
                'API_KEY_HASH_SECRET="key-material-123456"',
                "UNRELATED_VAR=should-not-apply",
                "JWT_SECRET=" + SECRET_B,  # last wins
                "",  # missing trailing newline handled by splitlines
            ],
        )
        report = reload_auth_secrets(env_files=[f])
        assert report.ok
        assert os.environ["JWT_SECRET"] == SECRET_B
        assert os.environ["API_KEY_HASH_SECRET"] == "key-material-123456"
        assert "UNRELATED_VAR" not in os.environ

    def test_missing_trailing_newline(self, tmp_path):
        p = tmp_path / "secrets.env"
        p.write_text("JWT_SECRET=" + SECRET_A)  # no trailing newline
        report = reload_auth_secrets(env_files=[str(p)])
        assert report.ok
        assert os.environ["JWT_SECRET"] == SECRET_A


class TestFailClosed:
    def test_malformed_file_keeps_old_secret(self, tmp_path, monkeypatch):
        good = _write_env(tmp_path / "good.env", ["JWT_SECRET=" + SECRET_A])
        reload_auth_secrets(env_files=[good])
        assert os.environ["JWT_SECRET"] == SECRET_A

        bad = tmp_path / "bad.env"
        bad.write_text("JWT_SECRET=" + SECRET_B + "\nnot-a-key-value-line\n")
        report = reload_auth_secrets(env_files=[str(bad)])
        assert not report.ok
        assert os.environ["JWT_SECRET"] == SECRET_A  # unchanged

    def test_weak_secret_rejected(self, tmp_path):
        f = _write_env(tmp_path / "weak.env", ["JWT_SECRET=short"])
        report = reload_auth_secrets(env_files=[f])
        assert not report.ok
        assert "JWT_SECRET" not in os.environ

    def test_default_secret_rejected(self, tmp_path):
        f = _write_env(tmp_path / "def.env", ["JWT_SECRET=change-me-in-production" + "x" * 20])
        # pad so length passes but value stays a known default prefix? use exact default
        f = _write_env(tmp_path / "def.env", ["JWT_SECRET=change-me-in-production"])
        report = reload_auth_secrets(env_files=[f])
        assert not report.ok

    def test_missing_file_is_skipped_not_fatal(self, tmp_path):
        report = reload_auth_secrets(env_files=[str(tmp_path / "absent.env")])
        assert report.ok
        assert report.files_read == []


class TestJWTInstanceRefresh:
    def test_env_backed_jwt_auth_refreshes(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        reload_auth_secrets()
        auth = JWTAuth()
        assert auth.secret == SECRET_A

        # rotate: file now carries SECRET_B
        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_B])
        report = reload_auth_secrets()
        assert report.ok
        assert auth.secret == SECRET_B

    def test_explicit_secret_instance_not_refreshed(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        reload_auth_secrets()
        auth = JWTAuth(secret=SECRET_C)
        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_B])
        reload_auth_secrets()
        assert auth.secret == SECRET_C

    def test_jwt_handler_and_verify_set_refresh(self, tmp_path, monkeypatch):
        f = _write_env(
            tmp_path / "secrets.env",
            ["JWT_SECRET=" + SECRET_A, "JWT_SECRET_NEW=" + SECRET_C],
        )
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        reload_auth_secrets()
        handler = JWTHandler()
        assert handler.secret_key == SECRET_A
        assert SECRET_C in handler.extra_secrets

        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_B])
        reload_auth_secrets()
        assert handler.secret_key == SECRET_B
        assert SECRET_C not in handler.extra_secrets  # NEW var gone from file

    def test_verify_accepts_new_secret_after_reload(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        monkeypatch.setenv("JWT_NO_EXPIRATION", "1")
        reload_auth_secrets()
        auth = JWTAuth()
        token_old = auth.create_token({"sub": "u1", "role": "client"})

        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_B, "JWT_SECRET_PREVIOUS=" + SECRET_A])
        reload_auth_secrets()
        # old token still verifies via PREVIOUS; new tokens sign with B
        assert auth.verify_token(token_old)["sub"] == "u1"
        token_new = auth.create_token({"sub": "u2", "role": "client"})
        assert auth.verify_token(token_new)["sub"] == "u2"

    def test_singleton_refreshes(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        reload_auth_secrets()
        singleton = get_jwt_auth()
        assert singleton.secret == SECRET_A
        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_B])
        reload_auth_secrets()
        assert get_jwt_auth().secret == SECRET_B

    def test_failed_reload_keeps_instance_secrets(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "secrets.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f)
        reload_auth_secrets()
        auth = JWTAuth()
        _write_env(tmp_path / "secrets.env", ["JWT_SECRET=weak"])
        report = reload_auth_secrets()
        assert not report.ok
        assert auth.secret == SECRET_A


class TestEnvFileSelection:
    def test_aitbc_secrets_env_single_file_override(self, tmp_path, monkeypatch):
        f = _write_env(tmp_path / "custom.env", ["JWT_SECRET=" + SECRET_A])
        monkeypatch.setenv("AITBC_SECRETS_ENV", f)
        report = reload_auth_secrets()
        assert report.ok
        assert os.environ["JWT_SECRET"] == SECRET_A

    def test_colon_separated_files_last_wins(self, tmp_path, monkeypatch):
        f1 = _write_env(tmp_path / "a.env", ["JWT_SECRET=" + SECRET_A])
        f2 = _write_env(tmp_path / "b.env", ["API_KEY_HASH_SECRET=hash-secret-1234567890"])
        monkeypatch.setenv("AITBC_AUTH_ENV_FILES", f"{f1}:{f2}")
        report = reload_auth_secrets()
        assert report.ok
        assert os.environ["JWT_SECRET"] == SECRET_A
        assert os.environ["API_KEY_HASH_SECRET"] == "hash-secret-1234567890"


class TestSignalInstall:
    def test_install_auth_reload_signal(self):
        from aitbc.auth.secret_reload import install_auth_reload_signal

        assert install_auth_reload_signal(signal.SIGUSR1) is True
        signal.signal(signal.SIGUSR1, signal.SIG_DFL)  # restore
