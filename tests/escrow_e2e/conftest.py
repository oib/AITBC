"""ESCROW-E2E-TEST-1 fixtures (Refs #463).

Unlike ``apps/coordinator-api/tests``, this conftest deliberately does NOT
set ``TEST_MODE`` — the app is built with ``auth_enabled`` so the real
``AuthMiddleware`` and the committed ``ROUTE_SECURITY_MATRIX`` guard every
request. That is the deny-by-default regression this suite exists to see.
"""

from __future__ import annotations

import os
import sys

# Snapshot the environment this conftest is about to overwrite — the writes
# are needed for exactly one window: the coordinator_api.config import below,
# which instantiates ``settings`` once. Restoring right after those imports
# keeps the rest of a shared pytest session (e.g. tests/integration, whose
# conftest setdefaults TEST_MODE) out of this suite's env.
_ENV_KEYS = (
    "URL",
    "JWT_SECRET",
    "AUTH_ENABLED",
    "CHAIN_ID",
    "BLOCKCHAIN_RPC_URL",
    "EXPLORER_API_URL",
    "MARKET_STATS_URL",
    "ECON_STATS_URL",
    "MARKET_HEALTH_URL",
    "MARKET_HEALTH_URL_ALT",
    "COORDINATOR_HEALTH_URL",
    "TEST_MODE",
)
_PRE_ENV = {k: os.environ.get(k) for k in _ENV_KEYS}

# And the settings singleton's fields, when the module already exists —
# restored in place at suite teardown so a later suite never inherits this
# suite's production-shaped app config (that leak is what 401'd
# tests/integration when both ran in one session).
_SETTINGS_FIELDS = ("test_mode", "auth_enabled", "jwt_secret", "url", "blockchain_rpc_url")
_HAD_CONFIG = "coordinator_api.config" in sys.modules
_ABSENT = object()
_PRE_SETTINGS: dict[str, object] | None = None
if _HAD_CONFIG:
    from coordinator_api.config import settings as _pre_settings

    _PRE_SETTINGS = {f: getattr(_pre_settings, f, _ABSENT) for f in _SETTINGS_FIELDS}
    del _pre_settings

# Environment first — coordinator_api.config.settings is instantiated at
# import time, so every variable it reads must be in place beforehand.
# Hard-assign, not setdefault: when the coordinator test conftest already ran
# in the same pytest session its values would win and this suite would build
# an app against the wrong DB/secret/RPC URL.
os.environ["URL"] = "sqlite:////tmp/aitbc-escrow-e2e.db"
os.environ["JWT_SECRET"] = "escrow-e2e-test-secret-key-material-0123456789"
os.environ["AUTH_ENABLED"] = "true"
os.environ["CHAIN_ID"] = "ait-testchain"
os.environ["BLOCKCHAIN_RPC_URL"] = "http://settlement-node.test"
os.environ.setdefault("EXPLORER_API_URL", "http://127.0.0.1:8100/health")
os.environ.setdefault("MARKET_STATS_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("ECON_STATS_URL", "http://127.0.0.1:8104/health")
os.environ.setdefault("MARKET_HEALTH_URL", "http://127.0.0.1:8102/health")
os.environ.setdefault("MARKET_HEALTH_URL_ALT", "http://127.0.0.1:8104/health")
os.environ.setdefault("COORDINATOR_HEALTH_URL", "http://127.0.0.1:8203/health")
os.environ.pop("TEST_MODE", None)


# The coordinator test conftest sets TEST_MODE=true; when both suites share a
# pytest session, coordinator_api.config may already be imported with
# settings.test_mode frozen — middleware would never mount. The e2e field
# values are applied per test by the _e2e_settings_guard fixture below (and
# restored again after each test), so this suite always builds a
# production-shaped app without leaking that shape to other suites.
def _apply_e2e_settings() -> None:
    if "coordinator_api.config" not in sys.modules:
        return
    from coordinator_api.config import settings as _settings

    _settings.test_mode = False
    _settings.auth_enabled = True
    _settings.jwt_secret = "escrow-e2e-test-secret-key-material-0123456789"
    _settings.url = "sqlite:////tmp/aitbc-escrow-e2e.db"
    _settings.blockchain_rpc_url = "http://settlement-node.test"


def _restore_settings() -> None:
    """Put the shared coordinator settings singleton back the way this suite
    found it (pre-existing fields), or back to a clean-env instance (when this
    suite's conftest triggered the first config import). Fields are mutated in
    place — modules holding a `from ... import settings` reference must see
    the clean values too."""
    if "coordinator_api.config" not in sys.modules:
        return
    import coordinator_api.config as _cfg

    if _PRE_SETTINGS is not None:
        for field, value in _PRE_SETTINGS.items():
            if value is _ABSENT:
                try:
                    delattr(_cfg.settings, field)
                except AttributeError:
                    pass
            else:
                setattr(_cfg.settings, field, value)
        return
    fresh = type(_cfg.settings)()
    fields = getattr(type(_cfg.settings), "model_fields", None) or vars(fresh)
    for field in fields:
        setattr(_cfg.settings, field, getattr(fresh, field))


import sys as _sys  # noqa: E402

if "coordinator_api.config" in _sys.modules:
    # Align now in case anything between here and the guard fixture reads the
    # singleton (e.g. the create_app import below); the guard keeps it aligned
    # per test and _restore_settings() after the imports puts it back.
    _apply_e2e_settings()
    del _sys

import sys  # noqa: E402
from collections.abc import Generator  # noqa: E402
from pathlib import Path  # noqa: E402

# This directory is not a package; put it on sys.path so `stubchain` and
# `conftest` resolve the same way in every pytest/import mode.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import StaticPool, create_engine  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from aitbc.auth import create_access_token  # noqa: E402
from aitbc.crypto.crypto import derive_ethereum_address  # noqa: E402

from coordinator_api.main import create_app  # noqa: E402

# Build a private app AFTER the test_mode reset above — the coordinator
# conftest's module-level `app` may already exist with middleware off, so
# this suite must never reuse that instance.
from coordinator_api.storage import get_session  # noqa: E402
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet  # noqa: E402

from stubchain import (  # noqa: E402
    COORDINATOR_URL,
    LOCAL_RPC_URL,
    SETTLEMENT_RPC_URL,
    StubChain,
    make_async_client_class,
    make_cli_bridge_class,
)

# coordinator_api.config is now imported (or was already): the environment
# writes above have done their one job — freeze the e2e values into the
# settings singleton. Put the process env back exactly as found so nothing
# downstream in a shared session (env-file loads, other conftests' setdefault
# chains, subprocess children) sees this suite's secrets or AUTH_ENABLED.
for _k, _v in _PRE_ENV.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v
del _k, _v

# Same for the settings singleton: realigned above only so the imports built
# this suite's app config; restored so collection of every later suite sees
# the environment it ran under. The per-test guard re-applies the e2e values.
_restore_settings()

# A fixed throwaway test key — never a real wallet; its only use is deriving
# a syntactically valid buyer address for the signature path.
BUYER_PRIVATE_KEY = "0x" + "11" * 32
BUYER_ADDRESS = derive_ethereum_address(BUYER_PRIVATE_KEY)
PROVIDER_ADDRESS = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x5E8E8f0B5b4C9dE2a1B3c4D5e6F7080910112aAA"
FOREIGN_ADDRESS = "0x11cD222222eF3496344cFA78fe025c3B48Caf435"


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session]:
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def stub_chain() -> StubChain:
    return StubChain(node_wallet=NODE_WALLET)


@pytest.fixture
def coord_client(db_session):
    """The real coordinator app — real middleware, real relay routers."""
    from fastapi.testclient import TestClient

    def override_get_session() -> Generator[Session]:
        yield db_session

    real_app = create_app()
    real_app.dependency_overrides[get_session] = override_get_session
    yield TestClient(real_app)
    real_app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def wired(coord_client, db_session, stub_chain, monkeypatch):
    """Wire the real app to the stub chain and the real CLI helpers to both.

    Returns a namespace with everything a scenario needs.
    """
    async_client = make_async_client_class(stub_chain)
    monkeypatch.setattr(
        "coordinator_api.contexts.payments.services.escrow_relay.AsyncAITBCHTTPClient",
        async_client,
    )
    monkeypatch.setattr(
        "coordinator_api.contexts.payments.services.escrow_release_relay.AsyncAITBCHTTPClient",
        async_client,
    )

    bridge = make_cli_bridge_class(coord_client, stub_chain)
    # Every CLI module that instantiates AITBCHTTPClient gets the bridge.
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.AITBCHTTPClient", bridge)
    monkeypatch.setattr("aitbc_cli.commands.market.jobs.AITBCHTTPClient", bridge)
    monkeypatch.setattr("aitbc_cli.utils.escrow.AITBCHTTPClient", bridge)
    monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", bridge)
    monkeypatch.setattr(
        "aitbc_cli.commands.market.escrow._get_rpc_client",
        lambda config, base_url, timeout=10: bridge(base_url=base_url, timeout=timeout),
    )

    return SimpleNamespace(
        client=coord_client,
        session=db_session,
        chain=stub_chain,
        bridge_class=bridge,
    )


def bind_wallet(db_session: Session, user_id: str, address: str, role: str = "client") -> None:
    if db_session.get(User, user_id) is None:
        db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
    db_session.add(Wallet(user_id=user_id, address=address.lower()))
    db_session.commit()


def auth_header(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def cli_ctx(sub: str = "client-1", role: str = "client", output_format: str = "json") -> Any:
    """The click-context stand-in the CLI helpers read ``ctx.obj`` from."""
    return SimpleNamespace(
        obj={
            "api_key": create_access_token(sub, role),
            "url": COORDINATOR_URL,
            "output_format": output_format,
        }
    )


def cli_config() -> Any:
    """The config stand-in the CLI helpers read URLs/keys from."""
    return SimpleNamespace(
        hub_proposer_id="0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01",
        blockchain_rpc_api_key=None,
        blockchain_rpc_url=LOCAL_RPC_URL,
        hub_discovery_url=SETTLEMENT_RPC_URL,
        coordinator_api_url=COORDINATOR_URL,
    )


@pytest.fixture(autouse=True)
def _e2e_settings_guard() -> Generator[None]:
    """Scope this suite's production-shaped settings to each e2e test.

    The e2e suite needs auth on with its own jwt secret/DB, so it realigns the
    ``coordinator_api.config.settings`` singleton — which every later suite
    then inherits. Without the restore a same-session ``tests/integration``
    run built its app with auth mounted and no valid credential and every
    endpoint answered 401. The JWT handler singleton gets the same treatment:
    it resolved this suite's secret once and would keep signing with it.
    """
    _apply_e2e_settings()
    yield
    _restore_settings()
    try:
        import aitbc.auth.jwt as _jwt

        _jwt._jwt_handler = None
    except Exception:
        pass


@pytest.fixture(autouse=True, scope="module")
def _rebuild_shared_app_after_module() -> Generator[None]:
    """Rebuild ``coordinator_api.main.app`` when each e2e module finishes.

    This conftest's import-time ``from coordinator_api.main import create_app``
    executes the module-level ``app = create_app()`` — under the e2e
    environment, so that shared instance carries the mounted AuthMiddleware.
    Rebuilding at import time is no better: later conftests (e.g.
    tests/integration's ``TEST_MODE=true`` setdefault) have not run yet during
    collection. A module-scoped teardown fires after this suite's tests and —
    crucially — after every conftest in the session has been collected, so the
    rebuild sees the session's settled environment, not ours.
    """
    yield
    if "coordinator_api.main" in sys.modules:
        import coordinator_api.main as _main

        _main.app = _main.create_app()
        del _main
