"""CLI-AUTH-FALLBACK-SWEEP-1 (#2246): remaining call sites must resolve
credentials explicit ``--api-key`` > stored ``auth login`` JWT >
``config.api_key`` instead of reading ``ctx.obj["api_key"]`` /
``config.api_key`` only and 401ing normally-authenticated users.

Covers the sites swept in this row: market escrow relay/create/refund +
payment lookup, market job tracking, market gpu auth headers, dispute
coordinator client, confidential + economics API clients, and the ai
command auth-header helper's config fallback.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import click

import aitbc_cli.commands.ai as ai_mod
import aitbc_cli.commands.confidential as confidential_mod
import aitbc_cli.commands.dispute as dispute_mod
import aitbc_cli.commands.economics as economics_mod
import aitbc_cli.commands.market.escrow as escrow_mod
import aitbc_cli.commands.market.gpu as gpu_mod
import aitbc_cli.commands.market.jobs as jobs_mod
from aitbc_cli import auth as auth_pkg

JWT = "eyJhbGciOi.fake.token"


class _Ctx:
    def __init__(self, obj):
        self.obj = obj


def _stub_store(monkeypatch, credential):
    monkeypatch.setattr(auth_pkg.AuthManager, "get_credential", lambda self, *a, **kw: credential)


# --- market/escrow.py ---------------------------------------------------------


def test_escrow_client_auth_kwargs_uses_stored_jwt(monkeypatch):
    """#2246: no --api-key → the stored `auth login` JWT goes out as Bearer."""
    _stub_store(monkeypatch, JWT)
    monkeypatch.setattr(escrow_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    assert escrow_mod._client_auth_kwargs(_Ctx({})) == {"headers": {"Authorization": f"Bearer {JWT}"}}


def test_escrow_client_auth_kwargs_explicit_wins_and_skips_store(monkeypatch):
    class _Exploding:
        def get_credential(self, *a, **kw):
            raise AssertionError("store must not be read when --api-key is given")

    monkeypatch.setattr(auth_pkg, "AuthManager", _Exploding)
    monkeypatch.setattr(escrow_mod, "get_config", lambda: SimpleNamespace(api_key="cfg-key"))
    assert escrow_mod._client_auth_kwargs(_Ctx({"api_key": "explicit-key"})) == {"api_key": "explicit-key"}


def test_escrow_client_auth_kwargs_config_key_last(monkeypatch):
    _stub_store(monkeypatch, None)
    monkeypatch.setattr(escrow_mod, "get_config", lambda: SimpleNamespace(api_key="cfg-key"))
    assert escrow_mod._client_auth_kwargs(_Ctx({})) == {"api_key": "cfg-key"}


def test_escrow_client_auth_kwargs_empty_when_nothing(monkeypatch):
    _stub_store(monkeypatch, None)
    monkeypatch.setattr(escrow_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    assert escrow_mod._client_auth_kwargs(_Ctx({})) == {}


# --- market/jobs.py -----------------------------------------------------------


def test_track_coordinator_job_uses_stored_jwt(monkeypatch):
    """#2246: market job tracking sends the stored JWT, not just ctx.api_key."""
    _stub_store(monkeypatch, JWT)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203", api_key=None)
    monkeypatch.setattr(jobs_mod, "get_config", lambda: config)
    client = MagicMock()
    client.post.return_value = {"job_id": "cj-1"}
    ctor = MagicMock(return_value=client)
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", ctor)

    result = jobs_mod._track_coordinator_job(
        cast(click.Context, SimpleNamespace(obj={"output_format": "table"})),
        "j1",
        {"offer_id": "o1", "model": "m"},
        "0xB",
        "0xP",
        Decimal("0.5"),
        "ollama",
    )
    assert result == {"job_id": "cj-1"}
    assert ctor.call_args.kwargs["headers"] == {"Authorization": f"Bearer {JWT}"}


def test_track_coordinator_job_explicit_key_skips_store(monkeypatch):
    class _Exploding:
        def get_credential(self, *a, **kw):
            raise AssertionError("store must not be read when --api-key is given")

    monkeypatch.setattr(auth_pkg, "AuthManager", _Exploding)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203", api_key="cfg-key")
    monkeypatch.setattr(jobs_mod, "get_config", lambda: config)
    client = MagicMock()
    client.post.return_value = {"job_id": "cj-1"}
    ctor = MagicMock(return_value=client)
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", ctor)

    jobs_mod._track_coordinator_job(
        cast(click.Context, SimpleNamespace(obj={"output_format": "table", "api_key": "explicit-key"})),
        "j1",
        {},
        "0xB",
        "0xP",
        Decimal("0.5"),
        "ollama",
    )
    assert ctor.call_args.kwargs["api_key"] == "explicit-key"
    assert "headers" not in ctor.call_args.kwargs


# --- market/gpu.py ------------------------------------------------------------


def test_gpu_auth_headers_uses_stored_jwt(monkeypatch):
    _stub_store(monkeypatch, JWT)
    monkeypatch.setattr(gpu_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    assert gpu_mod._auth_headers(_Ctx({})) == {"Authorization": f"Bearer {JWT}"}


def test_gpu_auth_headers_explicit_non_jwt_is_x_api_key(monkeypatch):
    """A non-JWT --api-key goes out as X-API-Key, matching auth_headers."""
    _stub_store(monkeypatch, JWT)
    monkeypatch.setattr(gpu_mod, "get_config", lambda: SimpleNamespace(api_key=None))
    assert gpu_mod._auth_headers(_Ctx({"api_key": "plain-key"})) == {"X-API-Key": "plain-key"}


def test_gpu_auth_headers_config_key_fallback(monkeypatch):
    _stub_store(monkeypatch, None)
    monkeypatch.setattr(gpu_mod, "get_config", lambda: SimpleNamespace(api_key="cfg-key"))
    assert gpu_mod._auth_headers(_Ctx({})) == {"X-API-Key": "cfg-key"}


# --- dispute.py ---------------------------------------------------------------


def test_dispute_coordinator_client_uses_stored_jwt(monkeypatch):
    """#2246: admin dispute routes get the stored `auth login` JWT."""
    _stub_store(monkeypatch, JWT)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203", api_key=None, timeout=10)
    monkeypatch.setattr(dispute_mod, "get_config", lambda: config)
    ctor = MagicMock()
    monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", ctor)

    dispute_mod._coordinator_client(cast(click.Context, SimpleNamespace(obj={})))
    assert ctor.call_args.kwargs["headers"] == {"Authorization": f"Bearer {JWT}"}


def test_dispute_coordinator_client_explicit_key_wins(monkeypatch):
    class _Exploding:
        def get_admin_token(self, *a, **kw):
            raise AssertionError("store must not be read when --api-key is given")

    monkeypatch.setattr(auth_pkg, "AuthManager", _Exploding)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203", api_key="cfg-key", timeout=10)
    monkeypatch.setattr(dispute_mod, "get_config", lambda: config)
    ctor = MagicMock()
    monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", ctor)

    dispute_mod._coordinator_client(cast(click.Context, SimpleNamespace(obj={"api_key": "explicit-key"})))
    assert ctor.call_args.kwargs["api_key"] == "explicit-key"
    assert "headers" not in ctor.call_args.kwargs


# --- confidential.py ----------------------------------------------------------


def test_confidential_api_client_uses_stored_jwt(monkeypatch):
    _stub_store(monkeypatch, JWT)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203/v1", api_key=None, timeout=10)
    monkeypatch.setattr(confidential_mod, "get_config", lambda: config)
    ctor = MagicMock()
    monkeypatch.setattr(confidential_mod, "AITBCHTTPClient", ctor)

    client = confidential_mod._api_client()
    assert client is ctor.return_value
    assert ctor.call_args.kwargs["headers"] == {"Authorization": f"Bearer {JWT}"}
    # Trailing /v1 is stripped — endpoints carry their own /v1 prefix.
    assert ctor.call_args.kwargs["base_url"] == "http://coord:8203"


def test_confidential_api_client_none_without_any_credential(monkeypatch):
    _stub_store(monkeypatch, None)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203", api_key=None, timeout=10)
    monkeypatch.setattr(confidential_mod, "get_config", lambda: config)
    assert confidential_mod._api_client() is None


# --- economics.py -------------------------------------------------------------


def test_economics_api_client_uses_stored_jwt(monkeypatch):
    _stub_store(monkeypatch, JWT)
    config = SimpleNamespace(coordinator_api_url="http://coord:8203/v1", api_key=None, timeout=10)
    monkeypatch.setattr(economics_mod, "get_config", lambda: config)
    ctor = MagicMock()
    monkeypatch.setattr(economics_mod, "AITBCHTTPClient", ctor)

    economics_mod._api_client()
    assert ctor.call_args.kwargs["headers"] == {"Authorization": f"Bearer {JWT}"}
    assert ctor.call_args.kwargs["base_url"] == "http://coord:8203"


# --- ai/__init__.py -----------------------------------------------------------


def test_ai_auth_headers_config_key_fallback(monkeypatch):
    """#2246: _auth_headers' last resort is config.api_key (explicit > store > config)."""
    _stub_store(monkeypatch, None)
    monkeypatch.setattr(ai_mod, "get_config", lambda: SimpleNamespace(api_key="cfg-key"))
    assert ai_mod._auth_headers(_Ctx({})) == {"X-API-Key": "cfg-key"}


def test_ai_auth_headers_stored_jwt_beats_config_key(monkeypatch):
    _stub_store(monkeypatch, JWT)
    monkeypatch.setattr(ai_mod, "get_config", lambda: SimpleNamespace(api_key="cfg-key"))
    assert ai_mod._auth_headers(_Ctx({})) == {"Authorization": f"Bearer {JWT}"}
