"""#1259 (D2 option P) — per-chain validator-membership guard.

The validator set is process-global, so a process that connectably serves a
non-default chain would authenticate that chain's dialers against the DEFAULT
chain's set. The guard counts the situation always (auth on) and refuses it
only behind ``gossip_auth_require_chain_membership``; the default chain, a
single-chain host, auth-off hosts and ``GOSSIP_SHARED_VALIDATOR_CHAINS``
entries are never touched.
"""

from __future__ import annotations

import pytest
from aitbc_chain.app import create_app
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.metrics import gossip_auth_membership_unconfigured_total, gossip_ws_rejected_total
from aitbc_chain.rpc import websocket as websocket_module
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    websocket_module._chain_brokers.clear()
    monkeypatch.setattr(settings, "gossip_backends", "chain-a:memory")
    monkeypatch.setattr(settings, "gossip_auth_enabled", True)
    monkeypatch.setattr(settings, "gossip_auth_require_chain_membership", False)
    monkeypatch.setattr(settings, "gossip_shared_validator_chains", "")
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 100)
    yield
    websocket_module._chain_brokers.clear()


def _unconfigured(chain: str) -> float:
    return gossip_auth_membership_unconfigured_total.labels(chain=chain)._value.get()


def _refused(chain: str) -> float:
    return gossip_ws_rejected_total.labels(
        chain=chain, topic_class="public", reason="chain_membership_unconfigured"
    )._value.get()


def _connect(chain: str) -> bool:
    """True when the socket was accepted and held open, False when closed 1008."""
    with TestClient(create_app()) as client:
        try:
            with client.websocket_connect(f"/rpc/gossip/ws?topic=transactions&chain={chain}"):
                return True
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
            return False


def test_defaults_are_off_and_empty() -> None:
    assert ChainSettings.model_fields["gossip_auth_require_chain_membership"].default is False
    assert ChainSettings.model_fields["gossip_shared_validator_chains"].default == ""


def test_shared_opt_in_parser() -> None:
    s = ChainSettings(gossip_shared_validator_chains=" chain-a , ,chain-b")
    assert s.gossip_shared_validator_chain_ids() == {"chain-a", "chain-b"}
    assert ChainSettings(gossip_shared_validator_chains="").gossip_shared_validator_chain_ids() == set()


def test_flag_off_counts_but_admits_non_default_chain() -> None:
    before = _unconfigured("chain-a")
    assert _connect("chain-a") is True
    assert _unconfigured("chain-a") == before + 1
    assert _refused("chain-a") == 0


def test_flag_on_refuses_non_default_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_require_chain_membership", True)
    before_ref = _refused("chain-a")
    assert _connect("chain-a") is False
    assert _refused("chain-a") == before_ref + 1


def test_flag_on_shared_opt_in_admits_listed_chain_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_require_chain_membership", True)
    monkeypatch.setattr(settings, "gossip_shared_validator_chains", "chain-a")
    before = _unconfigured("chain-a")
    assert _connect("chain-a") is True
    assert _unconfigured("chain-a") == before  # an opted-in chain is not "unconfigured"


def test_flag_on_default_chain_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_require_chain_membership", True)
    default = settings.chain_id
    before = _unconfigured(default)
    assert _connect(default) is True
    assert _unconfigured(default) == before


def test_auth_off_host_is_never_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_auth_require_chain_membership", True)
    before = _unconfigured("chain-a")
    assert _connect("chain-a") is True
    assert _unconfigured("chain-a") == before
