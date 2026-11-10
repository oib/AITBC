"""NaN/Infinity fuzz pins for POST /v1/wallets/{id}/send (#1676-class).

``WalletTransactionRequest.amount``/``fee`` are typed ints, so literal
``NaN``/``Infinity`` JSON floats are rejected by pydantic — but only if the
app installs the JSON-safe validation-error handler, otherwise the 422 body
echoes ``input=nan`` and the response itself fails serialization (500).
The wallet app had no such handler until this batch wired
``register_request_validation_error_handler`` into ``create_app``.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from wallet_app.deps import get_keystore, get_ledger, require_admin_api_key
from wallet_app.main import app


@pytest.fixture
def client():
    """Validation-only surface: deps stubbed so a malformed body is the only
    thing that can fail (same override pattern as test_wallet_operations)."""
    app.dependency_overrides[get_keystore] = lambda: MagicMock()
    app.dependency_overrides[get_ledger] = lambda: MagicMock()
    app.dependency_overrides[require_admin_api_key] = lambda: None
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _post(client: TestClient, body: bytes):
    return client.post(
        "/v1/wallets/w1/send",
        content=body,
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.parametrize("field", ["amount", "fee"])
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_literals_answer_422_not_500(client, field, literal):
    """Raw literal bodies — Python's json parser accepts these, pydantic must
    refuse them, and the refusal must serialize."""
    body = (
        b'{"password":"pw","recipient":"0xrecipient","amount":5,"fee":36,"' + field.encode() + b'":' + literal.encode() + b"}"
    )
    resp = _post(client, body)
    assert resp.status_code == 422, f"{field}={literal}: {resp.status_code} {resp.text[:200]}"
    resp.json()  # body must be valid JSON — the #1676 regression was a 500 here


@pytest.mark.parametrize(
    "amount_json",
    [
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1e308",  # finite float, out of int range
        b'"abc"',
        b'"1e3"',  # scientific notation string — not an int literal
        b"1e999",  # exponent overflow literal — parses to inf, must not send
        b'"-0"',  # negative-zero string — not an int literal
        b"[]",
        b"{}",
        '"١٢٣"'.encode(),  # unicode digits — may coerce; must never 500 or send
    ],
)
def test_bad_amount_values_never_500_or_send(client, amount_json):
    body = b'{"password":"pw","recipient":"0xrecipient","amount":' + amount_json + b',"fee":36}'
    resp = _post(client, body)
    assert resp.status_code in (400, 404, 422), f"amount={amount_json}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("amount_json", [b"-5", b"0"])
def test_negative_and_zero_amount_rejected_not_sent(client, amount_json):
    body = b'{"password":"pw","recipient":"0xrecipient","amount":' + amount_json + b',"fee":36}'
    resp = _post(client, body)
    assert resp.status_code in (400, 404, 422), f"amount={amount_json}: {resp.status_code} {resp.text[:200]}"
