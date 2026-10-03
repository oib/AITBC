"""Fail-loud chain-id resolution on the remaining signing paths.

These commands used to fall back to ``config.chain_id`` /
``config.native_chain_id`` (both defaulting to ``ait-localnet``) when no
explicit chain id was given, signing a transaction no node serves. They now
resolve explicit flag > CHAIN_ID > strict probe of the submit URL, aborting
otherwise. Tests mock every RPC/coordinator client; nothing is signed or sent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.utils.error_handling import CLIError

ACCOUNT = "0x6dB6EBAda5ab0d00041FDCa3a409EE0aA15B5F2f"
PROVIDER = "0x17B9ED0c7b8b0d0B30Fa3d4BbE2F6a0Abb679d"
NODE_WALLET = "0x9dAd8eE274d92F6d02Df0a5F51cf80d9990E70DA"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ai_patches():
    """Coordinator/client seams for ``aitbc ai``; job POST returns an unpaid
    job so the escrow path runs."""
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
    ):
        escrow_spy.return_value = ({"from": ACCOUNT, "payload": {"provider": PROVIDER}, "nonce": 1, "fee": "1"}, "0xsig")
        yield client, escrow_spy


def _failing_probe():
    """Patch the chain-id prober so every lookup fails."""
    prober = MagicMock()
    prober.get.side_effect = RuntimeError("connection refused")
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


def _ok_probe(chain_id="ait-hub-chain"):
    prober = MagicMock()
    prober.get.return_value = {"chain_id": chain_id}
    return patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=prober)


SUBMIT_ARGS = [
    "submit",
    "--prompt",
    "hi",
    "--payment",
    "5",
    "--provider-address",
    PROVIDER,
    "--wallet",
    "w",
]

PAY_ARGS = ["pay", "--job-id", "job-1", "--wallet", "w"]


def _invoke_ai(runner, args, **env):
    from aitbc_cli.commands.ai import ai

    return runner.invoke(ai, args, obj={"output_format": "table", "api_key": "k"})


def test_ai_submit_aborts_when_chain_probe_fails(runner, ai_patches):
    client, escrow_spy = ai_patches
    with _failing_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    assert "chain" in (result.output + str(result.exception)).lower()
    escrow_spy.assert_not_called()


def test_ai_submit_chain_id_env_wins(runner, ai_patches, monkeypatch):
    client, escrow_spy = ai_patches
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    with _failing_probe() as prober_cls:
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert escrow_spy.call_args.kwargs["chain_id"] == "env-chain"


def test_ai_submit_chain_id_flag_wins(runner, ai_patches):
    client, escrow_spy = ai_patches
    with _failing_probe() as prober_cls:
        result = _invoke_ai(runner, [*SUBMIT_ARGS, "--chain-id", "flag-chain"])
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert escrow_spy.call_args.kwargs["chain_id"] == "flag-chain"


def test_ai_submit_success_uses_probed_chain_id(runner, ai_patches):
    client, escrow_spy = ai_patches
    with _ok_probe("ait-probed"):
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code == 0, result.output
    assert escrow_spy.call_args.kwargs["chain_id"] == "ait-probed"


def test_ai_pay_aborts_when_chain_probe_fails(runner, ai_patches):
    client, escrow_spy = ai_patches
    client.post.side_effect = None
    client.post.return_value = {"payment_id": "pay-1"}
    client.get.return_value = {
        "job_id": "job-1",
        "payment_amount": "5",
        "payment_token": "AIT",
        "node_wallet_address": NODE_WALLET,
        "buyer_address": ACCOUNT,
        "provider_address": PROVIDER,
    }
    with _failing_probe():
        result = _invoke_ai(runner, PAY_ARGS)
    assert result.exit_code != 0
    escrow_spy.assert_not_called()


def test_ai_pay_chain_id_flag_wins(runner, ai_patches):
    client, escrow_spy = ai_patches
    client.post.side_effect = None
    client.post.return_value = {"payment_id": "pay-1"}
    client.get.return_value = {
        "job_id": "job-1",
        "payment_amount": "5",
        "payment_token": "AIT",
        "node_wallet_address": NODE_WALLET,
        "buyer_address": ACCOUNT,
        "provider_address": PROVIDER,
    }
    with _failing_probe() as prober_cls:
        result = _invoke_ai(runner, [*PAY_ARGS, "--chain-id", "flag-chain"])
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    assert escrow_spy.call_args.kwargs["chain_id"] == "flag-chain"


# --- market gpu buy (_buy_native) -------------------------------------------


def _gpu_ctx():
    ctx = MagicMock()
    ctx.obj = {"output_format": "table", "api_key": "k"}
    return ctx


def _gpu_patches(prober_patch):
    from aitbc_cli.commands.market import gpu as market_gpu

    parsed = MagicMock()
    parsed.provider = PROVIDER
    parsed.quote_id = "q1"
    parsed.settlement_unit_scale = 1
    config = MagicMock()
    config.blockchain_rpc_url = "http://localhost:8202"
    escrow_spy = MagicMock(
        return_value=({"from": ACCOUNT, "payload": {"provider": PROVIDER}, "nonce": 1, "fee": "1"}, "0xsig")
    )
    return (
        patch.object(market_gpu, "get_config", return_value=config),
        patch.object(market_gpu, "parse_quote", return_value=parsed),
        patch("aitbc_cli.utils.escrow.get_node_wallet", return_value=NODE_WALLET),
        patch.object(market_gpu, "create_signed_escrow_lock", escrow_spy),
        prober_patch,
        escrow_spy,
        market_gpu,
    )


def _call_buy_native(market_gpu):
    market_gpu._buy_native(
        _gpu_ctx(),
        buyer_id="b1",
        gpu_id="gpu-1",
        job_id="job-1",
        duration_hours=1,
        quote_dict={},
        buyer_address=ACCOUNT,
        private_key="0xprivate",
        max_ait=None,
        yes=True,
        json_output=False,
        breakdown={"buyer_charge_units": 5},
    )


def test_gpu_buy_native_aborts_when_chain_probe_fails():
    *patches, escrow_spy, market_gpu = _gpu_patches(_failing_probe())
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with pytest.raises(CLIError):
            _call_buy_native(market_gpu)
    escrow_spy.assert_not_called()


def test_gpu_buy_native_env_chain_id_wins(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    *patches, escrow_spy, market_gpu = _gpu_patches(_failing_probe())
    prober_cls = patches[4]
    coord = MagicMock()
    coord.post.return_value = {"success": True}
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        prober_cls as prober,
        patch.object(market_gpu, "AITBCHTTPClient", return_value=coord),
    ):
        _call_buy_native(market_gpu)
    prober.assert_not_called()
    assert escrow_spy.call_args.kwargs["chain_id"] == "env-chain"


# --- node island join --------------------------------------------------------


def _island_ctx():
    ctx = MagicMock()
    ctx.obj = {"output_format": "table"}
    return ctx


def _join(**kw):
    from aitbc_cli.commands.node.island import join_island_command

    return join_island_command(
        _island_ctx(),
        island_id="isl-1",
        island_name="isl",
        chain_id=None,
        hub="hub",
        is_hub=False,
        rpc_url="http://hub-rpc:8202",
        **kw,
    )


def _keystore_patches():
    import builtins
    import json as _json

    keystore_json = _json.dumps({"k1": {"public_key_pem": "PUB"}})
    m_open = mock_open(read_data=keystore_json)
    return (
        patch("aitbc_cli.commands.node.island.os.path.exists", return_value=True),
        patch.object(builtins, "open", m_open),
        patch("aitbc_cli.commands.node.island.shutil.chown"),
        patch("aitbc_cli.commands.node.island.os.chmod"),
    )


def test_island_join_aborts_when_chain_probe_fails():
    coord = MagicMock()
    exists, m_open, _chown, _chmod = _keystore_patches()
    with (
        exists,
        m_open,
        _chown,
        _chmod,
        patch("aitbc_cli.commands.node.island.AITBCHTTPClient", return_value=coord),
        _failing_probe(),
        pytest.raises(CLIError),
    ):
        _join()
    coord.post.assert_not_called()


def test_island_join_env_chain_id_wins(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    coord = MagicMock()
    coord.post.return_value = {"success": True, "members": [], "credentials": {}}
    exists, m_open, _chown, _chmod = _keystore_patches()
    with (
        exists,
        m_open,
        _chown,
        _chmod,
        patch("aitbc_cli.commands.node.island.AITBCHTTPClient", return_value=coord),
        _failing_probe() as prober_cls,
    ):
        _join()
    prober_cls.assert_not_called()
    assert coord.post.call_args.kwargs["json"]["chain_id"] == "env-chain"


def test_ai_submit_lookup_failure_names_job_id(runner, ai_patches):
    """A chain-lookup abort after the job was POSTed must name the job id
    and the pay-job recovery hint, not just the lookup error."""
    client, escrow_spy = ai_patches
    with _failing_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert "job-1" in text
    assert "pay-job job-1" in text
    assert "CHAIN_ID" in text
    escrow_spy.assert_not_called()


def test_ai_submit_invalid_amount_omits_chain_hint(runner, ai_patches):
    """A non-chain escrow failure names the job and the pay-job recovery
    path but must not suggest CHAIN_ID."""
    client, escrow_spy = ai_patches
    client.post.side_effect = [
        {
            "job_id": "job-1",
            "state": "QUEUED",
            "payment_amount": "notanumber",
            "payment_token": "AIT",
            "node_wallet_address": NODE_WALLET,
            "provider_address": PROVIDER,
        },
        {"payment_id": "pay-1"},
    ]
    with _ok_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert "Invalid payment amount" in text
    assert "job-1" in text
    assert "pay-job job-1" in text
    assert "CHAIN_ID" not in text


def test_ai_submit_nonce_failure_omits_chain_hint(runner, ai_patches):
    """A nonce-lookup failure inside escrow signing names the job and the
    pay-job recovery path but must not suggest CHAIN_ID."""
    client, escrow_spy = ai_patches
    escrow_spy.side_effect = CLIError("nonce lookup failed for 0xabc")
    with _ok_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    text = result.output + str(result.exception)
    assert "nonce lookup failed" in text
    assert "job-1" in text
    assert "pay-job job-1" in text
    assert "CHAIN_ID" not in text
