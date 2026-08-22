"""Tests for bridge withdrawal multi-sig gate (P1.3)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.exchange.simple_exchange.config import BridgeConfig
from apps.exchange.simple_exchange.handlers import bridge as bridge_module


class _BridgeHandler(bridge_module.BridgeMixin):
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


def _patch_bridge_config(signers, threshold):
    """Return a patch for bridge.bridge_config configured for the multi-sig tests."""
    return patch.object(
        bridge_module,
        "bridge_config",
        BridgeConfig(
            bridge_eth_address="0x818018F30d8F5FB7AE7a64f25895F15110923748",
            bridge_contract_address="0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA",
            withdraw_enabled=False,
            custodian=True,
            multisig_enabled=bool(signers),
            multisig_threshold=threshold,
            signers=signers,
        ),
    )


def test_withdraw_without_signers_is_allowed_when_no_policy(handler):
    """If signers is empty, the multi-sig gate is open."""
    with _patch_bridge_config((), 2):
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

    with _patch_bridge_config((signer_address,), 1):
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

    with _patch_bridge_config((signer_address,), 1):
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

    with _patch_bridge_config((signer_address,), 2):
        ok, count = handler._verify_bridge_withdrawal_signatures(
            signer_address,
            Decimal("1.0"),
            [{"signature": signature.to_hex()}],
        )
    assert ok is False
    assert count == 1
