"""Pin for #2878: signed-payload residuals.

- A NaN ``timestamp`` used to pass ``_check_fresh`` — ``nan > 300`` is False —
  so a captured signed body stayed fresh forever. Timestamps must now be
  finite.
- ``POST /v1/governance/proposals/{id}/execute`` took ``executor_address``
  as an unbound query param: it was neither the signing identity nor inside
  the signed payload. It is now bound to the caller and covered by the
  signature when present.
"""

from __future__ import annotations

import json
import time

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi.testclient import TestClient

from governance_service.main import StakeRequest, app


def _sign(pk: keys.PrivateKey, payload: dict) -> str:
    return pk.sign_msg_hash(keccak(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())).to_hex()


def _address(pk: keys.PrivateKey) -> str:
    return pk.public_key.to_checksum_address()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _stake_body(staker: keys.PrivateKey, **over) -> dict:
    body = {
        "staker_address": _address(staker),
        "amount": 1000,
        "lock_period_days": 30,
        "timestamp": time.time(),
    }
    body.update(over)
    return body


def _signed_stake(staker: keys.PrivateKey, **over) -> dict:
    body = _stake_body(staker, **over)
    unsigned = {k: v for k, v in StakeRequest(**body).model_dump(mode="json").items() if k != "signature"}
    body["signature"] = _sign(staker, unsigned)
    return body


def test_nan_timestamp_refused(client: TestClient) -> None:
    """float('nan') must not satisfy the freshness window."""
    staker = keys.PrivateKey(b"\x07" * 32)
    body = _signed_stake(staker, timestamp=float("nan"))
    # httpx's json= encoder rejects NaN; send the literal the way a raw
    # client would (Python json.loads on the server accepts it).
    r = client.post(
        "/v1/governance/stake",
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 403


def test_execute_rejects_old_style_signature_with_executor(client: TestClient) -> None:
    """A signature over the legacy 3-field payload must not carry an
    executor_address query param — the executor is now inside the signed
    payload, so the old signature shape fails verification (403)."""
    executor = keys.PrivateKey(b"\x08" * 32)
    ts = time.time()
    body = {
        "caller_address": _address(executor),
        "timestamp": ts,
        "signature": _sign(
            executor,
            {"action": "execute", "proposal_id": "prop-x", "timestamp": ts},
        ),
    }
    r = client.post(
        "/v1/governance/proposals/prop-x/execute",
        params={"executor_address": _address(executor)},
        json=body,
    )
    assert r.status_code == 403


def test_execute_binds_executor_to_signer(client: TestClient) -> None:
    """caller_address=A with executor_address=B is refused even when the
    signature itself is valid for the route's signed payload."""
    signer = keys.PrivateKey(b"\x09" * 32)
    other = _address(keys.PrivateKey(b"\x0a" * 32))
    ts = time.time()
    signed_payload = {
        "action": "execute",
        "proposal_id": "prop-x",
        "executor_address": other,
        "timestamp": ts,
    }
    body = {
        "caller_address": _address(signer),
        "timestamp": ts,
        "signature": _sign(signer, signed_payload),
    }
    r = client.post(
        "/v1/governance/proposals/prop-x/execute",
        params={"executor_address": other},
        json=body,
    )
    assert r.status_code == 403


def test_execute_accepts_bound_executor(client: TestClient) -> None:
    """Positive control: caller == executor_address and the signature covers
    the executor — auth passes (proposal lookup may still 404)."""
    executor = keys.PrivateKey(b"\x0b" * 32)
    ts = time.time()
    signed_payload = {
        "action": "execute",
        "proposal_id": "prop-x",
        "executor_address": _address(executor),
        "timestamp": ts,
    }
    body = {
        "caller_address": _address(executor),
        "timestamp": ts,
        "signature": _sign(executor, signed_payload),
    }
    r = client.post(
        "/v1/governance/proposals/prop-x/execute",
        params={"executor_address": _address(executor)},
        json=body,
    )
    assert r.status_code != 403
