"""Energy operator and provider CLI commands.

Commands:
  aitbc energy operator info     - Show configured operator key/address
  aitbc energy operator verify   - Verify an energy quote's operator signature
  aitbc energy provider register - Register a GPU energy profile on-chain
  aitbc energy provider profile  - Read a registered energy profile
  aitbc energy provider rate     - Read or publish the AIT/EUR rate
  aitbc energy floor             - Compute or check the on-chain energy floor
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.energy_quote import (
    compute_settlement_breakdown,
    parse_quote,
    verify_quote,
    verify_quote_against_oracle,
)
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


@click.group()
def energy():
    """Energy pricing operator and provider commands."""


@energy.group()
def operator():
    """Operator commands for energy quote signing and verification."""


@operator.command("info")
@click.pass_context
def operator_info(ctx):
    """Show the configured energy operator address and signing status."""
    config = get_config()
    addr = config.energy_operator_address
    if addr:
        success(f"Operator address: {addr}")
    else:
        warning("No operator address configured (ENERGY_OPERATOR_ADDRESS)")
    info(f"Quote domain: {config.energy_quote_domain}")
    info(f"Native chain: {config.native_chain_id}")
    info(f"EVM chain ID: {config.energy_pricing_chain_id}")
    if config.energy_pricing_contract_address:
        info(f"Pricing contract: {config.energy_pricing_contract_address}")
    if config.energy_rental_contract_address:
        info(f"Rental contract: {config.energy_rental_contract_address}")
    if config.evm_rpc_url:
        info(f"EVM RPC URL: {config.evm_rpc_url}")


@operator.command("verify")
@click.option("--quote-file", type=click.Path(exists=True), required=True, help="JSON file containing an energy quote")
@click.option("--check-oracle", is_flag=True, help="Also verify against the on-chain IEnergyPricing oracle")
@click.pass_context
def operator_verify(ctx, quote_file, check_oracle):
    """Verify an energy quote's operator signature and freshness."""
    with open(quote_file) as f:
        quote_dict = json.load(f)

    config = get_config()
    parsed = parse_quote(quote_dict)

    if check_oracle and config.evm_rpc_url and config.energy_pricing_contract_address:
        result = verify_quote_against_oracle(
            parsed,
            rpc_url=config.evm_rpc_url,
            contract_address=config.energy_pricing_contract_address,
            chain_id=config.energy_pricing_chain_id,
            operator_address=config.energy_operator_address,
        )
    else:
        result = verify_quote(
            parsed,
            expected_operator_address=config.energy_operator_address,
            expected_domain=config.energy_quote_domain,
            expected_chain_id=config.native_chain_id,
        )

    if result.valid:
        success("Quote is valid")
        info(f"Digest: {result.digest_hex}")
        info(f"Operator verified: {result.operator_verified}")
        if result.breakdown:
            info(f"Buyer charge: {result.breakdown['buyer_charge_units']} units")
            info(f"Provider credit: {result.breakdown['provider_credit_units']} units")
            info(f"Platform fee: {result.breakdown['platform_fee_units']} units")
    else:
        error(f"Quote verification failed: {result.refusal_reason} ({result.refusal_code})")
        sys.exit(1)


@energy.group()
def provider():
    """Provider commands for GPU energy profile and rate management."""


@provider.command("register")
@click.option("--resource-id", required=True, help="Canonical resource ID")
@click.option("--provider-address", required=True, help="Provider wallet address")
@click.option("--model-id", required=True, help="GPU model ID")
@click.option("--tdp-watts", type=int, required=True, help="GPU TDP in watts")
@click.option("--eur-per-kwh", type=float, required=True, help="EUR per kWh tariff")
@click.option("--wallet", help="Wallet name for signing")
@click.option("--wallet-path", help="Direct wallet file path")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Wallet password file")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def provider_register(
    ctx,
    resource_id,
    provider_address,
    model_id,
    tdp_watts,
    eur_per_kwh,
    wallet,
    wallet_path,
    password,
    password_file,
    json_output,
):
    """Register a GPU energy profile on the IEnergyPricing contract."""
    config = get_config()
    if not config.evm_rpc_url:
        error("EVM RPC URL not configured (set EVM_RPC_URL)")
        sys.exit(1)
    if not config.energy_pricing_contract_address:
        error("IEnergyPricing contract address not configured")
        sys.exit(1)

    pw = password
    if password_file:
        with open(password_file) as f:
            pw = f.read().strip()

    from ..utils.wallet_loader import load_wallet_for_payment

    addr, private_key, _ = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=pw,
        require_private_key=True,
    )

    if private_key is None:
        error("A private key is required to register an energy profile")
        sys.exit(1)

    from ..utils.evm_contract import EVMContractClient, _ERC20_ABI

    # Build and submit the registerEnergyProfile call via the EVM client.
    # We use the IEnergyPricing ABI directly since it's a separate contract.
    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.marketplace.energy_oracle import DEFAULT_ENERGY_PRICING_ABI

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id)))
    scale = 10**18
    eur_scaled = int(eur_per_kwh * scale)
    data = rpc.encode_function_call(
        abi=DEFAULT_ENERGY_PRICING_ABI,
        function_name="registerEnergyProfile",
        args=[resource_id, provider_address, model_id, tdp_watts, eur_scaled],
    )
    nonce = rpc._get_web3().eth.get_transaction_count(addr)
    gas_price = int(rpc.get_gas_price()["wei"])
    tx = {
        "to": config.energy_pricing_contract_address,
        "from": addr,
        "nonce": nonce,
        "gas": 300_000,
        "gasPrice": gas_price,
        "chainId": config.energy_pricing_chain_id,
        "data": data,
        "value": 0,
    }
    raw = rpc.sign_transaction(tx, private_key)
    tx_hash = rpc.send_raw_transaction(raw)
    receipt = rpc.wait_for_transaction(tx_hash, timeout=120)
    if receipt is None or int(receipt.get("status", 0)) != 1:
        error(f"Registration transaction failed: {tx_hash}")
        sys.exit(1)

    if json_output:
        output(json.dumps({"tx_hash": tx_hash, "status": "confirmed"}, indent=2))
    else:
        success(f"Energy profile registered for {resource_id}")
        info(f"TX hash: {tx_hash}")


@provider.command("profile")
@click.option("--resource-id", required=True, help="Canonical resource ID")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def provider_profile(ctx, resource_id, json_output):
    """Read a registered energy profile from the IEnergyPricing contract."""
    config = get_config()
    if not config.evm_rpc_url:
        error("EVM RPC URL not configured (set EVM_RPC_URL)")
        sys.exit(1)
    if not config.energy_pricing_contract_address:
        error("IEnergyPricing contract address not configured")
        sys.exit(1)

    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.marketplace.energy_oracle import EVMEnergyOracle

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id)))
    oracle = EVMEnergyOracle(rpc, config.energy_pricing_contract_address, config.energy_pricing_chain_id)
    profile = oracle.get_profile(resource_id)

    data = {
        "resource_id": resource_id,
        "enabled": profile.enabled,
        "revision": profile.revision,
        "model_id": profile.model_id,
        "provider": profile.provider,
        "tdp_watts": profile.tdp_watts,
        "eur_per_kwh_scaled": profile.eur_per_kwh_scaled,
        "eur_per_kwh": profile.eur_per_kwh_scaled / 1e18,
    }
    if json_output:
        output(json.dumps(data, indent=2))
    else:
        info(f"Resource:    {resource_id}")
        info(f"Enabled:     {profile.enabled}")
        info(f"Revision:    {profile.revision}")
        info(f"Model:       {profile.model_id}")
        info(f"Provider:    {profile.provider}")
        info(f"TDP:         {profile.tdp_watts}W")
        info(f"EUR/kWh:     {profile.eur_per_kwh_scaled / 1e18:.6f}")


@provider.command("rate")
@click.option("--publish", is_flag=True, help="Publish a new rate (requires wallet)")
@click.option("--ait-per-eur", type=float, help="AIT per EUR rate to publish")
@click.option("--observed-at", type=int, help="Unix timestamp when the rate was observed")
@click.option("--source-kind", default="manual", help="Rate source kind")
@click.option("--wallet", help="Wallet name for signing")
@click.option("--wallet-path", help="Direct wallet file path")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Wallet password file")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def provider_rate(ctx, publish, ait_per_eur, observed_at, source_kind, wallet, wallet_path, password, password_file, json_output):
    """Read or publish the AIT/EUR energy rate."""
    config = get_config()
    if not config.evm_rpc_url:
        error("EVM RPC URL not configured (set EVM_RPC_URL)")
        sys.exit(1)
    if not config.energy_pricing_contract_address:
        error("IEnergyPricing contract address not configured")
        sys.exit(1)

    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.marketplace.energy_oracle import EVMEnergyOracle

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id)))
    oracle = EVMEnergyOracle(rpc, config.energy_pricing_contract_address, config.energy_pricing_chain_id)

    if not publish:
        rate = oracle.get_rate()
        data = {
            "enabled": rate.enabled,
            "version": rate.version,
            "ait_per_eur_scaled": rate.ait_per_eur_scaled,
            "ait_per_eur": rate.ait_per_eur_scaled / 1e18,
            "observed_at": rate.observed_at,
            "submitted_at": rate.submitted_at,
            "source_kind": rate.source_kind,
        }
        if json_output:
            output(json.dumps(data, indent=2))
        else:
            info(f"Enabled:       {rate.enabled}")
            info(f"Version:       {rate.version}")
            info(f"AIT/EUR:       {rate.ait_per_eur_scaled / 1e18:.6f}")
            info(f"Observed at:   {rate.observed_at}")
            info(f"Submitted at:  {rate.submitted_at}")
            info(f"Source:        {rate.source_kind}")
        return

    # Publish a new rate.
    if ait_per_eur is None:
        error("--ait-per-eur is required when --publish is set")
        sys.exit(1)
    import time

    if observed_at is None:
        observed_at = int(time.time())

    pw = password
    if password_file:
        with open(password_file) as f:
            pw = f.read().strip()

    from ..utils.wallet_loader import load_wallet_for_payment

    addr, private_key, _ = load_wallet_for_payment(
        ctx,
        wallet_name=wallet,
        wallet_path=wallet_path,
        password=pw,
        require_private_key=True,
    )
    if private_key is None:
        error("A private key is required to publish a rate")
        sys.exit(1)

    from aitbc.marketplace.energy_oracle import DEFAULT_ENERGY_PRICING_ABI

    scale = 10**18
    ait_scaled = int(ait_per_eur * scale)
    data = rpc.encode_function_call(
        abi=DEFAULT_ENERGY_PRICING_ABI,
        function_name="publishEnergyRate",
        args=[ait_scaled, observed_at, source_kind],
    )
    nonce = rpc._get_web3().eth.get_transaction_count(addr)
    gas_price = int(rpc.get_gas_price()["wei"])
    tx = {
        "to": config.energy_pricing_contract_address,
        "from": addr,
        "nonce": nonce,
        "gas": 200_000,
        "gasPrice": gas_price,
        "chainId": config.energy_pricing_chain_id,
        "data": data,
        "value": 0,
    }
    raw = rpc.sign_transaction(tx, private_key)
    tx_hash = rpc.send_raw_transaction(raw)
    receipt = rpc.wait_for_transaction(tx_hash, timeout=120)
    if receipt is None or int(receipt.get("status", 0)) != 1:
        error(f"Rate publish transaction failed: {tx_hash}")
        sys.exit(1)

    if json_output:
        output(json.dumps({"tx_hash": tx_hash, "status": "confirmed"}, indent=2))
    else:
        success(f"Energy rate published: {ait_per_eur} AIT/EUR")
        info(f"TX hash: {tx_hash}")


@energy.command()
@click.option("--resource-id", required=True, help="Canonical resource ID")
@click.option("--gpu-count", type=int, required=True, help="Number of GPUs")
@click.option("--duration-seconds", type=int, required=True, help="Rental duration in seconds")
@click.option("--settlement-unit-scale", type=int, default=10**18, help="Settlement unit scale")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def floor(ctx, resource_id, gpu_count, duration_seconds, settlement_unit_scale, json_output):
    """Compute the on-chain energy floor for given rental terms."""
    config = get_config()
    if not config.evm_rpc_url:
        error("EVM RPC URL not configured (set EVM_RPC_URL)")
        sys.exit(1)
    if not config.energy_pricing_contract_address:
        error("IEnergyPricing contract address not configured")
        sys.exit(1)

    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.marketplace.energy_oracle import EVMEnergyOracle

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id)))
    oracle = EVMEnergyOracle(rpc, config.energy_pricing_contract_address, config.energy_pricing_chain_id)
    net_floor = oracle.get_energy_floor(
        resource_id=resource_id,
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        settlement_unit_scale=settlement_unit_scale,
    )

    data = {
        "resource_id": resource_id,
        "gpu_count": gpu_count,
        "duration_seconds": duration_seconds,
        "settlement_unit_scale": settlement_unit_scale,
        "net_floor_units": net_floor,
    }
    if json_output:
        output(json.dumps(data, indent=2))
    else:
        info(f"Resource:    {resource_id}")
        info(f"GPUs:        {gpu_count}")
        info(f"Duration:    {duration_seconds}s")
        info(f"Scale:       {settlement_unit_scale}")
        info(f"Net floor:   {net_floor} units")
