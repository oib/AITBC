"""Money inside a signed transaction payload is `float`, and must stay that way.

V23-45. The repo-wide rule is `Decimal` for money (CLAUDE.md, V23-33 through V23-42, and
`scripts/lint/no_float_money.py`, whose baseline is zero). Four fields are exempt because they
cross a signature and hash boundary:

    rpc/ai_services.py   AIJobRequest.payment, AIJobResponse.payment
    rpc/marketplace.py   MarketplaceListing.price, MarketplaceCreateRequest.price

`verify_transaction_signature` builds the signed message as
`json.dumps(tx_without_sig, sort_keys=True, separators=(",", ":"))`, keccak-hashes it and
recovers the signer. So the *wire spelling* of these values is fixed by every signature
already issued and every transaction hash already on chain.

Converting them is a hard fork, not a lint fix. V23-36 recorded that and declined to make it;
`docs/architecture/money-types-and-the-signature-boundary.md` is the decision record. This
file is the part that cannot be skimmed past: it demonstrates the failure with a real
secp256k1 signature rather than asserting it in prose, and it fails if anyone converts one of
the four.
"""

from __future__ import annotations

import inspect
import json
from decimal import Decimal

import pytest
from aitbc_chain.rpc import utils as rpc_utils
from aitbc_chain.rpc.ai_services import AIJobRequest, AIJobResponse
from aitbc_chain.rpc.marketplace import MarketplaceCreateRequest, MarketplaceListing
from aitbc_chain.rpc.utils import verify_transaction_signature
from eth_keys import keys
from eth_utils import keccak

# The same deterministic test key test_signing_round_trip.py uses.
PRIVATE_KEY = keys.PrivateKey(bytes.fromhex("4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"))
ADDRESS = PRIVATE_KEY.public_key.to_checksum_address()

# The four fields the money guard exempts, and where they are declared.
WIRE_MONEY_FIELDS = [
    (AIJobRequest, "payment"),
    (AIJobResponse, "payment"),
    (MarketplaceListing, "price"),
    (MarketplaceCreateRequest, "price"),
]


def _canonical(tx: dict) -> bytes:
    """The exact encoding `verify_transaction_signature` signs over."""
    return json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()


def _sign(tx: dict) -> str:
    return PRIVATE_KEY.sign_msg_hash(keccak(_canonical(tx))).to_hex()


def _ai_job_tx(payment: object) -> dict:
    """An AI_JOB transaction shaped the way `submit_ai_job` builds one."""
    return {
        "from": ADDRESS,
        "to": "ai_service",
        "type": "AI_JOB",
        "nonce": 0,
        "payload": {"payment": payment, "prompt": "hi", "job_type": "text"},
    }


# --------------------------------------------------------------------------------------
# The demonstration. These three tests are the reason the decision went the way it did.
# --------------------------------------------------------------------------------------


def test_a_float_payment_verifies():
    """The baseline: this is what every client signing against this node produces today."""
    tx = _ai_job_tx(0.5)
    signature = _sign(tx)

    assert verify_transaction_signature({**tx, "signature": signature}, signature, ADDRESS) is True


def test_the_same_amount_spelled_as_a_string_does_not_verify():
    """The whole argument, in one assertion.

    A `Decimal` cannot be JSON-encoded, so converting these fields means adding an encoder
    that emits a string. That changes the bytes being hashed, which changes the recovered
    address, which rejects a signature the client computed correctly. Every wallet, SDK and
    CLI already in the field would start failing — and every transaction hash on chain was
    computed over the float spelling, so history would not re-derive either.
    """
    tx = _ai_job_tx(0.5)
    signature = _sign(tx)

    assert b'"payment":0.5' in _canonical(tx)

    as_string = _ai_job_tx("0.5")
    assert b'"payment":"0.5"' in _canonical(as_string)

    assert verify_transaction_signature({**as_string, "signature": signature}, signature, ADDRESS) is False
    assert keccak(_canonical(tx)) != keccak(_canonical(as_string)), "the transaction hash moves too"


def test_a_decimal_cannot_be_put_on_the_wire_at_all():
    """Before the spelling even matters, `json.dumps` refuses."""
    with pytest.raises(TypeError, match="Decimal is not JSON serializable"):
        _canonical(_ai_job_tx(Decimal("0.5")))


def test_an_integral_decimal_is_not_a_loophole():
    """`Decimal("2")` serialises no better than `Decimal("0.5")` — the type is the problem."""
    with pytest.raises(TypeError, match="Decimal is not JSON serializable"):
        _canonical(_ai_job_tx(Decimal("2")))


# --------------------------------------------------------------------------------------
# The guard. These fail when someone converts a field or changes the canonicalisation.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("model", "field"), WIRE_MONEY_FIELDS, ids=lambda v: getattr(v, "__name__", v))
def test_the_wire_money_fields_are_still_float(model, field):
    annotation = model.model_fields[field].annotation

    assert annotation is float, (
        f"{model.__name__}.{field} is now {annotation!r}. This field crosses a signature and "
        f"hash boundary — see test_the_same_amount_spelled_as_a_string_does_not_verify above "
        f"and docs/architecture/money-types-and-the-signature-boundary.md. Converting it "
        f"invalidates every signature already issued and every transaction hash already on "
        f"chain. If that is genuinely intended, it is a protocol version bump with a "
        f"migration, and this test should be deleted as part of it — not adjusted."
    )


@pytest.mark.parametrize(("model", "field"), WIRE_MONEY_FIELDS, ids=lambda v: getattr(v, "__name__", v))
def test_each_wire_money_field_says_why_it_is_exempt(model, field):
    """The `# not-money:` marker is what keeps the money guard's baseline at zero here.

    Without it the field is a violation; with it and no explanation, the next person deletes
    the marker. Both failure modes are the same mistake, so the marker is required to exist.
    """
    source = inspect.getsource(model)
    declaration = next(line for line in source.splitlines() if line.strip().startswith(f"{field}:"))
    preceding = source.split(declaration)[0].splitlines()

    marker_lines = [line for line in preceding[-8:] if "not-money:" in line]
    assert marker_lines, f"{model.__name__}.{field} lost its `# not-money:` marker"


def test_the_signed_message_is_still_canonical_json():
    """Every claim above assumes this specific encoding. If it changes, re-derive them.

    `sort_keys=True` fixes key order and `separators` removes the whitespace that would
    otherwise vary between encoders. Both are load-bearing: a client that emits
    `{"payment": 0.5}` with a space signs different bytes from one that emits
    `{"payment":0.5}`.
    """
    source = inspect.getsource(verify_transaction_signature)

    assert "sort_keys=True" in source
    assert 'separators=(",", ":")' in source
    assert "keccak(message)" in source

    # And the generic request verifier alongside it, which staking and the bridge use.
    generic = inspect.getsource(rpc_utils.verify_request_signature)
    assert "sort_keys=True" in generic
    assert 'separators=(",", ":")' in generic


def test_float_round_trips_through_the_canonical_encoding():
    """Signature validity depends on float -> str -> float being stable, so pin that.

    This is the property that makes the current scheme work at all, and it is also the reason
    the scheme is a design defect worth recording: `repr()` shortest-round-trip is a Python
    guarantee, not a wire-format one. A client in another language that formats 0.1 as
    `0.10000000000000001` produces a valid float and an invalid signature.
    """
    for value in (0.5, 0.1, 2.0, 0.0001, 1e-7, 123456.789):
        encoded = _canonical({"v": value})
        assert json.loads(encoded)["v"] == value, f"{value!r} did not survive the round trip"

    # The spelling matters, not just the value: 2.0 and 2 are the same number, different bytes.
    assert _canonical({"v": 2.0}) != _canonical({"v": 2})
