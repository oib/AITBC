"""Energy operator and provider CLI commands.

Commands:
  aitbc energy operator info     - Show configured operator key/address
  aitbc energy operator verify   - Verify an energy quote's operator signature
  aitbc energy provider register - Register a GPU energy profile (EVM or native rail)
  aitbc energy provider profile  - Read a registered energy profile (EVM or native rail)
  aitbc energy provider rate     - Read or publish the AIT/EUR rate (EVM or native rail)
  aitbc energy floor             - Compute or check the energy floor (EVM or native rail)
  aitbc energy suggest           - Hardware-based energy profile and price suggestion

Rail selection is automatic: when ``EVM_RPC_URL`` + ``ENERGY_PRICING_CONTRACT_ADDRESS``
are configured the EVM ``IEnergyPricing`` contract is used; otherwise commands talk to
the coordinator's ``/v1/marketplace/native-energy/*`` endpoints (miner auth for writes).
"""

from __future__ import annotations

import json
import sys

import click

from ..config import get_config
from ..utils import error, info, output, success, warning
from ..utils.energy_quote import (
    parse_quote,
    verify_quote,
    verify_quote_against_oracle,
)
from ..utils.http_client import AITBCHTTPClient, NetworkError, auth_client_kwargs, get_logger, looks_like_jwt

logger = get_logger(__name__)


def _evm_energy_configured() -> bool:
    """True when the CLI can reach the EVM IEnergyPricing contract."""
    config = get_config()
    return bool(config.evm_rpc_url and config.energy_pricing_contract_address)


def _coordinator_base() -> str:
    """Coordinator API base URL (native pricing rail lives here)."""
    config = get_config()
    url = (
        getattr(config, "coordinator_url", None)
        or getattr(config, "coordinator_api_url", None)
        or "http://localhost:8203"
    ).rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url.rstrip("/")


def _coordinator_client(ctx, *, miner: bool = False, timeout: int = 30) -> AITBCHTTPClient:
    """HTTP client for the coordinator, with miner-credential auth when needed."""
    explicit = ctx.obj.get("api_key") if ctx.obj else None
    kwargs = auth_client_kwargs(
        explicit, getattr(get_config(), "api_key", None), credential="miner" if miner else "client"
    )
    return AITBCHTTPClient(base_url=_coordinator_base(), timeout=timeout, **kwargs)


def _native_energy_request(ctx, method: str, path: str, *, miner: bool = False,
                           params: dict | None = None, json_body: dict | None = None,
                           timeout: int = 15) -> dict:
    """Call a ``/v1/marketplace/native-energy/*`` endpoint.

    Native pricing state lives on the hub coordinator; a node's local
    coordinator may be EVM-railed or lack the tables, so fall back to the
    hub mount (``hub_coordinator_url()``) when the local call fails.
    """
    from aitbc.config.hub import hub_coordinator_url

    bases = [_coordinator_base()]
    hub = (hub_coordinator_url() or "").rstrip("/")
    if hub.endswith("/v1"):
        hub = hub[:-3]
    if hub and hub != bases[0]:
        bases.append(hub)

    last: Exception | None = None
    for base in bases:
        kwargs = _miner_client_kwargs(ctx) if miner else auth_client_kwargs(
            ctx.obj.get("api_key") if ctx.obj else None,
            getattr(get_config(), "api_key", None),
        )
        client = AITBCHTTPClient(base_url=base, timeout=timeout, **kwargs)
        try:
            if method == "get":
                return client.get(path, params=params)
            return client.post(path, json=json_body)
        except NetworkError as e:
            last = e
            logger.debug("native-energy %s %s via %s failed: %s", method, path, base, e)
    raise last or NetworkError("no coordinator reachable")


def _miner_client_kwargs(ctx) -> dict:
    """Miner credentials: ``--api-key``, the stored ``miner`` credential, or the
    configured API key (``MINER_API_KEYS`` in the coordinator env file).

    Deliberately skips the ``client`` credential fallback — a client-role JWT can
    never satisfy a miner-gated endpoint, and sending it would suppress the
    ``X-Api-Key`` miner key that does.
    """
    from ..auth import AuthManager  # late import: auth imports ..utils

    explicit = ctx.obj.get("api_key") if ctx.obj else None
    token = explicit or AuthManager().get_credential("miner", quiet=True)
    if not token:
        token = getattr(get_config(), "api_key", None)
    if not token:
        return {}
    if looks_like_jwt(token):
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"api_key": token}


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
@click.option("--tbp-watts", type=int, required=True, help="GPU TBP (total board power) in watts")
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
    tbp_watts,
    eur_per_kwh,
    wallet,
    wallet_path,
    password,
    password_file,
    json_output,
):
    """Register a GPU energy profile (EVM contract or native rail)."""
    config = get_config()
    if not _evm_energy_configured():
        try:
            result = _native_energy_request(
                ctx, "post", "/v1/marketplace/native-energy/profile",
                miner=True,
                json_body={
                    "resource_id": resource_id,
                    "provider": provider_address,
                    "model_id": model_id,
                    "tbp_watts": tbp_watts,
                    "eur_per_kwh": eur_per_kwh,
                },
            )
        except NetworkError as e:
            error(f"Native profile registration failed: {e}")
            sys.exit(1)
        if json_output:
            output(json.dumps(result, indent=2))
        else:
            success(f"Native energy profile registered for {resource_id} ({tbp_watts}W, {eur_per_kwh} EUR/kWh)")
        return
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
        args=[resource_id, provider_address, model_id, tbp_watts, eur_scaled],
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
    """Read a registered energy profile (EVM contract or native rail)."""
    config = get_config()
    if not _evm_energy_configured():
        try:
            data = _native_energy_request(
                ctx, "get", f"/v1/marketplace/native-energy/profile/{resource_id}", timeout=10
            )
        except NetworkError as e:
            error(f"Native energy profile lookup failed: {e}")
            sys.exit(1)
        if json_output:
            output(json.dumps(data, indent=2))
        else:
            info("Rail:        native (coordinator DB)")
            info(f"Resource:    {data.get('resource_id')}")
            info(f"Enabled:     {data.get('enabled')}")
            info(f"Revision:    {data.get('revision')}")
            info(f"Model:       {data.get('model_id')}")
            info(f"Provider:    {data.get('provider')}")
            info(f"TBP:         {data.get('tbp_watts')}W")
            info(f"EUR/kWh:     {data.get('eur_per_kwh')}")
        return
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
        "tbp_watts": profile.tbp_watts,
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
        info(f"TBP:         {profile.tbp_watts}W")
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
def provider_rate(
    ctx, publish, ait_per_eur, observed_at, source_kind, wallet, wallet_path, password, password_file, json_output
):
    """Read or publish the AIT/EUR energy rate (EVM contract or native rail)."""
    config = get_config()
    if not _evm_energy_configured():
        if not publish:
            try:
                data = _native_energy_request(
                    ctx, "get", "/v1/marketplace/native-energy/rate", miner=True, timeout=10
                )
            except NetworkError as e:
                error(f"Native energy rate lookup failed: {e}")
                sys.exit(1)
            if json_output:
                output(json.dumps(data, indent=2))
            else:
                info("Rail:          native (coordinator DB)")
                info(f"Enabled:       {data.get('enabled')}")
                info(f"Version:       {data.get('version')}")
                info(f"AIT/EUR:       {data.get('ait_per_eur')}")
                info(f"Source:        {data.get('source_kind')}")
            return
        if ait_per_eur is None:
            error("--ait-per-eur is required when --publish is set")
            sys.exit(1)
        try:
            result = _native_energy_request(
                ctx, "post", "/v1/marketplace/native-energy/rate",
                miner=True,
                json_body={"ait_per_eur": ait_per_eur, "source_kind": source_kind},
            )
        except NetworkError as e:
            error(f"Native rate publish failed: {e}")
            sys.exit(1)
        if json_output:
            output(json.dumps(result, indent=2))
        else:
            success(f"Native energy rate published: {ait_per_eur} AIT/EUR (v{result.get('version')})")
        return
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
    calldata = rpc.encode_function_call(
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
        "data": calldata,
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
    """Compute the energy floor for given rental terms (EVM or native rail)."""
    config = get_config()
    if not (config.evm_rpc_url and config.energy_pricing_contract_address):
        try:
            result = _native_energy_request(
                ctx, "get", "/v1/marketplace/native-energy/floor",
                params={
                    "resource_id": resource_id,
                    "gpu_count": gpu_count,
                    "duration_seconds": duration_seconds,
                },
                timeout=10,
            )
        except NetworkError as e:
            error(f"Native energy floor lookup failed: {e}")
            sys.exit(1)
        data = {
            "rail": "native",
            "resource_id": resource_id,
            "gpu_count": gpu_count,
            "duration_seconds": duration_seconds,
            "settlement_unit_scale": result.get("settlement_unit_scale"),
            "net_floor_units": result.get("net_floor_units"),
            "net_floor_ait": result.get("net_floor_ait"),
        }
        if json_output:
            output(json.dumps(data, indent=2))
        else:
            info("Rail:        native (coordinator DB)")
            info(f"Resource:    {resource_id}")
            info(f"GPUs:        {gpu_count}")
            info(f"Duration:    {duration_seconds}s")
            info(f"Scale:       {result.get('settlement_unit_scale')}")
            info(f"Net floor:   {result.get('net_floor_units')} units ({result.get('net_floor_ait')} AIT)")
        return

    from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
    from aitbc.marketplace.energy_oracle import EVMEnergyOracle

    rpc = EthereumRPCClient(EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id)))
    oracle = EVMEnergyOracle(rpc, config.energy_pricing_contract_address, config.energy_pricing_chain_id)
    net_floor = oracle.get_floor(
        resource_id=resource_id,
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        settlement_unit_scale=settlement_unit_scale,
    )

    data = {
        "rail": "evm",
        "resource_id": resource_id,
        "gpu_count": gpu_count,
        "duration_seconds": duration_seconds,
        "settlement_unit_scale": settlement_unit_scale,
        "net_floor_units": net_floor,
    }
    if json_output:
        output(json.dumps(data, indent=2))
    else:
        info("Rail:        evm (IEnergyPricing contract)")
        info(f"Resource:    {resource_id}")
        info(f"GPUs:        {gpu_count}")
        info(f"Duration:    {duration_seconds}s")
        info(f"Scale:       {settlement_unit_scale}")
        info(f"Net floor:   {net_floor} units")


@energy.command(
    epilog="""Examples:

  aitbc energy suggest --region de

  aitbc energy suggest --gpu-model "RTX 4090" --eur-per-kwh 0.28

  aitbc energy suggest --resource-id gpu-01 --provider-address 0x.. --register --wallet provider"""
)
@click.option("--gpu-model", help="GPU model override (skips nvidia-smi detection)")
@click.option("--tbp-watts", type=int, help="Explicit per-GPU board watts (highest precedence)")
@click.option("--gpu-count", type=int, default=1, help="GPUs covered by one registered resource")
@click.option("--node-gpu-count", type=int, help="Total GPUs in this node (platform draw is shared across them)")
@click.option("--cpu-watts", type=int, help="CPU sustained watts override")
@click.option("--platform-watts", type=int, help="Board/RAM/fans/storage overhead override in watts")
@click.option("--region", help="Region code for the tariff table (or SHOP_REGION env)")
@click.option("--eur-per-kwh", type=float, help="Electricity tariff in EUR/kWh (or ENERGY_EUR_PER_KWH env)")
@click.option("--ait-per-eur", type=float, help="AIT/EUR rate override (default: on-chain rate, else 4.0)")
@click.option("--duration-seconds", type=int, default=3600, help="Floor horizon in seconds (default 1h)")
@click.option("--resource-id", help="Resource ID used in the printed registration command / --register")
@click.option("--provider-address", help="Provider wallet address (required for --register)")
@click.option("--model-id", help="Model ID for registration (default: detected model)")
@click.option("--wallet", help="Wallet name for signing (with --register)")
@click.option("--wallet-path", help="Direct wallet file path (with --register)")
@click.option("--password", help="Wallet password (with --register)")
@click.option("--password-file", type=click.Path(exists=True), help="Wallet password file (with --register)")
@click.option("--register", is_flag=True, help="Submit the on-chain energy profile registration")
@click.option("--json-output", is_flag=True, help="Output raw JSON")
@click.pass_context
def suggest(
    ctx,
    gpu_model,
    tbp_watts,
    gpu_count,
    node_gpu_count,
    cpu_watts,
    platform_watts,
    region,
    eur_per_kwh,
    ait_per_eur,
    duration_seconds,
    resource_id,
    provider_address,
    model_id,
    wallet,
    wallet_path,
    password,
    password_file,
    register,
    json_output,
):
    """Suggest a hardware-based energy profile and market price.

    Probes the local node (nvidia-smi power limit = real GPU TBP, lscpu CPU
    model), sums the whole-node draw, applies the electricity tariff, and
    prints the resulting energy floor plus the compute-multiplier market
    price suggestion (1 AIT = one reference compute-hour = EUR 0.25).
    """
    from aitbc.marketplace.energy_pricing import (
        FIXED_POINT_SCALE,
        NATIVE_UNITS_PER_AIT,
        compute_energy_net_units,
    )
    from aitbc.marketplace.hardware_catalog import (
        BASE_PLATFORM_W,
        compute_multiplier,
        estimate_node_power,
        normalize_cpu_model,
        normalize_gpu_model,
        region_tariff,
        resolve_cpu_watts,
        resolve_gpu_tbp,
    )
    from ..utils.hardware_probe import probe_cpu_model, probe_gpus

    config = get_config()
    scale = int(FIXED_POINT_SCALE)

    # --- hardware -----------------------------------------------------------
    gpus = [] if gpu_model or tbp_watts else probe_gpus()
    primary = gpus[0] if gpus else None
    model_key = normalize_gpu_model(
        gpu_model or (primary.name if primary else ""),
        memory_gb=(primary.memory_gb if primary else None),
    )
    gpu_tbp, gpu_src = resolve_gpu_tbp(
        model_key=model_key,
        power_limit_w=(primary.power_limit_w if primary else None),
        explicit_watts=tbp_watts,
    )
    if gpu_tbp <= 0:
        error("Could not determine GPU TBP — pass --gpu-model/--tbp-watts")
        sys.exit(1)

    cpu_key = normalize_cpu_model(probe_cpu_model() or "")
    cpu_w, cpu_src = resolve_cpu_watts(cpu_key, cpu_watts)
    node_gpus = node_gpu_count or max(1, len(gpus))
    est = estimate_node_power(
        gpu_tbp_w=gpu_tbp,
        gpu_w_source=gpu_src,
        gpu_model_key=model_key or None,
        gpu_count=gpu_count,
        node_gpu_count=node_gpus,
        cpu_watts=cpu_w,
        cpu_w_source=cpu_src,
        platform_watts=platform_watts if platform_watts is not None else BASE_PLATFORM_W,
    )

    # --- tariff --------------------------------------------------------------
    from decimal import Decimal

    tariff: Decimal | None = None
    tariff_src = ""
    if eur_per_kwh is not None:
        tariff, tariff_src = Decimal(str(eur_per_kwh)), "manual"
    elif config.energy_eur_per_kwh is not None:
        tariff, tariff_src = Decimal(str(config.energy_eur_per_kwh)), "ENERGY_EUR_PER_KWH"
    else:
        region_code = region or config.shop_region
        tariff = region_tariff(region_code)
        if tariff is not None and region_code:
            tariff_src = f"region table ({region_code.lower()})"
    if tariff is None or tariff <= 0:
        error("No electricity tariff — pass --eur-per-kwh, set ENERGY_EUR_PER_KWH, or use --region")
        sys.exit(1)

    # --- AIT/EUR rate ---------------------------------------------------------
    rate: Decimal | None = None
    rate_src = ""
    if ait_per_eur is not None:
        rate, rate_src = Decimal(str(ait_per_eur)), "manual"
    elif config.evm_rpc_url and config.energy_pricing_contract_address:
        try:
            from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient
            from aitbc.marketplace.energy_oracle import EVMEnergyOracle

            rpc = EthereumRPCClient(
                EthereumConfig(rpc_url=config.evm_rpc_url, network=str(config.energy_pricing_chain_id))
            )
            oracle = EVMEnergyOracle(rpc, config.energy_pricing_contract_address, config.energy_pricing_chain_id)
            rate = Decimal(oracle.get_rate().ait_per_eur_scaled) / scale
            rate_src = "on-chain rate"
        except Exception as exc:  # oracle unavailable -> reference fallback
            logger.warning("On-chain rate read failed (%s); using reference", exc)
    if rate is None and not config.evm_rpc_url:
        # native rail: the published rate lives in the coordinator DB
        try:
            result = _native_energy_request(
                ctx, "get", "/v1/marketplace/native-energy/rate", miner=True, timeout=10
            )
            native_rate = Decimal(str(result["ait_per_eur"]))
            if native_rate > 0:
                rate, rate_src = native_rate, "native rate"
        except Exception as exc:  # coordinator unavailable -> reference fallback
            logger.warning("Native rate read failed (%s); using reference", exc)
    if rate is None:
        from aitbc.oracles.price_oracle import AIT_REFERENCE_PRICE_EUR

        rate, rate_src = Decimal(1) / AIT_REFERENCE_PRICE_EUR, "EUR 0.25 reference"

    # --- floor + suggestion ---------------------------------------------------
    floor_units = compute_energy_net_units(
        tbp_watts=est.register_watts,
        eur_per_kwh_scaled=int(tariff * scale),
        ait_per_eur_scaled=int(rate * scale),
        gpu_count=gpu_count,
        duration_seconds=duration_seconds,
        settlement_unit_scale=NATIVE_UNITS_PER_AIT,
    )
    floor_ait = Decimal(floor_units) / NATIVE_UNITS_PER_AIT
    floor_per_hour = floor_ait * Decimal(3600) / duration_seconds
    node_eur_hour = (Decimal(est.node_wall_watts) / 1000) * tariff

    mult = compute_multiplier(model_key or None)
    suggested = mult if mult is not None else None

    data = {
        "gpu_model": model_key or None,
        "gpu_tbp_watts": est.gpu_tbp_w,
        "gpu_tbp_source": est.gpu_w_source,
        "cpu_watts": est.cpu_watts,
        "cpu_source": est.cpu_w_source,
        "platform_watts": est.platform_watts,
        "node_gpu_count": est.node_gpu_count,
        "node_wall_watts": est.node_wall_watts,
        "register_watts": est.register_watts,
        "eur_per_kwh": str(tariff),
        "tariff_source": tariff_src,
        "ait_per_eur": str(rate),
        "rate_source": rate_src,
        "duration_seconds": duration_seconds,
        "energy_floor_ait": str(floor_ait),
        "energy_floor_ait_per_hour": str(floor_per_hour),
        "node_eur_per_hour": str(node_eur_hour),
        "compute_multiplier": str(mult) if mult is not None else None,
        "suggested_ait_per_hour": str(suggested) if suggested is not None else None,
    }
    if json_output:
        output(json.dumps(data, indent=2))
    else:
        info(f"GPU:           {gpu_model or (primary.name if primary else '?')} — TBP {est.gpu_tbp_w}W ({est.gpu_w_source})")
        info(f"CPU:           {cpu_key or '?'} — {est.cpu_watts}W ({est.cpu_w_source})")
        info(f"Platform:      {est.platform_watts}W board/RAM/PSU overhead")
        info(f"Node draw:     {est.node_wall_watts}W at the wall ({est.node_gpu_count} GPU(s))")
        info(f"Register as:   {est.register_watts}W per resource (platform shared over node GPUs)")
        info(f"Tariff:        {tariff} EUR/kWh ({tariff_src})")
        info(f"AIT/EUR:       {rate} ({rate_src})")
        info(f"Energy floor:  {floor_per_hour:.4f} AIT/h ({node_eur_hour:.4f} EUR/h node electricity)")
        if suggested is not None:
            info(f"Suggested:     {suggested} AIT/h (compute multiplier {suggested}x = EUR {suggested * Decimal('0.25')}/h)")
            if suggested < floor_per_hour:
                warning(f"Suggested price is below the energy floor ({floor_per_hour:.4f} AIT/h) — raise tariff margin")
        else:
            warning("No compute multiplier for this GPU model — set price manually at or above the floor")
        info("")
        rid = resource_id or "<resource-id>"
        prov = provider_address or "<provider-address>"
        mid = model_id or model_key or "<model-id>"
        if not register:
            info("Apply with:")
            if _evm_energy_configured():
                info(f"  aitbc energy provider register --resource-id {rid} --provider-address {prov} "
                     f"--model-id {mid} --tbp-watts {est.register_watts} --eur-per-kwh {tariff} --wallet <wallet>")
                info("  (native quotes also need POST /v1/marketplace/native-energy/profile with the same watts/tariff)")
            else:
                info(f"  aitbc energy suggest --register --resource-id {rid} --provider-address {prov} "
                     f"--model-id {mid} --tbp-watts {est.register_watts} --eur-per-kwh {tariff}")
                info("  (posts the profile to the coordinator's native-energy endpoint)")
        if suggested is not None:
            info(f"  aitbc gpu update --gpu-id <gpu-id> --pricing '{{\"price_per_hour\": {suggested}}}'")

    if register:
        if not (resource_id and provider_address):
            error("--register requires --resource-id and --provider-address")
            sys.exit(1)
        if _evm_energy_configured():
            ctx.invoke(
                provider_register,
                resource_id=resource_id,
                provider_address=provider_address,
                model_id=model_id or model_key or resource_id,
                tbp_watts=est.register_watts,
                eur_per_kwh=float(tariff),
                wallet=wallet,
                wallet_path=wallet_path,
                password=password,
                password_file=password_file,
                json_output=json_output,
            )
            return
        # native rail: upsert the profile on the coordinator (miner auth)
        try:
            result = _native_energy_request(
                ctx, "post", "/v1/marketplace/native-energy/profile",
                miner=True,
                json_body={
                    "resource_id": resource_id,
                    "provider": provider_address,
                    "model_id": model_id or model_key or resource_id,
                    "tbp_watts": est.register_watts,
                    "eur_per_kwh": float(tariff),
                },
            )
        except NetworkError as e:
            error(f"Native profile registration failed: {e}")
            sys.exit(1)
        if json_output:
            output(json.dumps(result, indent=2))
        else:
            success(f"Native energy profile registered: {resource_id} ({est.register_watts}W, {tariff} EUR/kWh)")
