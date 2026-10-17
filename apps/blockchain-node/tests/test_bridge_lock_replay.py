"""SEC-REPLAY-1: the bridge lock signature had no nonce or expiry — a captured
signed body could be re-posted as a new transfer (``transfer_id`` derives from
``time.time()``), debiting the sender again.

New-form locks sign ``issued_at`` (within ±``_ADMIN_MAX_SKEW_SECS``) and a
single-use ``nonce`` keyed ``bridge-lock:<sender>:<nonce>`` in the shared
sqlite nonce store; both are always checked. Old-form locks stay accepted
unless ``bridge_lock_require_replay_guard`` is set.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException

import aitbc_chain.rpc.bridge as bridge_mod
import aitbc_chain.rpc.utils as rpc_utils
from aitbc_chain.rpc.bridge import bridge_lock

SENDER_ACCT = EthAccount.create()
SENDER = SENDER_ACCT.address
RECIPIENT = EthAccount.create().address
TARGET = "ait-target"
AMOUNT = 3600000


class _FakeStatus:
    value = "locked"


class _FakeTransfer:
    transfer_id = "0x" + "ab" * 32
    status = _FakeStatus()
    source_chain = "ait-src"
    target_chain = TARGET
    sender = SENDER
    recipient = RECIPIENT
    amount = AMOUNT
    lock_time = None


class _FakeBridge:
    def __init__(self):
        self.initiate_calls = 0

    def initiate_transfer(self, **kwargs):
        self.initiate_calls += 1
        return _FakeTransfer()

    def release_availability(self, chain_id):
        return (True, "")


@pytest.fixture
def bridge_and_nonce(monkeypatch, tmp_path):
    """Real signature verification, fake bridge, tmp nonce store."""
    fake = _FakeBridge()
    monkeypatch.setattr("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", lambda: fake)
    monkeypatch.setattr(rpc_utils, "_nonce_db_path", lambda: tmp_path / "nonces.db")
    return fake


def _sign(private_key_hex: str, data: dict) -> str:
    """The exact signature verify_request_signature expects (canonical JSON → keccak)."""
    import json as _json

    msg = keccak(_json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
    return keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x"))).sign_msg_hash(msg).to_hex()


def _lock_body(*, new_form: bool = True, issued_at=None, nonce="nonce-1", sign_extra=True) -> dict:
    body = {
        "source_chain": "ait-src",
        "target_chain": TARGET,
        "sender": SENDER,
        "recipient": RECIPIENT,
        "amount": AMOUNT,
        "asset": "native",
    }
    if new_form:
        body["issued_at"] = time.time() if issued_at is None else issued_at
        body["nonce"] = nonce
    sign_data = dict(body)
    if not sign_extra:
        sign_data.pop("issued_at", None)
        sign_data.pop("nonce", None)
    body["signature"] = _sign(SENDER_ACCT.key.hex(), sign_data)
    return body


async def test_new_form_lock_accepted_once_then_replay_refused(bridge_and_nonce):
    fake = bridge_and_nonce
    body = _lock_body()

    result = await bridge_lock(MagicMock(), dict(body))
    assert result["success"] is True
    assert fake.initiate_calls == 1

    # Same captured body re-posted — the nonce is spent.
    with pytest.raises(HTTPException) as exc_info:
        await bridge_lock(MagicMock(), dict(body))
    assert exc_info.value.status_code == 403
    assert "nonce" in exc_info.value.detail.lower()
    assert fake.initiate_calls == 1


async def test_fresh_nonce_after_first_still_works(bridge_and_nonce):
    """A *different* signed body (fresh nonce) is a legitimate second lock."""
    fake = bridge_and_nonce
    assert (await bridge_lock(MagicMock(), _lock_body(nonce="n1")))["success"] is True
    assert (await bridge_lock(MagicMock(), _lock_body(nonce="n2")))["success"] is True
    assert fake.initiate_calls == 2


async def test_expired_issued_at_refused(bridge_and_nonce):
    with pytest.raises(HTTPException) as exc_info:
        await bridge_lock(MagicMock(), _lock_body(issued_at=time.time() - 400))
    assert exc_info.value.status_code == 403


async def test_future_issued_at_refused(bridge_and_nonce):
    with pytest.raises(HTTPException) as exc_info:
        await bridge_lock(MagicMock(), _lock_body(issued_at=time.time() + 400))
    assert exc_info.value.status_code == 403


async def test_old_form_accepted_with_flag_off(bridge_and_nonce, monkeypatch):
    monkeypatch.setattr(bridge_mod.settings, "bridge_lock_require_replay_guard", False)
    result = await bridge_lock(MagicMock(), _lock_body(new_form=False))
    assert result["success"] is True


async def test_old_form_refused_with_flag_on(bridge_and_nonce, monkeypatch):
    monkeypatch.setattr(bridge_mod.settings, "bridge_lock_require_replay_guard", True)
    with pytest.raises(HTTPException) as exc_info:
        await bridge_lock(MagicMock(), _lock_body(new_form=False))
    assert exc_info.value.status_code == 400


async def test_new_fields_present_but_unsigned_refused(bridge_and_nonce):
    """issued_at/nonce in the body but not in the signed dict → signature mismatch."""
    body = _lock_body(new_form=True, sign_extra=False)
    with pytest.raises(HTTPException) as exc_info:
        await bridge_lock(MagicMock(), body)
    assert exc_info.value.status_code == 403
    assert "Invalid sender signature" in exc_info.value.detail
