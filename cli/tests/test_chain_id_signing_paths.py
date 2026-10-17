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
        patch("aitbc_cli.commands.ai.get_buyer_nonce", return_value=7),
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


def test_ai_submit_chain_probe_failure_posts_no_job(runner, ai_patches):
    """A chain-probe failure now aborts during pre-flight — before
    ``POST /v1/jobs`` — so the coordinator never holds an accepted but
    unfunded job."""
    client, escrow_spy = ai_patches
    with _failing_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    assert "chain" in (result.output + str(result.exception)).lower()
    client.post.assert_not_called()
    escrow_spy.assert_not_called()


def test_ai_submit_nonce_probe_failure_posts_no_job(runner, ai_patches):
    """A missing/unreachable buyer account likewise aborts pre-flight; no
    unfunded job row is left for the operator to discover later."""
    client, escrow_spy = ai_patches
    with _ok_probe(), patch("aitbc_cli.commands.ai.get_buyer_nonce", side_effect=CLIError("nonce lookup failed")):
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code != 0
    client.post.assert_not_called()
    escrow_spy.assert_not_called()


def test_ai_submit_unpaid_skips_chain_preflight(runner, ai_patches):
    """Deliberately-unpaid submits must not depend on the chain RPC at all —
    no chain-id probe, no nonce lookup."""
    client, escrow_spy = ai_patches
    client.post.side_effect = None
    client.post.return_value = {"job_id": "job-2", "state": "QUEUED"}
    with _failing_probe() as prober_cls, patch("aitbc_cli.commands.ai.get_buyer_nonce") as nonce_spy:
        result = _invoke_ai(runner, ["submit", "--prompt", "hi", "--wallet", "w"])
    assert result.exit_code == 0, result.output
    prober_cls.assert_not_called()
    nonce_spy.assert_not_called()
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
    assert "pay --job-id job-1" in text
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
    assert "pay --job-id job-1" in text
    assert "CHAIN_ID" not in text


def test_ai_submit_escrow_lock_uses_wallet_buyer(runner, ai_patches):
    """Without --buyer-address the escrow lock must sign for the --wallet
    address — the same buyer the job POST carries — not the literal
    string 'none' (which produced /rpc/account/none lookups live)."""
    from aitbc_cli.utils.address import to_canonical

    client, escrow_spy = ai_patches
    with _ok_probe():
        result = _invoke_ai(runner, SUBMIT_ARGS)
    assert result.exit_code == 0, result.output
    # create_signed_escrow_lock(ctx, rpc_url, job_id, buyer, provider, ...)
    assert escrow_spy.call_args.args[3] == to_canonical(ACCOUNT)


def test_ai_submit_escrow_lock_prefers_explicit_buyer(runner, ai_patches):
    """An explicit --buyer-address still wins over the wallet fallback."""
    from aitbc_cli.utils.address import to_canonical

    client, escrow_spy = ai_patches
    other = "0x1111111111111111111111111111111111111111"
    with _ok_probe():
        result = _invoke_ai(runner, [*SUBMIT_ARGS, "--buyer-address", other])
    assert result.exit_code == 0, result.output
    assert escrow_spy.call_args.args[3] == to_canonical(other)


# --- escrow address guards (S4) --------------------------------------------


def _escrow_ctx():
    ctx = MagicMock()
    ctx.obj = {"output_format": "table", "api_key": "k"}
    return ctx


def _call_create_escrow(**kw):
    from aitbc_cli.commands.ai import _create_escrow_payment

    args = {
        "ctx": _escrow_ctx(),
        "coord_http_client": MagicMock(),
        "rpc_url": "http://localhost:8202",
        "job_id": "job-1",
        "amount": "5",
        "token": "AIT",
        "buyer_address": ACCOUNT,
        "provider_address": PROVIDER,
        "private_key": "0xprivate",
        "node_wallet": NODE_WALLET,
        "chain_id": "ait-x",
        "offer_id": None,
        "offer_quantity": None,
    }
    args.update(kw)
    _create_escrow_payment(*args.values())


def test_create_escrow_aborts_on_missing_buyer():
    """buyer_address=None must abort locally — never reach /rpc/account/none."""
    with (
        patch("aitbc_cli.commands.ai.resolve_chain_id") as chain_spy,
        patch("aitbc_cli.commands.ai.create_signed_escrow_lock") as escrow_spy,
        pytest.raises(CLIError, match="buyer_address"),
    ):
        _call_create_escrow(buyer_address=None)
    chain_spy.assert_not_called()
    escrow_spy.assert_not_called()


def test_create_escrow_aborts_on_missing_provider():
    with (
        patch("aitbc_cli.commands.ai.resolve_chain_id") as chain_spy,
        patch("aitbc_cli.commands.ai.create_signed_escrow_lock") as escrow_spy,
        pytest.raises(CLIError, match="provider_address"),
    ):
        _call_create_escrow(provider_address=None)
    chain_spy.assert_not_called()
    escrow_spy.assert_not_called()


# --- probe base normalization (CLI-3) -------------------------------------


class TestRpcProbeRoot:
    """``_rpc_probe_root`` strips exactly one trailing ``/rpc`` so the probe
    paths (service-native ``/rpc/proposer``, ``/health``) resolve for both
    bare and ``/rpc``-suffixed bases."""

    def test_rpc_probe_root_strips_suffix(self):
        from aitbc_cli.utils.chain_id import _rpc_probe_root

        assert _rpc_probe_root("https://hub.example/rpc") == "https://hub.example"
        assert _rpc_probe_root("https://hub.example/rpc/") == "https://hub.example"
        assert _rpc_probe_root("http://localhost:8202") == "http://localhost:8202"
        assert _rpc_probe_root("http://localhost:8202/") == "http://localhost:8202"
        # only ONE trailing /rpc segment is stripped
        assert _rpc_probe_root("http://x/rpc/rpc") == "http://x/rpc"
        # non-/rpc suffixes are left alone
        assert _rpc_probe_root("http://x/api") == "http://x/api"

    def test_probed_urls_never_double_rpc(self, monkeypatch):
        from aitbc_cli.utils.chain_id import get_chain_id

        created: list[str] = []
        gets: list[str] = []

        class _Prober:
            def __init__(self, base_url=None, **kw):
                created.append(base_url)

            def get(self, path, **kw):
                gets.append(path)
                if path == "/rpc/proposer":
                    raise RuntimeError("404")
                return {"chain_id": "ait-x"}

        for base in ("http://node:8202", "http://node:8202/rpc", "https://hub.example/rpc"):
            created.clear()
            gets.clear()
            monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", _Prober)
            monkeypatch.delenv("CHAIN_ID", raising=False)
            assert get_chain_id(base, override=None, timeout=5, strict=True) == "ait-x"
            (base_url,) = created
            assert not base_url.endswith("/rpc"), base_url
            assert gets == ["/rpc/proposer", "/health"]
            assert all("/rpc/rpc" not in f"{base_url}{p}" for p in gets)
