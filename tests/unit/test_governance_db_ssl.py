"""Unit tests for the governance database's TLS configuration.

`aitbc.database.ssl_args.build_ssl_arg` exists because of an outage, not because of a feature
request: under `ProtectHome=yes`, asyncpg's own sslmode handling stats
`~/.postgresql/...` and lets the resulting `PermissionError` escape, so
governance could not open a connection at all on a host whose service user's
home lives under /home. The host was patched with a `PGSSLMODE=disable` that
the repo knew nothing about; these tests pin the in-repo replacement,
shared via `aitbc.database.ssl_args` since pool-hub needed the same protection.

Two properties are worth a test here. The resolution *order*, because a rebuilt
host that loses its environment file must still land somewhere safe; and the
fact that what reaches asyncpg is never a mode **string**, because a string is
exactly what sends asyncpg back into the home-directory lookup that failed.
"""

from __future__ import annotations

import pathlib
import ssl

import pytest

from governance_service import storage

from aitbc.database import ssl_args

ENCRYPT_ONLY = ("allow", "prefer", "require")
VERIFYING = ("verify-ca", "verify-full")
ALL_MODES = ("disable", *ENCRYPT_ONLY, *VERIFYING)


@pytest.fixture(autouse=True)
def _clear_ssl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither variable may leak in from the shell running the tests."""
    monkeypatch.delenv("DB_SSLMODE", raising=False)
    monkeypatch.delenv("PGSSLMODE", raising=False)


# --- mode resolution -------------------------------------------------------


def test_default_is_asyncpg_default() -> None:
    """Unconfigured must mean "what asyncpg would have done", never a downgrade."""
    assert ssl_args.resolve_sslmode() == "prefer"


def test_db_sslmode_wins_over_pgsslmode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGSSLMODE", "disable")
    monkeypatch.setenv("DB_SSLMODE", "require")
    assert ssl_args.resolve_sslmode() == "require"


def test_pgsslmode_is_honoured_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fleet already carries PGSSLMODE; adopting it is what makes this a no-op deploy."""
    monkeypatch.setenv("PGSSLMODE", "disable")
    assert ssl_args.resolve_sslmode() == "disable"


def test_empty_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SSLMODE", "")
    monkeypatch.setenv("PGSSLMODE", "require")
    assert ssl_args.resolve_sslmode() == "require"


def test_value_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SSLMODE", "  VERIFY_FULL ")
    assert ssl_args.resolve_sslmode() == "verify-full"


# --- context construction --------------------------------------------------


def test_disable_yields_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SSLMODE", "disable")
    # `is False`, not merely falsy: asyncpg distinguishes False from None.
    assert ssl_args.build_ssl_arg() is False


@pytest.mark.parametrize("mode", ENCRYPT_ONLY)
def test_encrypting_modes_do_not_verify(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SSLMODE", mode)
    context = ssl_args.build_ssl_arg()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_NONE
    assert context.check_hostname is False


@pytest.mark.parametrize(("mode", "checks_hostname"), [("verify-ca", False), ("verify-full", True)])
def test_verifying_modes_require_a_certificate(mode: str, checks_hostname: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_SSLMODE", mode)
    context = ssl_args.build_ssl_arg()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is checks_hostname


def test_unknown_mode_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Better to refuse to start than to guess at a security setting."""
    monkeypatch.setenv("DB_SSLMODE", "verify-everything")
    with pytest.raises(ValueError, match="verify-everything"):
        ssl_args.build_ssl_arg()


# --- the regression itself -------------------------------------------------


@pytest.mark.parametrize("mode", ALL_MODES)
def test_asyncpg_never_receives_a_mode_string(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of the helper.

    asyncpg gates its home-directory lookups on `isinstance(ssl, (str, SSLMode))`.
    Hand it a bool or a ready-made context and that branch never runs; hand it
    `"require"` and the outage is back, TLS settings notwithstanding.
    """
    monkeypatch.setenv("DB_SSLMODE", mode)
    assert isinstance(ssl_args.build_ssl_arg(), (bool, ssl.SSLContext))
    assert not isinstance(ssl_args.build_ssl_arg(), str)


@pytest.mark.parametrize("mode", ALL_MODES)
def test_no_mode_touches_the_home_directory(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Models the failure directly: an unreadable home must not matter.

    This proves our own resolution is home-independent. That asyncpg's is too,
    given what we hand it, is the assertion above.
    """

    def _refuse() -> pathlib.Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(pathlib.Path, "home", staticmethod(_refuse))
    monkeypatch.setenv("DB_SSLMODE", mode)
    ssl_args.build_ssl_arg()


# --- wiring ----------------------------------------------------------------


@pytest.fixture
def recorded_engine(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Capture create_async_engine kwargs without needing a database driver."""
    calls: list[dict[str, object]] = []

    def _record(url: str, **kwargs: object) -> object:
        calls.append({"url": url, **kwargs})
        return object()

    monkeypatch.setattr(storage, "create_async_engine", _record)
    return calls


def test_postgres_engine_carries_the_ssl_arg(
    recorded_engine: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DB_TYPE", "postgresql")
    monkeypatch.setenv("DB_SSLMODE", "require")
    storage._create_engine()
    (call,) = recorded_engine
    assert isinstance(call["connect_args"], dict)
    assert isinstance(call["connect_args"]["ssl"], ssl.SSLContext)


def test_sqlite_engine_gets_no_ssl_arg(recorded_engine: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch) -> None:
    """aiosqlite would reject the argument outright."""
    monkeypatch.setenv("DB_TYPE", "sqlite")
    storage._create_engine()
    (call,) = recorded_engine
    assert "connect_args" not in call


# --- URL construction ------------------------------------------------------
#
# `_build_database_url` interpolates DB_USER/DB_PASS into the URL's userinfo.
# Raw interpolation lets a password containing `@` or `/` move the host and
# path boundaries, so the driver silently dials the wrong endpoint. The fix is
# percent-encoding with `safe=""`, which these tests pin through
# `urllib.parse`/`sqlalchemy.engine.make_url` rather than by string-matching.


@pytest.fixture
def postgres_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DB_TYPE", "postgresql")
    return monkeypatch


def test_plain_credentials_are_untouched(postgres_env: pytest.MonkeyPatch) -> None:
    postgres_env.setenv("DB_USER", "aitbc")
    postgres_env.setenv("DB_PASS", "s3cret")
    postgres_env.setenv("DB_HOST", "db.internal")
    url = storage._build_database_url()
    assert url == "postgresql+asyncpg://aitbc:s3cret@db.internal:5432/aitbc_governance"


def test_a_password_with_at_and_slash_cannot_move_the_host(postgres_env: pytest.MonkeyPatch) -> None:
    """The regression: `p@ss/word` unquoted parses host=`ss` path=`word@db...`."""
    from urllib.parse import unquote

    from sqlalchemy.engine import make_url

    postgres_env.setenv("DB_USER", "aitbc")
    postgres_env.setenv("DB_PASS", "p@ss/word")
    postgres_env.setenv("DB_HOST", "db.internal")
    postgres_env.setenv("DB_NAME", "gov")
    parsed = make_url(storage._build_database_url())
    assert parsed.host == "db.internal"
    # SQLAlchemy does not guarantee whether `password` comes back decoded;
    # unquote() is a no-op when it already is, so this holds either way.
    assert unquote(parsed.password or "") == "p@ss/word"
    assert parsed.database == "gov"


def test_a_user_with_at_is_quoted_too(postgres_env: pytest.MonkeyPatch) -> None:
    from urllib.parse import unquote

    from sqlalchemy.engine import make_url

    postgres_env.setenv("DB_USER", "svc@gov")
    postgres_env.setenv("DB_PASS", "x")
    parsed = make_url(storage._build_database_url())
    assert unquote(parsed.username or "") == "svc@gov"
    assert parsed.host == "localhost"


def test_empty_password_stays_empty(postgres_env: pytest.MonkeyPatch) -> None:
    postgres_env.delenv("DB_PASS", raising=False)
    url = storage._build_database_url()
    assert url.startswith("postgresql+asyncpg://aitbc:@")
