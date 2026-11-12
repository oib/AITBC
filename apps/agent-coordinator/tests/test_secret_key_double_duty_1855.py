"""#1855: SECRET_KEY/COORDINATOR_API_KEY must not double as faucet + operator creds.

The cluster-wide ``SECRET_KEY`` is loaded by every service; accepting it on
the coin-request routes (``_require_api_key``) and as the shared operator
principal (``shared_key_principal``) meant one env leak yielded bounded
treasury drain *and* hub admin. ``FOLLOWER_API_KEY`` is the dedicated faucet
credential; ``COORDINATOR_API_KEY`` remains the operator key. Both legacy
acceptances now sit behind ``AITBC_ALLOW_LEGACY_SHARED_KEYS=1``.
"""

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from agent_app.routers.coin_requests import _require_api_key  # noqa: E402
from agent_app.services.agent_auth import (  # noqa: E402
    OPERATOR_AGENT_ID,
    _shared_key_value,
    shared_key_principal,
)

FOLLOWER_KEY = "follower-" + "f" * 32
COORD_KEY = "coord-" + "c" * 32
CLUSTER_KEY = "cluster-" + "k" * 32
FLAG = "AITBC_ALLOW_LEGACY_SHARED_KEYS"


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("FOLLOWER_API_KEY", FOLLOWER_KEY)
    monkeypatch.setenv("COORDINATOR_API_KEY", COORD_KEY)
    monkeypatch.setenv("SECRET_KEY", CLUSTER_KEY)
    monkeypatch.delenv(FLAG, raising=False)


class TestFaucetRouteGate:
    def test_follower_key_accepted(self):
        _require_api_key(FOLLOWER_KEY)

    def test_coordinator_key_refused_by_default(self):
        with pytest.raises(HTTPException) as raised:
            _require_api_key(COORD_KEY)
        assert raised.value.status_code == 401

    def test_secret_key_refused_by_default(self):
        with pytest.raises(HTTPException) as raised:
            _require_api_key(CLUSTER_KEY)
        assert raised.value.status_code == 401

    def test_both_legacy_keys_accepted_under_hatch(self, monkeypatch):
        monkeypatch.setenv(FLAG, "1")
        _require_api_key(COORD_KEY)
        _require_api_key(CLUSTER_KEY)

    def test_follower_key_accepted_under_hatch_too(self, monkeypatch):
        monkeypatch.setenv(FLAG, "1")
        _require_api_key(FOLLOWER_KEY)


class TestOperatorPrincipal:
    def test_coordinator_key_resolves_operator(self):
        principal = shared_key_principal(COORD_KEY)
        assert principal is not None
        assert principal.agent_id == OPERATOR_AGENT_ID
        assert principal.is_admin is True

    def test_secret_key_does_not_resolve_operator_by_default(self):
        """The cluster secret must not mint a hub admin principal."""
        assert shared_key_principal(CLUSTER_KEY) is None
        assert _shared_key_value() == COORD_KEY

    def test_secret_key_alone_is_not_an_operator_credential(self, monkeypatch):
        """Mutation-sensitive form: with no COORDINATOR_API_KEY set, the
        pre-fix fallback made SECRET_KEY itself the operator key."""
        monkeypatch.delenv("COORDINATOR_API_KEY")
        assert _shared_key_value() != CLUSTER_KEY
        assert shared_key_principal(CLUSTER_KEY) is None

    def test_secret_key_resolves_under_hatch(self, monkeypatch):
        monkeypatch.setenv(FLAG, "1")
        # COORDINATOR_API_KEY still wins when both are set.
        assert _shared_key_value() == COORD_KEY
        monkeypatch.delenv("COORDINATOR_API_KEY")
        assert _shared_key_value() == CLUSTER_KEY
        principal = shared_key_principal(CLUSTER_KEY)
        assert principal is not None and principal.is_admin is True

    def test_no_credential_still_none(self):
        assert shared_key_principal(None) is None
        assert shared_key_principal("") is None
        assert shared_key_principal("wrong") is None
