"""Unit tests for EVMContractClient gas-limit resolution (#2754).

The build_*_tx helpers used to carry hardcoded gas limits that OOG'd on
Sepolia. They now default to eth_estimateGas + 25% headroom unless an
explicit gas_limit is passed.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from aitbc_cli.utils.evm_contract import EVMContractClient


RENTAL = "0xRENTAL0000000000000000000000000000"
TOKEN = "0xTOKEN000000000000000000000000000000"
FROM = "0x1111111111111111111111111111111111111111"
SPENDER = "0x2222222222222222222222222222222222222222"
PROVIDER = "0x3333333333333333333333333333333333333333"
CONSUMER = "0x4444444444444444444444444444444444444444"
ESTIMATE = 480_000
EXPECTED_GAS = math.ceil(ESTIMATE * 5 / 4)


def _client() -> tuple[EVMContractClient, MagicMock]:
    client = EVMContractClient(
        rpc_url="http://evm.test",
        chain_id=11155111,
        rental_contract_address=RENTAL,
        token_contract_address=TOKEN,
    )
    rpc = MagicMock()
    rpc.encode_function_call.return_value = "0xdeadbeef"
    rpc.get_gas_price.return_value = {"wei": 1}
    rpc.estimate_gas.return_value = ESTIMATE
    client.rpc = rpc
    return client, rpc


# (name, callable(client) -> tx, expected "to")
_BUILDERS = [
    (
        "build_approve_tx",
        lambda c: c.build_approve_tx(SPENDER, 1000, FROM, 7),
        TOKEN,
    ),
    (
        "build_start_rental_tx",
        lambda c: c.build_start_rental_tx(42, FROM, 7),
        RENTAL,
    ),
    (
        "build_create_rental_tx",
        lambda c: c.build_create_rental_tx(PROVIDER, CONSUMER, 3600, 1000, "gpu", 1, FROM, 7),
        RENTAL,
    ),
    (
        "build_complete_rental_tx",
        lambda c: c.build_complete_rental_tx(42, FROM, 7),
        RENTAL,
    ),
]


@pytest.mark.parametrize("name,call,to_addr", _BUILDERS, ids=[b[0] for b in _BUILDERS])
def test_estimated_gas_limit(name, call, to_addr):
    client, rpc = _client()
    tx = call(client)
    assert tx["gas"] == EXPECTED_GAS
    rpc.estimate_gas.assert_called_once()
    est_tx = rpc.estimate_gas.call_args[0][0]
    assert est_tx["to"] == to_addr
    assert est_tx["data"] == "0xdeadbeef"
    assert est_tx["value"] == 0
    assert est_tx["from"] == FROM


@pytest.mark.parametrize("name,call,to_addr", _BUILDERS, ids=[b[0] for b in _BUILDERS])
def test_explicit_gas_limit_bypasses_estimate(name, call, to_addr):
    client, rpc = _client()

    def call_with_limit(c):
        # Re-invoke the same builder with an explicit gas_limit kwarg.
        if name == "build_approve_tx":
            return c.build_approve_tx(SPENDER, 1000, FROM, 7, gas_limit=77_000)
        if name == "build_start_rental_tx":
            return c.build_start_rental_tx(42, FROM, 7, gas_limit=77_000)
        if name == "build_create_rental_tx":
            return c.build_create_rental_tx(PROVIDER, CONSUMER, 3600, 1000, "gpu", 1, FROM, 7, gas_limit=77_000)
        return c.build_complete_rental_tx(42, FROM, 7, gas_limit=77_000)

    tx = call_with_limit(client)
    assert tx["gas"] == 77_000
    rpc.estimate_gas.assert_not_called()


@pytest.mark.parametrize("name,call,to_addr", _BUILDERS, ids=[b[0] for b in _BUILDERS])
def test_estimate_failure_raises_runtime_error(name, call, to_addr):
    client, rpc = _client()
    rpc.estimate_gas.side_effect = Exception("node says revert")
    with pytest.raises(RuntimeError, match="eth_estimateGas"):
        call(client)
