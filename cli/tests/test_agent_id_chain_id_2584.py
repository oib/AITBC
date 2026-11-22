"""#2584: agent-identity resolve must accept the deployment's named chain id.

``market run``, ``ai pay``/``ai submit`` and ``market escrow create`` used
to ``int()`` the chain id (``bc-2``) before calling the resolve API, which
expects the integer registry id. The mapping now lives inside
``resolve_escrow_parties``/``agent_registry_chain_id`` so no caller
converts; ``escrow create`` resolves the chain via ``get_chain_id()``
instead of defaulting to 1.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import aitbc_cli.utils.agent_identity_resolve as air

ACCOUNT = "0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f"
PROVIDER = "0x1111111111111111111111111111111111111111"
NODE_WALLET = "0x9dAd8eE274d92F6d02Df0a5F51cf80d9990E70DA"


@pytest.fixture
def runner():
    return CliRunner()


# --- resolve_escrow_parties mapping ------------------------------------------


def test_resolve_escrow_parties_maps_named_chain_to_registry_id():
    ctx = MagicMock()
    with patch.object(air, "resolve_agent_payment_address", return_value="0xresolved") as spy:
        air.resolve_escrow_parties(
            ctx,
            buyer=None,
            provider=PROVIDER,
            buyer_agent_id="agent-b",
            chain_id="bc-2",
        )
    assert spy.call_args.args[2] == 1


def test_resolve_escrow_parties_numeric_and_default_chain():
    ctx = MagicMock()
    with patch.object(air, "resolve_agent_payment_address", return_value="0xresolved") as spy:
        air.resolve_escrow_parties(ctx, buyer=None, provider=PROVIDER, buyer_agent_id="a", chain_id="7")
        assert spy.call_args.args[2] == 7
        air.resolve_escrow_parties(ctx, buyer=None, provider=PROVIDER, buyer_agent_id="a")
        assert spy.call_args.args[2] == 1


# --- market run helper --------------------------------------------------------


def test_market_run_escrow_parties_passes_named_chain_through():
    import aitbc_cli.commands.market.jobs as jobs_mod

    with (
        patch.object(jobs_mod, "get_chain_id", return_value="bc-2"),
        patch.object(air, "resolve_escrow_parties", return_value=("0xb", "0xp", "ba", "pa")) as spy,
    ):
        out = jobs_mod._escrow_parties_for_market_run(MagicMock(), ACCOUNT, PROVIDER, "agent-b", None)
    assert out == ("0xb", "0xp", "ba", "pa")
    assert spy.call_args.kwargs["chain_id"] == "bc-2"


# --- market escrow create -----------------------------------------------------


def test_escrow_create_resolves_agent_ids_on_named_chain(runner):
    import aitbc_cli.commands.market.escrow as escrow_mod

    resolve_spy = MagicMock(return_value="0xresolved")
    with (
        patch.object(escrow_mod, "get_config", return_value=MagicMock()),
        patch("aitbc_cli.commands.market.get_chain_id", return_value="bc-2"),
        patch.object(air, "resolve_agent_payment_address", resolve_spy),
        patch(
            "aitbc_cli.utils.wallet_loader.load_wallet_for_payment",
            return_value=(None, "0xprivate", None),
        ),
        patch.object(escrow_mod, "_escrow_create", return_value="0xcontract"),
    ):
        result = runner.invoke(
            escrow_mod.escrow,
            [
                "create",
                "--job-id",
                "job-1",
                "--provider",
                PROVIDER,
                "--buyer-agent-id",
                "agent-b",
            ],
            obj={"output_format": "table", "api_key": "k"},
        )
    assert result.exit_code == 0, result.output
    assert resolve_spy.call_args.args[2] == 1


# --- ai submit end-to-end -----------------------------------------------------


@pytest.fixture
def ai_patches():
    client = MagicMock()
    client.post.side_effect = [
        {
            "job_id": "job-1",
            "state": "QUEUED",
            "payment_amount": "5",
            "payment_token": "AIT",
            "node_wallet_address": NODE_WALLET,
            "provider_address": PROVIDER,
        },
        {"payment_id": "pay-1"},
    ]
    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.blockchain_rpc_url = "http://localhost:8202"
    config.api_key = "k"
    config.timeout = 10
    wallet = (ACCOUNT, "0xprivate", "default")
    with (
        patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.ai.get_config", return_value=config),
        patch("aitbc_cli.commands.ai.load_wallet_for_payment", return_value=wallet),
        patch("aitbc_cli.commands.ai.create_signed_escrow_lock") as escrow_spy,
        patch("aitbc_cli.commands.ai.get_buyer_nonce", return_value=7),
    ):
        escrow_spy.return_value = ({"from": ACCOUNT, "payload": {"provider": PROVIDER}, "nonce": 1, "fee": "1"}, "0xsig")
        yield client, escrow_spy


def test_ai_submit_agent_id_with_named_chain_reaches_resolve(runner, ai_patches):
    from aitbc_cli.utils.address import to_canonical

    client, _ = ai_patches
    resolve_spy = MagicMock(return_value=to_canonical(ACCOUNT))
    with (
        patch.object(air, "resolve_agent_payment_address", resolve_spy),
        patch("aitbc_cli.utils.chain_id.AITBCHTTPClient") as probe_cls,
    ):
        probe_cls.return_value.get.return_value = {"chain_id": "bc-2"}
        from aitbc_cli.commands.ai import ai

        result = runner.invoke(
            ai,
            [
                "submit",
                "--prompt",
                "hi",
                "--payment",
                "5",
                "--provider-address",
                PROVIDER,
                "--wallet",
                "w",
                "--chain-id",
                "bc-2",
                "--buyer-agent-id",
                "agent-b1",
            ],
            obj={"output_format": "table", "api_key": "k"},
        )
    assert result.exit_code == 0, result.output
    assert resolve_spy.call_args.args[2] == 1
