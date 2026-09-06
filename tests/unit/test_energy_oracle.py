"""Unit tests for aitbc.marketplace.energy_oracle.

Uses mocked ``EthereumRPCClient`` so no real EVM connection is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aitbc.marketplace.energy_oracle import (
    DEFAULT_ENERGY_PRICING_ABI,
    EnergyOracleError,
    EVMEnergyOracle,
)
from aitbc.marketplace.energy_pricing import EnergyProfile, EnergyRate


def _make_oracle() -> tuple[EVMEnergyOracle, MagicMock]:
    rpc = MagicMock()
    rpc.get_block.return_value = {
        "number": 12345678,
        "hash": "0xblockhash",
    }
    oracle = EVMEnergyOracle(
        rpc_client=rpc,
        contract_address="0xEnergyPricing",
        chain_id=1,
    )
    return oracle, rpc


def test_get_profile() -> None:
    oracle, rpc = _make_oracle()
    rpc.call_contract.return_value = (
        True,
        3,
        "rtx-4060-ti",
        "0xProvider",
        165,
        300_000_000_000_000_000,
    )
    profile = oracle.get_profile("gpu-001")
    assert isinstance(profile, EnergyProfile)
    assert profile.resource_id == "gpu-001"
    assert profile.provider == "0xProvider"
    assert profile.model_id == "rtx-4060-ti"
    assert profile.tdp_watts == 165
    assert profile.eur_per_kwh_scaled == 300_000_000_000_000_000
    assert profile.enabled is True
    assert profile.revision == 3

    call = rpc.call_contract.call_args
    assert call.kwargs["function_name"] == "getEnergyProfile"
    assert call.kwargs["block_identifier"] is None


def test_get_rate() -> None:
    oracle, rpc = _make_oracle()
    rpc.call_contract.return_value = (
        True,
        7,
        4_000_000_000_000_000_000,
        1_700_000_000,
        1_700_000_010,
        "operator_reference",
    )
    rate = oracle.get_rate()
    assert isinstance(rate, EnergyRate)
    assert rate.ait_per_eur_scaled == 4_000_000_000_000_000_000
    assert rate.version == 7
    assert rate.observed_at == 1_700_000_000
    assert rate.submitted_at == 1_700_000_010
    assert rate.source_kind == "operator_reference"
    assert rate.enabled is True


def test_get_floor_valid() -> None:
    oracle, rpc = _make_oracle()
    rpc.call_contract.return_value = (
        7_128_000,
        True,
        "",
    )
    floor = oracle.get_floor("gpu-001", 1, 3600, 36_000_000)
    assert floor == 7_128_000


def test_get_floor_invalid() -> None:
    oracle, rpc = _make_oracle()
    rpc.call_contract.return_value = (
        0,
        False,
        "disabled profile",
    )
    with pytest.raises(EnergyOracleError) as exc:
        oracle.get_floor("gpu-001", 1, 3600, 36_000_000)
    assert "disabled profile" in str(exc.value)


def test_get_pinned_inputs_uses_same_block() -> None:
    oracle, rpc = _make_oracle()
    rpc.call_contract.side_effect = [
        (
            True,
            3,
            "rtx-4060-ti",
            "0xProvider",
            165,
            300_000_000_000_000_000,
        ),
        (
            True,
            7,
            4_000_000_000_000_000_000,
            1_700_000_000,
            1_700_000_010,
            "operator_reference",
        ),
    ]
    profile, rate, block_number, block_hash = oracle.get_pinned_inputs("gpu-001")
    assert block_number == 12345678
    assert block_hash == "0xblockhash"
    assert profile.tdp_watts == 165
    assert rate.version == 7
    # Both calls should use the resolved block number, not None.
    calls = rpc.call_contract.call_args_list
    assert calls[0].kwargs["block_identifier"] == 12345678
    assert calls[1].kwargs["block_identifier"] == 12345678


def test_default_abi_has_required_functions() -> None:
    names = {fn["name"] for fn in DEFAULT_ENERGY_PRICING_ABI}
    assert names == {"getEnergyProfile", "getEnergyRate", "getEnergyFloor"}
