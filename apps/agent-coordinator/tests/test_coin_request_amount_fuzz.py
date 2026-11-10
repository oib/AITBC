"""Money fuzz round 4 — adversarial amount encodings on the coin-request
register endpoint (#v11 item 15).

Every payload below must land in exactly one of two buckets:

* **rejected** — a 4xx from pydantic/route validation, with no row written;
* **accepted-but-bounded** — a 200 whose stored amount is a plain positive
  ``int`` that ``coin_request_policy.decide`` still ceilings (an approved
  row can never exceed the automatic ceiling, and anything larger parks as
  PENDING for an operator).

A 500, a non-int amount, or an APPROVED row above the ceiling is a finding.
"""

from __future__ import annotations


import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.exceptions import register_exception_handlers
from agent_app.routers import coin_requests

from aitbc.utils.units import ait_to_units

from .conftest import API_KEY, stored_request


@pytest.fixture
def fuzz_client(bare_client, coin_request_env):
    """Same router as ``bare_client`` but with the production exception
    handlers — without them a rejected NaN amount echoes ``input=nan`` into a
    response body Starlette cannot serialize (the #1676 500 class)."""
    app = FastAPI()
    app.include_router(coin_requests.router)
    register_exception_handlers(app)
    return TestClient(app)


WALLET = "0xf3290d4F0D96a2Dd231C44362c57d5ad0AF0A281"
AUTO_CEILING = ait_to_units(100)  # hub automatic ceiling is 100 AIT


def _post_raw(client, body: str):
    return client.post(
        "/api/v1/agent/coin-requests/register",
        content=body.encode("utf-8"),
        headers={"x-api-key": API_KEY, "content-type": "application/json"},
    )


def _payload(request_id: str, amount_json: str) -> str:
    return f'{{"request_id": "{request_id}", "sender": "agent-fuzz", "amount": {amount_json}, "wallet_address": "{WALLET}"}}'


# Each entry: (name, raw JSON amount literal, expect_reject)
CASES = [
    ("unicode_arabic_indic_digits", '"١٢٣"', True),  # pydantic rejects; Python int() would read 123
    ("unicode_fullwidth_digits", '"１２３"', True),
    ("array_wrapped", "[100]", True),
    ("nested_object", '{"$gt": 0}', True),
    ("nested_amount", '{"value": 100}', True),
    ("hex_string", '"0x10"', True),
    ("float_integral", "1e3", False),  # 1000.0 -> int 1000
    ("float_fractional", "100.9", True),  # non-integral float
    ("bool_true", "true", True),
    ("nan_literal", "NaN", True),  # invalid strict JSON
    ("infinity_literal", "Infinity", True),
    ("negative_huge", "-" + "9" * 40, True),  # rejected by <=0 check -> 422
    ("astronomical", "1" + "0" * 40, True),  # > int64: un-storable, must 422 not 500
]


@pytest.mark.parametrize("name,amount_literal,expect_reject", CASES, ids=[c[0] for c in CASES])
def test_register_amount_encodings(fuzz_client, name, amount_literal, expect_reject) -> None:
    request_id = f"fuzz-{name}"
    response = _post_raw(fuzz_client, _payload(request_id, amount_literal))

    assert response.status_code != 500, f"{name}: server error on {amount_literal!r}: {response.text[:200]}"

    if expect_reject:
        assert response.status_code in (400, 422), f"{name}: expected 4xx, got {response.status_code}: {response.text[:200]}"
        assert stored_request(request_id) is None, f"{name}: rejected payload still wrote a row"
        return

    assert response.status_code == 200, f"{name}: unexpected {response.status_code}: {response.text[:200]}"
    body = response.json()
    stored = stored_request(request_id)
    assert stored is not None, f"{name}: 200 but no row"
    assert isinstance(stored.amount, int), f"{name}: non-int amount stored: {stored.amount!r}"
    assert stored.amount > 0, f"{name}: non-positive amount stored: {stored.amount}"

    # Whatever the encoding, the money invariant holds: nothing above the
    # automatic ceiling may be APPROVED without an operator.
    if stored.amount > AUTO_CEILING:
        assert stored.status.value != "approved", f"{name}: amount {stored.amount} above ceiling auto-approved"
        assert stored.status.value in ("pending", "manual_review", "rejected", "denied"), (
            f"{name}: unexpected status {stored.status} for oversized amount"
        )
    else:
        # Within ceiling the policy may approve — but the *stored* amount
        # must equal what the JSON literal denotes, never a coerced surprise.
        assert body.get("amount") == stored.amount


def test_register_unicode_digits_rejected(fuzz_client) -> None:
    """Pydantic's int parser refuses non-ASCII digits — a '١٢٣' amount can
    never smuggle a different number past validation."""
    for digits in ("١٢٣", "１２３"):
        response = _post_raw(fuzz_client, _payload(f"fuzz-uni-{digits}", f'"{digits}"'))
        assert response.status_code == 422, f"{digits!r}: {response.status_code}"
        assert stored_request(f"fuzz-uni-{digits}") is None
