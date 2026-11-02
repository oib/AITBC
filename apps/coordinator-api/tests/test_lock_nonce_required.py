"""Phase-0 pin for ESCROW-LOCK-NONCE-GUESS-1 (#807).

``payments.py`` builds the escrow lock tx with
``nonce = payment_data.buyer_lock_nonce or _get_account_nonce(buyer)`` —
when the buyer supplies ``buyer_lock_signature`` but omits
``buyer_lock_nonce``, the coordinator *guesses* the account nonce and the
buyer's signature almost never verifies against it. A signed lock without
an explicit nonce is silently broken rather than refused.

Desired behaviour (pinned here): ``GPUBuyRequest`` (and the job-create
payload) answer 422 — buyer_lock_nonce is required whenever
buyer_lock_signature is set — and the signed path never falls back to a
guessed nonce. These FAIL on current main (no validator; the field is
accepted and the nonce is guessed).
"""

import pytest
from pydantic import ValidationError

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coordinator_api.contexts.market.routers.market_gpu import GPUBuyRequest


def _payload(**over):
    base = {
        "buyer_id": "buyer1",
        "gpu_id": "gpu1",
        "duration_hours": 1,
        "buyer_address": "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
        "provider_address": "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2",
        "buyer_lock_signature": "0xsig",
    }
    base.update(over)
    return base


def test_signature_without_nonce_is_422():
    with pytest.raises(ValidationError):
        GPUBuyRequest(**_payload())


def test_signature_with_nonce_accepted():
    req = GPUBuyRequest(**_payload(buyer_lock_nonce=7))
    assert req.buyer_lock_nonce == 7


def test_no_signature_no_nonce_accepted():
    req = GPUBuyRequest(buyer_id="buyer1", gpu_id="gpu1", duration_hours=1)
    assert req.buyer_lock_signature is None and req.buyer_lock_nonce is None
