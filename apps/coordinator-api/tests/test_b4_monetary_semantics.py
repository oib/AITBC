"""B4: exact monetary semantics regression tests.

Verifies that wallet/cross-chain monetary values are handled as integer atomic
units or Decimal, that float inputs are rejected, and that fee/price arithmetic
stays exact through common conversions.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from coordinator_api.contexts.wallet.services.money import (
    from_atomic_units,
    parse_decimal,
    to_atomic_units,
    validate_positive_amount,
)


def test_parse_decimal_rejects_float() -> None:
    """Float inputs must be refused to avoid binary floating-point loss."""
    with pytest.raises(TypeError, match="Float"):
        parse_decimal(1.1)
    with pytest.raises(TypeError, match="Float"):
        parse_decimal(1.0)


def test_parse_decimal_accepts_decimal_string_int() -> None:
    assert parse_decimal(Decimal("1.5")) == Decimal("1.5")
    assert parse_decimal("1.5") == Decimal("1.5")
    assert parse_decimal("1.0") == Decimal("1")
    assert parse_decimal(1) == Decimal("1")


def test_to_atomic_units_exact_conversion() -> None:
    """Decimal human amounts convert to integer atomic units without float loss."""
    assert to_atomic_units("1.0") == 10**18
    assert to_atomic_units(Decimal("0.1")) == 10**17
    assert to_atomic_units(Decimal("0.000000000000000001")) == 1
    assert to_atomic_units("123456789.123456789012345678") == int(Decimal("123456789.123456789012345678") * 10**18)


def test_to_atomic_units_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        to_atomic_units("0")
    with pytest.raises(ValueError, match="positive"):
        to_atomic_units("-1")


def test_to_atomic_units_rejects_float() -> None:
    with pytest.raises(TypeError, match="Float"):
        to_atomic_units(1.0)


def test_from_atomic_units_round_trip() -> None:
    """Atomic units round-trip through Decimal."""
    for decimals in (18, 9, 0):
        for atomic in (0, 1, 10**decimals, 10**decimals // 2, 10**18 + 1):
            dec = from_atomic_units(atomic, decimals=decimals)
            assert dec == Decimal(atomic) / (Decimal(10) ** decimals)


def test_from_atomic_units_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        from_atomic_units(-1)


def test_validate_positive_amount_bounds() -> None:
    assert validate_positive_amount("10", Decimal("100")) == Decimal("10")
    with pytest.raises(ValueError, match="maximum"):
        validate_positive_amount("101", Decimal("100"))
    with pytest.raises(ValueError, match="positive"):
        validate_positive_amount("0")


def test_ethereum_adapter_rejects_float_amounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """EthereumWalletAdapter.execute_transaction must refuse float amounts."""
    from coordinator_api.agent_identity import wallet_adapter_enhanced as wa
    from coordinator_api.agent_identity.wallet_adapter_enhanced import EthereumWalletAdapter, SecurityLevel

    monkeypatch.setattr(wa, "Web3Client", MagicMock)
    adapter = EthereumWalletAdapter(1, "http://localhost:8545", SecurityLevel.MEDIUM)
    monkeypatch.setattr(adapter, "validate_address", AsyncMock(return_value=True))
    monkeypatch.setattr(adapter, "_get_nonce", AsyncMock(return_value=0))
    monkeypatch.setattr(adapter, "_get_gas_price", AsyncMock(return_value=10**9))
    monkeypatch.setattr(adapter, "_estimate_gas_call", AsyncMock(return_value="0x5208"))
    monkeypatch.setattr(adapter, "_sign_transaction", AsyncMock(return_value="0xsigned"))
    monkeypatch.setattr(adapter, "_send_raw_transaction", AsyncMock(return_value="0x" + "11" * 32))

    with pytest.raises(TypeError, match="Float"):
        # Private key is required, but float amount must fail before signing
        import asyncio

        asyncio.run(adapter.execute_transaction("0x" + "00" * 20, "0x" + "00" * 20, 1.0, private_key="0x" + "11" * 32))


def test_aitbc_adapter_rejects_fractional_amounts(monkeypatch: pytest.MonkeyPatch) -> None:
    """AITBCWalletAdapter.execute_transaction must reject fractional atomic amounts."""
    from coordinator_api.agent_identity.wallet_adapter_enhanced import AITBCWalletAdapter, SecurityLevel

    adapter = AITBCWalletAdapter("http://localhost:8000", SecurityLevel.MEDIUM)
    monkeypatch.setattr(adapter, "validate_address", AsyncMock(return_value=True))
    monkeypatch.setattr(adapter, "_get_nonce", AsyncMock(return_value=0))
    mock_client = MagicMock()
    mock_client.post.return_value = {"transaction_hash": "0x" + "11" * 32}
    monkeypatch.setattr(adapter, "_http_client", mock_client)

    import asyncio

    with pytest.raises(ValueError, match="whole number"):
        asyncio.run(adapter.execute_transaction("0x" + "00" * 20, "0x" + "00" * 20, "1.5", private_key="ignored"))


@pytest.mark.asyncio
async def test_bridge_network_fee_is_decimal(monkeypatch: pytest.MonkeyPatch) -> None:
    """BridgeClientAdapter._estimate_network_fee must return a Decimal cost."""
    from decimal import Decimal

    from coordinator_api.contexts.cross_chain.services.cross_chain.bridge_client_adapter import BridgeClientAdapter

    adapter = BridgeClientAdapter(session=None, rpc_url="http://localhost:8545", chain_id=1)
    mock_wallet = AsyncMock()
    mock_wallet.estimate_gas.return_value = {"gas_limit": 21000}
    mock_wallet._get_gas_price.return_value = 10**9  # 1 gwei in wei
    adapter.wallet_adapters[1] = mock_wallet

    fee = await adapter._estimate_network_fee(1, Decimal("1.0"), None)
    assert isinstance(fee, Decimal)
    # 21000 gas * 1 gwei = 21000 gwei = 0.000021 ETH
    assert fee == Decimal("0.000021")


@pytest.mark.asyncio
async def test_multi_chain_gas_cost_is_decimal(monkeypatch: pytest.MonkeyPatch) -> None:
    """ChainTransactionManager statistics must aggregate gas cost as Decimal."""
    from coordinator_api.contexts.cross_chain.services.multi_chain_transaction_manager import ChainTransactionManager

    session = MagicMock()
    manager = ChainTransactionManager(session)
    tx = MagicMock()
    tx.gas_used = 21000
    tx.gas_price_paid = 10**9
    tx.chain_id = 1
    session.execute.return_value.scalars.return_value.all.return_value = [tx]
    session.execute.return_value.scalar.return_value = 1

    stats = await manager.get_transaction_statistics(1)
    assert stats["gas_statistics"][1]["total_gas_cost"] == Decimal("0.000021")
