"""Tests for bridge withdrawal multi-sig gate (P1.3)."""

import os
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.exchange.simple_exchange.handlers.bridge import BridgeMixin


class _BridgeHandler(BridgeMixin):
    """Minimal handler stand-in for the BridgeMixin."""


@pytest.fixture
def handler():
    return _BridgeHandler()


@pytest.fixture
def signer_pair():
    try:
        from eth_keys import keys
    except ImportError as e:
        pytest.skip(f"eth_keys not installed: {e}")
    private = keys.PrivateKey(b"\x01" * 32)
    return private, private.public_key


def test_withdraw_without_signers_is_allowed_when_no_policy(handler):
    """If BRIDGE_SIGNERS is empty, the multi-sig gate is open."""
    with patch.dict(os.environ, {"BRIDGE_SIGNERS": "", "BRIDGE_MULTISIG_THRESHOLD": "2"}, clear=False):
        ok, count = handler._verify_bridge_withdrawal_signatures(
            "0x0000000000000000000000000000000000000000", Decimal("1.0"), []
        )
    assert ok is True
    assert count == 0


def test_withdraw_requires_threshold_signatures(handler, signer_pair):
    private, public = signer_pair
    signer_address = public.to_address()
    message = f"BRIDGE_WITHDRAW:{signer_address}:1.0".encode("utf-8")
    signature = private.sign_msg(message)

    with patch.dict(
        os.environ,
        {
            "BRIDGE_SIGNERS": signer_address,
            "BRIDGE_MULTISIG_THRESHOLD": "1",
        },
        clear=False,
    ):
        ok, count = handler._verify_bridge_withdrawal_signatures(
            signer_address,
            Decimal("1.0"),
            [{"signature": signature.to_hex()}],
        )
    assert ok is True
    assert count == 1


def test_withdraw_rejects_forbidden_signatures(handler, signer_pair):
    private, public = signer_pair
    signer_address = public.to_address()
    other_address = "0x0000000000000000000000000000000000000001"

    try:
        from eth_keys import keys
    except ImportError as e:
        pytest.skip(f"eth_keys not installed: {e}")
    # Use a different private key that is not in the configured signer set.
    other_private = keys.PrivateKey(b"\x02" * 32)
    message = f"BRIDGE_WITHDRAW:{other_address}:1.0".encode("utf-8")
    signature = other_private.sign_msg(message)

    with patch.dict(
        os.environ,
        {
            "BRIDGE_SIGNERS": signer_address,
            "BRIDGE_MULTISIG_THRESHOLD": "1",
        },
        clear=False,
    ):
        ok, count = handler._verify_bridge_withdrawal_signatures(
            other_address,
            Decimal("1.0"),
            [{"signature": signature.to_hex()}],
        )
    assert ok is False
    assert count == 0


def test_withdraw_requires_configured_threshold(handler, signer_pair):
    private, public = signer_pair
    signer_address = public.to_address()
    message = f"BRIDGE_WITHDRAW:{signer_address}:1.0".encode("utf-8")
    signature = private.sign_msg(message)

    with patch.dict(
        os.environ,
        {
            "BRIDGE_SIGNERS": signer_address,
            "BRIDGE_MULTISIG_THRESHOLD": "2",
        },
        clear=False,
    ):
        ok, count = handler._verify_bridge_withdrawal_signatures(
            signer_address,
            Decimal("1.0"),
            [{"signature": signature.to_hex()}],
        )
    assert ok is False
    assert count == 1
