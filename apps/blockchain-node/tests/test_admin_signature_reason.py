"""TARGET-CHAIN-FOOTGUN-1 (#679): admin-signature rejection names the reason.

``_request_freshness_error`` / ``admin_signature_failure`` return a
human-readable reason and ``require_admin_signature`` puts it in the 403
detail. A ``target_chain_id`` mismatch must spell out that the field binds
the *serving* node's own chain id — not the chain the payload is about —
because callers naturally (and wrongly) fill it with the registration
``chain_id`` (the live I-2 incident: bc-2-island-1 registrations posted to
bc-2 nodes).

The autouse conftest fixture pins ``settings.chain_id`` to ``"bc-2.test"``.
"""

from __future__ import annotations

import json
import secrets
import time

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException

from aitbc_chain.config import settings
from aitbc_chain.rpc.utils import (
    _request_freshness_error,
    admin_signature_failure,
    require_admin_signature,
    verify_admin_signature,
)

ADMIN_KEY = "ab" * 32
ADMIN_ADDR = keys.PrivateKey(bytes.fromhex(ADMIN_KEY)).public_key.to_checksum_address()


def _sign(private_key_hex: str, data: dict) -> str:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keys.PrivateKey(bytes.fromhex(private_key_hex)).sign_msg_hash(keccak(message)).to_hex()


@pytest.fixture
def admin_configured(monkeypatch):
    monkeypatch.setattr(settings, "bridge_admin_addresses", ADMIN_ADDR)


def _signed_payload(target_chain: str = "bc-2.test") -> dict:
    payload = {
        "issued_at": time.time(),
        "nonce": secrets.token_hex(16),
        "target_chain_id": target_chain,
        "admin_address": ADMIN_ADDR,
    }
    payload["admin_signature"] = _sign(ADMIN_KEY, payload)
    return payload


def test_target_chain_mismatch_reason_names_both_chains():
    err = _request_freshness_error({"issued_at": time.time(), "nonce": "n1", "target_chain_id": "bc-2-island-1"})
    assert err is not None
    assert "bc-2-island-1" in err
    assert "bc-2.test" in err
    assert "serving" in err


def test_missing_target_chain_reason():
    err = _request_freshness_error({"issued_at": time.time(), "nonce": "n2"})
    assert err is not None
    assert "target_chain_id" in err


def test_freshness_accepts_own_chain():
    assert (
        _request_freshness_error({"issued_at": time.time(), "nonce": secrets.token_hex(8), "target_chain_id": "bc-2.test"})
        is None
    )


def test_admin_signature_failure_missing_fields():
    assert "missing" in (admin_signature_failure({}, None, None) or "")


def test_require_admin_signature_mismatch_403_detail(admin_configured):
    """The footgun case end-to-end: a correctly signed payload whose
    target_chain_id is the *registration* chain fails with a detail that
    says which chain id was actually required."""
    payload = _signed_payload("bc-2-island-1")
    with pytest.raises(HTTPException) as excinfo:
        require_admin_signature(payload, ADMIN_ADDR, payload["admin_signature"])
    assert excinfo.value.status_code == 403
    detail = excinfo.value.detail
    assert "bc-2-island-1" in detail
    assert "bc-2.test" in detail


def test_require_admin_signature_accepts_valid(admin_configured):
    payload = _signed_payload("bc-2.test")
    require_admin_signature(payload, ADMIN_ADDR, payload["admin_signature"])


def test_verify_admin_signature_bool_api_unchanged(admin_configured):
    good = _signed_payload("bc-2.test")
    assert verify_admin_signature(good, ADMIN_ADDR, good["admin_signature"]) is True
    bad = _signed_payload("bc-2-island-1")
    assert verify_admin_signature(bad, ADMIN_ADDR, bad["admin_signature"]) is False
