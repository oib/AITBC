"""A key that is safe to publish, and the boundary that makes it safe (V23-68).

Followers need to call `/register` and `/execute` without holding a hub credential, so the
hub publishes a key in its bootstrap file at `/agent/blockchain.env` — a file anyone can read.
That is fine for a key which reaches only those two endpoints: `/execute` takes the amount and
destination from the stored row (V23-62), and `/register` writes rows the faucet policy has
ruled on (V23-67). Neither will pay outside the policy however loudly it is asked.

`COORDINATOR_API_KEY` was published in that file, and it is not that kind of key. It also
authenticates the agent WebSocket, where `agent_id` is a query parameter and the key is the
only check — so it connects as *any* agent and reaches `request_coins_handler`, which signs
and submits on the spot rather than writing a row. And `require_miner_api_key` falls back to
it whenever `miner_api_keys` is empty, which is the default and is what the deployed hub has,
making it a miner credential on coordinator-api's miner, settlement and marketplace routers.

So the tests that matter here are the negative ones. `FOLLOWER_API_KEY` opening `/register`
and `/execute` is the easy half; what makes it publishable is that it opens nothing else, and
that property has to fail loudly if anyone widens a check later.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from agent_app.routers.coin_requests import _require_api_key
from agent_app.routers.websocket import _authenticate_websocket

FOLLOWER_KEY = "follower-" + "f" * 32
HUB_KEY = "hub-" + "c" * 32


@pytest.fixture
def keys(monkeypatch):
    """Both keys configured, as a hub running this actually would be."""
    monkeypatch.setenv("FOLLOWER_API_KEY", FOLLOWER_KEY)
    monkeypatch.setenv("COORDINATOR_API_KEY", HUB_KEY)
    monkeypatch.delenv("SECRET_KEY", raising=False)


# --- What the published key may do -------------------------------------------------------


def test_the_follower_key_is_accepted_for_coin_requests(keys) -> None:
    _require_api_key(FOLLOWER_KEY)


def test_the_hub_key_still_works_there_too(keys) -> None:
    """Operators keep working; the split adds a key rather than replacing one."""
    _require_api_key(HUB_KEY)


def test_secret_key_still_works_when_it_is_the_only_one_set(monkeypatch) -> None:
    monkeypatch.delenv("FOLLOWER_API_KEY", raising=False)
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", HUB_KEY)

    _require_api_key(HUB_KEY)


# --- What it must not do. This is the half that makes publishing it safe -----------------


def test_the_follower_key_does_not_open_the_agent_websocket(keys) -> None:
    """The WebSocket authenticates as any `agent_id` and pays on the spot.

    If this ever passes, the published key has become a treasury credential and an
    impersonation credential in the same moment.
    """
    assert _authenticate_websocket(None, FOLLOWER_KEY) is False


def test_the_hub_key_does_open_the_websocket(keys) -> None:
    """The contrast that gives the test above its meaning."""
    assert _authenticate_websocket(None, HUB_KEY) is True


def test_the_follower_key_is_not_a_miner_credential(keys, monkeypatch) -> None:
    """`require_miner_api_key` falls back to COORDINATOR_API_KEY, never to this one."""
    from aitbc.auth.dependencies import require_miner_api_key

    class _Request:
        headers = {"X-Api-Key": FOLLOWER_KEY}

    with pytest.raises(HTTPException) as raised:
        require_miner_api_key(_Request())

    assert raised.value.status_code == 401


def test_the_miner_fallback_still_accepts_the_hub_key(keys) -> None:
    """Pinned because it is the reason the hub key must stay off the public file.

    Not an endorsement — `MINER_API_KEYS` should be set so this fallback stops applying.
    Until it is, this is the deployed behaviour and it should be visible in a test rather
    than discovered from a published file.
    """
    from aitbc.auth.dependencies import require_miner_api_key

    class _Request:
        headers = {"X-Api-Key": HUB_KEY}

    assert require_miner_api_key(_Request())["role"] == "miner"


# --- Ordinary rejections -----------------------------------------------------------------


@pytest.mark.parametrize("offered", [None, "", "wrong", FOLLOWER_KEY[:-1], FOLLOWER_KEY + "x"])
def test_anything_else_is_refused(keys, offered) -> None:
    with pytest.raises(HTTPException) as raised:
        _require_api_key(offered)

    assert raised.value.status_code == 401


def test_no_key_configured_refuses_everything(monkeypatch) -> None:
    """An unconfigured hub must fail closed, not open."""
    for name in ("FOLLOWER_API_KEY", "COORDINATOR_API_KEY", "SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)

    for offered in (None, "", "anything"):
        with pytest.raises(HTTPException):
            _require_api_key(offered)


def test_an_empty_configured_key_is_not_a_skeleton_key(monkeypatch) -> None:
    """`FOLLOWER_API_KEY=` in an env file must not mean "accept the empty string"."""
    monkeypatch.setenv("FOLLOWER_API_KEY", "")
    monkeypatch.setenv("COORDINATOR_API_KEY", HUB_KEY)

    with pytest.raises(HTTPException):
        _require_api_key("")


def test_the_published_file_is_not_a_place_for_the_hub_key() -> None:
    """The documentation of the rule, kept next to the code that depends on it.

    `docs/ops/` describes which key goes in the public bootstrap file. If that guidance is
    ever removed, this fails and whoever removed it has to decide deliberately.
    """
    guidance = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "ops", "follower-api-key.md")

    with open(os.path.abspath(guidance)) as handle:
        text = handle.read()

    assert "FOLLOWER_API_KEY" in text
    assert "COORDINATOR_API_KEY" in text
