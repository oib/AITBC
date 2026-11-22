"""#2531: is_canonical must check hex digits, and escrow buyer/provider
addresses must be real 0x addresses — to_canonical's lenient lowercase
fallback must not let garbage through to signing.
"""

from __future__ import annotations

from unittest import mock

import pytest

from aitbc_cli.commands.ai import _create_escrow_payment
from aitbc_cli.utils.address import is_canonical, to_canonical

GOOD = "0x" + "ab" * 20


def test_is_canonical_rejects_non_hex_body():
    assert is_canonical(GOOD)
    assert is_canonical(GOOD.upper())
    assert not is_canonical("0x" + "zz" * 20)  # right shape, not hex
    assert not is_canonical("0x" + "ab" * 19)  # too short
    assert not is_canonical("not-an-address")


def test_to_canonical_still_lenient_but_is_canonical_catches():
    # to_canonical keeps its passthrough contract; callers that need a real
    # address must gate on is_canonical.
    assert to_canonical("garbage") == "garbage"
    assert not is_canonical(to_canonical("garbage"))


def test_escrow_rejects_garbage_buyer():
    ctx = mock.Mock()
    with pytest.raises(Exception) as ei:
        _create_escrow_payment(
            ctx,
            mock.Mock(),
            "http://rpc",
            "job1",
            "1",
            "AIT",
            "not-an-address",
            GOOD,
            "0xkey",
            "wallet",
            None,
            None,
            None,
            None,
        )
    assert "buyer_address" in str(ei.value)


def test_escrow_rejects_garbage_provider():
    ctx = mock.Mock()
    with pytest.raises(Exception) as ei:
        _create_escrow_payment(
            ctx,
            mock.Mock(),
            "http://rpc",
            "job1",
            "1",
            "AIT",
            GOOD,
            "0x" + "zz" * 20,
            "0xkey",
            "wallet",
            None,
            None,
            None,
            None,
        )
    assert "provider_address" in str(ei.value)
