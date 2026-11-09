"""
Tests for the LayerZero bridge adapter (settlement/bridges/layerzero.py).

Coverage targets:
- CHAIN_IDS mapping and supported-chain validation
- _encode_payload ABI encoding (deterministic, decodable round-trip)
- _get_target_address / _get_signer_address / _load_abi / _verify_signature helpers
- initialize() contract wiring via a mocked web3
- estimate_cost success and BridgeError paths
- refund_failed_message -> BridgeNotSupportedError
- send_message happy path and the catch-all FAILED result
- verify_delivery / get_message_status receipt handling
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from web3 import Web3

from coordinator_api.settlement.bridges.base import (
    BridgeConfig,
    BridgeError,
    BridgeNotSupportedError,
    BridgeStatus,
    SettlementMessage,
    SettlementResult,
)
from coordinator_api.settlement.bridges.layerzero import LayerZeroAdapter

ENDPOINT_ADDRESS = "0x1111111111111111111111111111111111111111"
PAYMENT_TOKEN = "0x00000000000000000000000000000000000000aa"
TX_HASH = b"\x12" * 32
RECEIPT_HASH = "ab" * 32
SIGNATURE = "cd" * 16


def make_config(**overrides: Any) -> BridgeConfig:
    kwargs: dict[str, Any] = {
        "name": "layerzero",
        "enabled": True,
        "endpoint_address": ENDPOINT_ADDRESS,
        "supported_chains": [1, 137, 56, 42161],
        "default_fee": "0",
        "max_message_size": 65536,
    }
    kwargs.update(overrides)
    return BridgeConfig(**kwargs)


def make_message(**overrides: Any) -> SettlementMessage:
    kwargs: dict[str, Any] = {
        "source_chain_id": 1,
        "target_chain_id": 1,
        "job_id": "42",
        "receipt_hash": RECEIPT_HASH,
        "proof_data": {"job": "abc", "result": "ok"},
        "payment_amount": 1000,
        "payment_token": PAYMENT_TOKEN,
        "nonce": 7,
        "signature": SIGNATURE,
        "gas_limit": 500_000,
    }
    kwargs.update(overrides)
    return SettlementMessage(**kwargs)


def make_adapter(config: BridgeConfig | None = None) -> LayerZeroAdapter:
    return LayerZeroAdapter(config or make_config(), web3=MagicMock())


def make_receipt(status: int = 1, timestamp: int = 1700000000) -> MagicMock:
    receipt = MagicMock()
    receipt.status = status
    receipt.gasUsed = 21000
    receipt.__getitem__.return_value = timestamp
    return receipt


class TestLayerZeroConstants:
    def test_chain_ids_maps_ethereum_only(self) -> None:
        assert LayerZeroAdapter.CHAIN_IDS == {1: 101}

    def test_get_supported_chains_comes_from_config(self) -> None:
        adapter = make_adapter()
        assert adapter.get_supported_chains() == [1, 137, 56, 42161]

    def test_get_max_message_size_comes_from_config(self) -> None:
        adapter = make_adapter()
        assert adapter.get_max_message_size() == 65536


class TestEncodePayload:
    def test_encode_payload_returns_bytes(self) -> None:
        adapter = make_adapter()
        encoded = adapter._encode_payload(make_message())
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_encode_payload_is_deterministic(self) -> None:
        adapter = make_adapter()
        first = adapter._encode_payload(make_message())
        second = adapter._encode_payload(make_message())
        assert first == second

    def test_encode_payload_round_trips_through_codec(self) -> None:
        adapter = make_adapter()
        message = make_message()
        encoded = adapter._encode_payload(message)

        payload_types = [
            "uint256",
            "bytes32",
            "bytes",
            "uint256",
            "address",
            "uint256",
            "bytes",
        ]
        decoded = Web3().codec.decode(payload_types, encoded)

        assert decoded[0] == 42
        assert decoded[1] == bytes.fromhex(RECEIPT_HASH)
        import json

        assert json.loads(decoded[2]) == message.proof_data
        assert decoded[3] == message.payment_amount
        assert decoded[4].lower() == PAYMENT_TOKEN.lower()
        assert decoded[5] == message.nonce
        assert decoded[6] == bytes.fromhex(SIGNATURE)

    def test_encode_payload_changes_with_message_fields(self) -> None:
        adapter = make_adapter()
        base = adapter._encode_payload(make_message())
        different_nonce = adapter._encode_payload(make_message(nonce=8))
        different_payment = adapter._encode_payload(make_message(payment_amount=2000))
        assert base != different_nonce
        assert base != different_payment


class TestTargetAddressAndHelpers:
    @pytest.mark.asyncio
    async def test_get_target_address_returns_placeholder_for_known_chains(self) -> None:
        adapter = make_adapter()
        for chain_id in (1, 137, 56, 42161):
            assert await adapter._get_target_address(chain_id) == "0x..."

    @pytest.mark.asyncio
    async def test_get_target_address_raises_for_unknown_chain(self) -> None:
        adapter = make_adapter()
        with pytest.raises(ValueError, match="No target address configured for chain 999"):
            await adapter._get_target_address(999)

    @pytest.mark.asyncio
    async def test_get_signer_address_returns_placeholder(self) -> None:
        adapter = make_adapter()
        assert await adapter._get_signer_address() == "0x..."

    @pytest.mark.asyncio
    async def test_load_abi_returns_empty_list(self) -> None:
        adapter = make_adapter()
        assert await adapter._load_abi("LayerZeroEndpoint") == []
        assert await adapter._load_abi("UltraLightNode") == []

    @pytest.mark.asyncio
    async def test_verify_signature_returns_true(self) -> None:
        adapter = make_adapter()
        assert await adapter._verify_signature(make_message()) is True


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_loads_endpoint_and_uln_contracts(self) -> None:
        adapter = make_adapter()
        web3 = adapter.web3

        endpoint_contract = MagicMock()
        endpoint_contract.functions.ultraLightNode.return_value.call = AsyncMock(
            return_value="0x2222222222222222222222222222222222222222"
        )
        uln_contract = MagicMock()

        def contract_factory(address: str, abi: list) -> MagicMock:
            return endpoint_contract if address == ENDPOINT_ADDRESS else uln_contract

        web3.eth.contract.side_effect = contract_factory

        await adapter.initialize()

        assert adapter.endpoint is endpoint_contract
        assert adapter.ultra_light_node is uln_contract
        # endpoint ABI loaded first, then ULN ABI with the address from the endpoint
        assert web3.eth.contract.call_count == 2
        first_call = web3.eth.contract.call_args_list[0]
        assert first_call.kwargs["address"] == ENDPOINT_ADDRESS
        second_call = web3.eth.contract.call_args_list[1]
        assert second_call.kwargs["address"] == "0x2222222222222222222222222222222222222222"


class TestEstimateCost:
    @pytest.mark.asyncio
    async def test_estimate_cost_returns_fee_breakdown(self) -> None:
        adapter = make_adapter()
        endpoint = MagicMock()
        endpoint.functions.estimateFees.return_value.call = AsyncMock(return_value=(1234, 56))
        adapter.endpoint = endpoint

        result = await adapter.estimate_cost(make_message())

        assert result == {"layerZeroFee": 1234, "zroFee": 56, "total": 1290}
        endpoint.functions.estimateFees.assert_called_once_with(
            101,  # CHAIN_IDS[1] dstChainId
            "0x...",  # target address placeholder
            adapter._encode_payload(make_message()),
            False,  # payInZRO
            [0, 0, 0],  # adapterParams
        )

    @pytest.mark.asyncio
    async def test_estimate_cost_raises_bridge_error_for_unmapped_chain(self) -> None:
        adapter = make_adapter()
        adapter.endpoint = MagicMock()
        # chain 999 is neither in CHAIN_IDS nor target_addresses
        with pytest.raises(BridgeError, match="Failed to estimate fees"):
            await adapter.estimate_cost(make_message(target_chain_id=999))

    @pytest.mark.asyncio
    async def test_estimate_cost_raises_bridge_error_when_endpoint_call_fails(self) -> None:
        adapter = make_adapter()
        endpoint = MagicMock()
        endpoint.functions.estimateFees.return_value.call = AsyncMock(side_effect=RuntimeError("rpc down"))
        adapter.endpoint = endpoint

        with pytest.raises(BridgeError, match="Failed to estimate fees: rpc down"):
            await adapter.estimate_cost(make_message())

    @pytest.mark.asyncio
    async def test_estimate_cost_raises_bridge_error_when_uninitialized(self) -> None:
        adapter = make_adapter()
        assert adapter.endpoint is None
        with pytest.raises(BridgeError):
            await adapter.estimate_cost(make_message())


class TestRefundFailedMessage:
    @pytest.mark.asyncio
    async def test_refund_failed_message_raises_not_supported(self) -> None:
        adapter = make_adapter()
        with pytest.raises(BridgeNotSupportedError, match="does not support message refunds"):
            await adapter.refund_failed_message("0xabc")

    @pytest.mark.asyncio
    async def test_refund_error_is_bridge_error_subclass(self) -> None:
        adapter = make_adapter()
        with pytest.raises(BridgeError):
            await adapter.refund_failed_message("0xabc")


class TestSendMessage:
    def _wire_endpoint(self, adapter: LayerZeroAdapter) -> MagicMock:
        endpoint = MagicMock()
        endpoint.functions.estimateFees.return_value.call = AsyncMock(return_value=(500, 0))
        endpoint.functions.send.return_value.transact = AsyncMock(return_value=TX_HASH)
        endpoint.functions.send.return_value.estimateGas = AsyncMock(return_value=1000)
        adapter.endpoint = endpoint
        return endpoint

    @pytest.mark.asyncio
    async def test_send_message_returns_in_progress_result(self) -> None:
        adapter = make_adapter()
        endpoint = self._wire_endpoint(adapter)

        web3 = adapter.web3
        web3.eth.get_transaction_count = AsyncMock(return_value=3)
        receipt = make_receipt()
        web3.eth.wait_for_transaction_receipt.return_value = receipt

        result = await adapter.send_message(make_message())

        assert isinstance(result, SettlementResult)
        assert result.status == BridgeStatus.IN_PROGRESS
        assert result.message_id == TX_HASH.hex()
        assert result.transaction_hash == TX_HASH.hex()
        assert result.gas_used == 21000
        assert result.fee_paid == 500
        assert result.error_message is None

        # verify the send call args: dstChainId=101, target placeholder, payload,
        # value=payment_amount, adapterParams, refund address=nonce
        endpoint.functions.send.assert_called_once()
        args = endpoint.functions.send.call_args.args
        assert args[0] == 101
        assert args[1] == "0x..."
        assert isinstance(args[2], bytes)
        assert args[3] == 1000
        assert args[4] == [0, 0, 0]
        assert args[5] == 7

        # gas_limit was provided on the message so estimateGas is not consulted
        endpoint.functions.send.return_value.estimateGas.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_message_estimates_gas_when_gas_limit_missing(self) -> None:
        adapter = make_adapter()
        endpoint = self._wire_endpoint(adapter)

        web3 = adapter.web3
        web3.eth.get_transaction_count = AsyncMock(return_value=0)
        web3.eth.wait_for_transaction_receipt.return_value = make_receipt()

        message = make_message()
        message.gas_limit = None
        result = await adapter.send_message(message)

        assert result.status == BridgeStatus.IN_PROGRESS
        # estimateGas returns 1000 -> +20% buffer => 1200
        endpoint.functions.send.return_value.estimateGas.assert_called_once()
        tx_params = endpoint.functions.send.return_value.transact.call_args.args[0]
        assert tx_params["gas"] == 1200

    @pytest.mark.asyncio
    async def test_send_message_uses_default_gas_on_estimate_failure(self) -> None:
        adapter = make_adapter()
        endpoint = self._wire_endpoint(adapter)
        endpoint.functions.send.return_value.estimateGas = AsyncMock(side_effect=RuntimeError("estimation failed"))

        web3 = adapter.web3
        web3.eth.get_transaction_count = AsyncMock(return_value=0)
        web3.eth.wait_for_transaction_receipt.return_value = make_receipt()

        message = make_message()
        message.gas_limit = None
        result = await adapter.send_message(message)

        assert result.status == BridgeStatus.IN_PROGRESS
        tx_params = endpoint.functions.send.return_value.transact.call_args.args[0]
        assert tx_params["gas"] == 300000  # default fallback

    @pytest.mark.asyncio
    async def test_send_message_returns_failed_on_unsupported_chain(self) -> None:
        adapter = make_adapter()
        self._wire_endpoint(adapter)

        # target_chain_id=999 is not in config.supported_chains -> validate_message raises
        result = await adapter.send_message(make_message(target_chain_id=999))

        assert result.status == BridgeStatus.FAILED
        assert result.message_id == ""
        assert result.transaction_hash is None
        assert result.error_message is not None
        assert "not supported" in result.error_message

    @pytest.mark.asyncio
    async def test_send_message_returns_failed_on_transact_error(self) -> None:
        adapter = make_adapter()
        endpoint = self._wire_endpoint(adapter)
        endpoint.functions.send.return_value.transact = AsyncMock(side_effect=RuntimeError("insufficient funds"))

        web3 = adapter.web3
        web3.eth.get_transaction_count = AsyncMock(return_value=0)

        result = await adapter.send_message(make_message())

        assert result.status == BridgeStatus.FAILED
        assert result.message_id == ""
        assert "insufficient funds" in (result.error_message or "")


class TestVerifyDelivery:
    @pytest.mark.asyncio
    async def test_verify_delivery_true_when_delivered_event_present(self) -> None:
        adapter = make_adapter()
        web3 = adapter.web3
        web3.eth.get_transaction_receipt = AsyncMock(return_value=make_receipt())

        endpoint = MagicMock()
        endpoint.events.Delivered.return_value.processReceipt.return_value = [{"event": "Delivered"}]
        adapter.endpoint = endpoint

        assert await adapter.verify_delivery("0xabc") is True
        endpoint.events.Delivered.return_value.processReceipt.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_delivery_false_when_no_delivered_event(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(return_value=make_receipt())

        endpoint = MagicMock()
        endpoint.events.Delivered.return_value.processReceipt.return_value = []
        adapter.endpoint = endpoint

        assert await adapter.verify_delivery("0xabc") is False

    @pytest.mark.asyncio
    async def test_verify_delivery_false_on_exception(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(side_effect=RuntimeError("receipt not found"))
        adapter.endpoint = MagicMock()

        assert await adapter.verify_delivery("0xabc") is False


class TestGetMessageStatus:
    @pytest.mark.asyncio
    async def test_get_message_status_failed_when_receipt_status_zero(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(return_value=make_receipt(status=0))
        adapter.endpoint = MagicMock()

        result = await adapter.get_message_status("0xdead")

        assert result.status == BridgeStatus.FAILED
        assert result.message_id == "0xdead"
        assert result.transaction_hash == "0xdead"
        assert result.completed_at == 1700000000

    @pytest.mark.asyncio
    async def test_get_message_status_completed_when_delivered(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(return_value=make_receipt(status=1))

        endpoint = MagicMock()
        endpoint.events.Delivered.return_value.processReceipt.return_value = [{"event": "Delivered"}]
        adapter.endpoint = endpoint

        result = await adapter.get_message_status("0xbeef")

        assert result.status == BridgeStatus.COMPLETED
        assert result.completed_at == 1700000000

    @pytest.mark.asyncio
    async def test_get_message_status_in_progress_when_not_delivered(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(return_value=make_receipt(status=1))

        endpoint = MagicMock()
        endpoint.events.Delivered.return_value.processReceipt.return_value = []
        adapter.endpoint = endpoint

        result = await adapter.get_message_status("0xcafe")

        assert result.status == BridgeStatus.IN_PROGRESS
        assert result.transaction_hash == "0xcafe"
        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_get_message_status_failed_on_exception(self) -> None:
        adapter = make_adapter()
        adapter.web3.eth.get_transaction_receipt = AsyncMock(side_effect=RuntimeError("node unreachable"))

        result = await adapter.get_message_status("0xbad")

        assert result.status == BridgeStatus.FAILED
        assert result.message_id == "0xbad"
        assert "node unreachable" in (result.error_message or "")
