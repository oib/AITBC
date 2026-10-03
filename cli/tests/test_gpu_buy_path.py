"""Protected GPU buy path regressions found in the live buy (2026-10-03).

- ``get_node_wallet`` must fail loudly and name ``blockchain_rpc_url`` when the
  configured RPC cannot serve the wallet: the public hub endpoint proxies
  ``/rpc/*`` only, and its root ``/health`` is answered by a different service
  (the agent-coordinator), never by the blockchain RPC.
- ``market gpu quote`` must refuse a non-address ``--buyer-id`` on the native
  rail *before* POSTing: the coordinator copies it verbatim into the signed
  quote's ``buyer`` field, and ``market gpu buy`` can only fund a quote whose
  buyer equals the signing wallet — so such a quote can never be bought.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc.exceptions import NetworkError as HTTPNetworkError
from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.escrow import get_node_wallet

ACCOUNT = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20
NODE_WALLET = "0x" + "33" * 20
UUID_BUYER = "3f2c9a1b-7d4e-4c1a-9b2e-5d6f7a8b9c0d"
PUBLIC_URL = "https://hub.aitbc.bubuit.net"
DOMAIN = "aitbc.energy.quote.v1"
RESOLVED = "ait-hub.aitbc.bubuit.net"


@pytest.fixture
def runner():
    return CliRunner()


def _health_client(*, payload=None, error=None):
    """Patch the escrow module's HTTP client; ``error`` is raised, else ``payload`` returned."""
    client = MagicMock()
    if error is not None:
        client.get.side_effect = error
    else:
        client.get.return_value = payload if payload is not None else {}
    return patch("aitbc_cli.utils.escrow.AITBCHTTPClient", return_value=client)


# --- get_node_wallet -------------------------------------------------------


def test_node_wallet_preferred_over_proposer():
    """/health with both fields returns the node wallet, not the proposer."""
    wallet = "0x" + "ab" * 20
    with _health_client(payload={"node_wallet": wallet, "proposer_id": "0x" + "99" * 20}):
        result = get_node_wallet(None, "http://127.0.0.1:8202")
    assert result.lower() == wallet.lower()
    assert result.startswith("0x")


def test_node_wallet_proposer_fallback_for_legacy_nodes():
    """A node that predates the field reports only proposer_id; use it."""
    with _health_client(payload={"proposer_id": NODE_WALLET}):
        result = get_node_wallet(None, "http://127.0.0.1:8202")
    assert result.lower() == NODE_WALLET.lower()


def test_node_wallet_unreachable_names_config_key():
    """An unreachable /health aborts naming blockchain_rpc_url.

    On the old source the message was just "Cannot reach blockchain RPC at
    <url>" — no hint about which config value repoints the lookup.
    """
    with (
        _health_client(error=HTTPNetworkError("GET request failed: 404 Client Error")),
        pytest.raises(CLIError) as excinfo,
    ):
        get_node_wallet(None, PUBLIC_URL)
    text = str(excinfo.value) + getattr(excinfo.value, "message", "")
    assert "Cannot determine the escrow node wallet" in text
    assert "blockchain_rpc_url" in text


def test_node_wallet_foreign_service_names_config_key():
    """A 200 /health without the fields means a different service answered.

    This is the public-proxy failure: the hub's root /health is the
    agent-coordinator's, which returns neither node_wallet nor proposer_id.
    """
    with (
        _health_client(payload={"service": "agent-coordinator", "status": "healthy"}),
        pytest.raises(CLIError) as excinfo,
    ):
        get_node_wallet(None, PUBLIC_URL)
    text = str(excinfo.value) + getattr(excinfo.value, "message", "")
    assert "blockchain_rpc_url" in text
    assert "different service" in text


# --- market gpu quote --buyer-id --------------------------------------------


def _quote_dict(chain_id: str, route: str = "native") -> dict:
    """A structurally valid, unexpired quote for ``chain_id`` and ``route``."""
    from aitbc.market.energy_pricing import EnergyQuote, SettlementRoute
    from aitbc_cli.utils.address import to_canonical
    from aitbc_cli.utils.energy_quote import compute_energy_net_units

    now = int(time.time())
    floor = compute_energy_net_units(
        tbp_watts=100,
        eur_per_kwh_scaled=30 * 10**16,
        ait_per_eur_scaled=10**18,
        gpu_count=1,
        duration_seconds=3600,
        settlement_unit_scale=10**18,
    )
    q = EnergyQuote(
        domain=DOMAIN,
        chain_id=chain_id,
        settlement_asset="AITBC",
        settlement_unit_scale=10**18,
        buyer=to_canonical(ACCOUNT),
        provider=PROVIDER,
        job_id="job-1",
        quote_id="q-1",
        settlement_route=SettlementRoute(route),
        resource_id="res-1",
        model_id="m-1",
        gpu_count=1,
        duration_seconds=3600,
        eur_per_kwh_scaled=30 * 10**16,
        tbp_watts=100,
        ait_per_eur_scaled=10**18,
        rate_version=1,
        rate_observed_at=now,
        rate_source_kind="manual",
        profile_revision=1,
        net_energy_floor_units=floor,
        principal_units=floor * 2,
        issued_at=now,
        expires_at=now + 300,
        operator_signature=b"\xde\xad\xbe\xef",
    )
    return q.to_dict(include_signature=True)


def _config():
    c = MagicMock()
    c.native_chain_id = ""
    c.blockchain_rpc_url = "http://localhost:8202"
    c.coordinator_api_url = "http://localhost:8203"
    c.energy_operator_address = None
    c.energy_quote_domain = DOMAIN
    c.energy_max_rate_age_seconds = 86400  # real int: the field is an int in CLIConfig
    return c


def _ok_probe(chain_id=RESOLVED):
    prober = MagicMock()
    prober.get.return_value = {"chain_id": chain_id}
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _invoke(runner, args, obj=None):
    from aitbc_cli.commands.market import market

    base = {"output_format": "table", "api_key": "k"}
    base.update(obj or {})
    return runner.invoke(market, args, obj=base)


def _quote_patches(config, result_quote_dict):
    client = MagicMock()
    client.post.return_value = {"energy_quote": result_quote_dict, "buyer_charge_ait": "1"}
    return (
        patch("aitbc_cli.commands.market.gpu.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.market.gpu.get_config", return_value=config),
        patch("aitbc_cli.config.get_config", return_value=config),
        client,
    )


def test_quote_refuses_non_address_buyer_on_native(runner):
    """A UUID --buyer-id mints a quote whose buyer can never equal a wallet.

    The refusal must happen before the coordinator POST — no dead quote and
    no bound job. Fails on the old source, which POSTs and exits 0.
    """
    config = _config()
    *patches, client = _quote_patches(config, _quote_dict(RESOLVED))
    with patches[0], patches[1], patches[2], _ok_probe():
        result = _invoke(runner, ["gpu", "quote", "--gpu-id", "g1", "--buyer-id", UUID_BUYER])
    assert result.exit_code != 0
    assert "--buyer-id" in result.output
    assert "wallet" in result.output
    client.post.assert_not_called()


def test_quote_allows_non_address_buyer_on_evm(runner):
    """The gate is scoped to the native rail; an EVM quote still POSTs.

    (A UUID buyer on EVM is still unfundable downstream — buy's wallet-vs-
    quote.buyer check is rail-agnostic — but the quote-time refusal is a
    native-rail change only.)
    """
    config = _config()
    *patches, client = _quote_patches(config, _quote_dict(RESOLVED, route="evm"))
    with patches[0], patches[1], patches[2], _ok_probe():
        result = _invoke(
            runner,
            ["gpu", "quote", "--gpu-id", "g1", "--buyer-id", UUID_BUYER, "--settlement", "evm"],
        )
    assert result.exit_code == 0, result.output
    client.post.assert_called_once()


def test_quote_accepts_wallet_buyer_on_native(runner):
    """The success path is unchanged: a 0x buyer-id POSTs and verifies."""
    config = _config()
    *patches, client = _quote_patches(config, _quote_dict(RESOLVED))
    with patches[0], patches[1], patches[2], _ok_probe():
        result = _invoke(runner, ["gpu", "quote", "--gpu-id", "g1", "--buyer-id", ACCOUNT])
    assert result.exit_code == 0, result.output
    client.post.assert_called_once()
