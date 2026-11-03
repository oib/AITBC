"""BRIDGE-ADMIN-GATE-DEFAULT-OPEN-1 (#836): the bridge admin gate fails closed.

``register_validator`` and ``store_block_header`` checked the admin signature
only when ``bridge_release_enabled`` was true — with the flag unset an
unsigned (register: self-signed-only) request walked straight in. The gate
now refuses whenever the signature cannot be verified; an unconfigured
``bridge_admin_addresses`` is a refusal, not an open door.
"""

from __future__ import annotations

import json
import secrets
import time
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Session

from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import bridge as bridge_rpc

ADMIN_KEY = "ab" * 32
ADMIN_ADDR = keys.PrivateKey(bytes.fromhex(ADMIN_KEY)).public_key.to_checksum_address()
VALIDATOR_KEY = "cd" * 32
VALIDATOR_ADDR = keys.PrivateKey(bytes.fromhex(VALIDATOR_KEY)).public_key.to_checksum_address()

CHAIN = "chain-a"


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture(autouse=True)
def _patch_supported_chains():
    with patch("aitbc_chain.config.settings.supported_chains", "chain-a,chain-b,chain-c"):
        yield


@pytest.fixture
def rpc_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)


@pytest.fixture
def bridged(rpc_engine):
    """Route calls see a real CrossChainBridge backed by rpc_engine."""
    b = CrossChainBridge(lambda: Session(rpc_engine))
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=b):
        yield b


def _sign(private_key_hex: str, data: dict) -> str:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keys.PrivateKey(bytes.fromhex(private_key_hex)).sign_msg_hash(keccak(message)).to_hex()


def _register_payload(*, self_signed: bool = True) -> dict:
    payload = {
        "chain_id": CHAIN,
        "address": VALIDATOR_ADDR,
        "public_key": "0x" + VALIDATOR_KEY,
        "epoch": 0,
    }
    if self_signed:
        payload["signature"] = _sign(
            VALIDATOR_KEY,
            {"chain_id": CHAIN, "address": VALIDATOR_ADDR, "public_key": payload["public_key"], "action": "register"},
        )
    else:
        payload["signature"] = "0xdeadbeef"
    return payload


def _header_payload() -> dict:
    return {
        "chain_id": CHAIN,
        "height": 10,
        "hash": "0x" + "ab" * 32,
        "proposer": "0xproposer",
        "state_root": "0x" + "cd" * 32,
    }


def _admin_sig(payload: dict) -> dict:
    signed = {
        **payload,
        "admin_address": ADMIN_ADDR,
        "issued_at": time.time(),
        "nonce": secrets.token_hex(16),
        "target_chain_id": settings.chain_id,
    }
    signed["admin_signature"] = _sign(ADMIN_KEY, signed)
    return signed


def test_store_block_header_refuses_unsigned_when_the_flag_is_unset(bridged, monkeypatch):
    """Flag off + no admin signature = refuse. On the open default this stored."""
    monkeypatch.setattr(settings, "bridge_release_enabled", False)
    with pytest.raises(HTTPException) as exc:
        bridge_rpc.store_block_header(MagicMock(), _header_payload())
    assert exc.value.status_code == 403


def test_register_validator_refuses_self_signed_only_when_the_flag_is_unset(bridged, monkeypatch):
    """A validator's own signature proves key ownership, never authority."""
    monkeypatch.setattr(settings, "bridge_release_enabled", False)
    with pytest.raises(HTTPException) as exc:
        bridge_rpc.register_validator(MagicMock(), _register_payload())
    assert exc.value.status_code == 403


def test_unconfigured_admin_addresses_is_a_refusal_not_an_open_door(bridged, monkeypatch):
    """Fail closed: flag on but nobody configured -> still refused."""
    monkeypatch.setattr(settings, "bridge_release_enabled", True)
    monkeypatch.setattr(settings, "bridge_admin_addresses", "")
    with pytest.raises(HTTPException) as exc:
        bridge_rpc.store_block_header(MagicMock(), _header_payload())
    assert exc.value.status_code == 403


def test_a_signed_admin_request_still_passes(bridged, monkeypatch):
    """The configured-open path keeps working: valid admin signature is honoured."""
    monkeypatch.setattr(settings, "bridge_release_enabled", False)
    monkeypatch.setattr(settings, "bridge_admin_addresses", ADMIN_ADDR)

    resp = bridge_rpc.store_block_header(MagicMock(), _admin_sig(_header_payload()))
    assert resp["success"] is True
    assert resp["height"] == 10

    resp = bridge_rpc.register_validator(MagicMock(), _admin_sig(_register_payload()))
    assert resp["success"] is True
