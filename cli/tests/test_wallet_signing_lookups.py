"""Wallet signing paths must abort loudly when the chain-id or nonce lookup fails.

Regression tests for the 2 Oct hub incident: a silent ``ait-localnet``/nonce-0
fallback signed a transaction for a chain nobody serves. The lookup must abort
the command naming the RPC URL and the underlying error; an explicit
``--chain-id`` or ``CHAIN_ID`` still wins over the lookup.
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

import aitbc_cli.utils.chain_id as chain_id_mod
from aitbc_cli.commands.wallet import wallet
from aitbc_cli.commands.wallet import staking as staking_mod


def _write_wallet(tmp_path: Path) -> Path:
    """A plaintext file wallet: real-looking key material, no encryption."""
    wallet_file = tmp_path / "testwallet.json"
    wallet_file.write_text(
        json.dumps(
            {
                "address": "0x08aB1234567890abcdef1234567890abcdef1234",
                "private_key": "0x" + "11" * 32,
                "encrypted": False,
            }
        )
    )
    return wallet_file


def _fake_http_client(get_data=None, get_exc=None, post_data=None):
    """AITBCHTTPClient stand-in recording construction URLs and POST bodies."""

    class _FakeClient:
        instances: list["_FakeClient"] = []

        def __init__(self, base_url: str = "", **kwargs):
            self.base_url = base_url
            self.posts: list[tuple[str, dict]] = []
            _FakeClient.instances.append(self)

        def get(self, endpoint: str, **kwargs):
            if get_exc is not None:
                raise get_exc
            return get_data or {}

        def post(self, endpoint: str, json=None, **kwargs):
            self.posts.append((endpoint, json))
            return post_data or {"transaction_hash": "0xdeadbeef"}

    _FakeClient.instances = []
    return _FakeClient


def _failing_chain_lookup(rpc_url, override=None, timeout=5, *, strict=False):
    """Group-init resolution yields ""; a strict probe raises like a dead RPC."""
    if override:
        return override
    if strict:
        raise chain_id_mod.ChainIdLookupError(f"{rpc_url}: connection refused")
    return ""


def _serving_chain_lookup(chain_id):
    def _fake(rpc_url, override=None, timeout=5, *, strict=False):
        return override or chain_id

    return _fake


@pytest.fixture
def runner():
    return CliRunner()


SEND_ARGS = ["send", "--to-address", "0x1234567890abcdef1234567890abcdef12345678", "--amount", "1"]


def test_send_aborts_when_chain_id_lookup_fails(runner, tmp_path, monkeypatch):
    """A dead RPC must abort send before signing — never a silent ait-localnet."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 5})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://127.0.0.1:1"],
            obj={},
        )
    assert result.exit_code != 0
    assert "127.0.0.1:1" in result.output
    assert "--rpc-url" in result.output
    assert all(not post for post in [c.posts for c in fake_client.instances])


def test_send_aborts_when_nonce_lookup_fails(runner, tmp_path, monkeypatch):
    """A failed account lookup must abort — never silently sign nonce 0."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_exc=RuntimeError("connection refused"))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://127.0.0.1:2"],
            obj={},
        )
    assert result.exit_code != 0
    assert "127.0.0.1:2" in result.output
    assert "--rpc-url" in result.output
    assert all(not c.posts for c in fake_client.instances)


def test_send_uses_looked_up_chain_and_nonce(runner, tmp_path, monkeypatch):
    """Successful lookups behave exactly as before: sign + submit."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 7})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-testnet")),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://10.0.0.9:8202"],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted, result.output
    tx = submitted[-1]
    assert tx["chain_id"] == "ait-testnet"
    assert tx["nonce"] == 7
    assert tx["signature"]


def test_send_explicit_chain_id_flag_wins_over_failed_lookup(runner, tmp_path, monkeypatch):
    """wallet --chain-id beats a failed probe: signs for the explicit chain."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 3})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), "--chain-id", "explicit-chain", *SEND_ARGS],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted and submitted[-1]["chain_id"] == "explicit-chain"


def test_send_chain_id_env_wins_over_failed_lookup(runner, tmp_path, monkeypatch):
    """CHAIN_ID env supplied by the user beats a failed probe."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 4})
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted and submitted[-1]["chain_id"] == "env-chain"


def _ctx(obj: dict | None = None) -> click.Context:
    ctx = click.Context(click.Command("wallet-test"))
    ctx.obj = obj or {}
    return ctx


def test_staking_get_chain_id_aborts_when_lookup_fails(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup):
        with pytest.raises(click.Abort):
            staking_mod._get_chain_id(_ctx(), "http://127.0.0.1:1")


def test_staking_get_chain_id_reuses_group_resolution(monkeypatch):
    """ctx chain_id is reused only when it was resolved against the submit URL."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    ctx = _ctx({"chain_id": "ait-detected", "chain_id_rpc_url": "http://x"})
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup):
        assert staking_mod._get_chain_id(ctx, "http://x") == "ait-detected"


def test_staking_get_chain_id_probes_submit_url_when_ctx_url_differs(monkeypatch):
    """A chain id detected from another node is not trusted for this submit."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    ctx = _ctx({"chain_id": "ait-detected", "chain_id_rpc_url": "http://other"})
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")):
        assert staking_mod._get_chain_id(ctx, "http://x") == "ait-probed"
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup):
        with pytest.raises(click.Abort):
            staking_mod._get_chain_id(ctx, "http://x")


def test_staking_get_chain_id_probes_when_ctx_has_no_recorded_url(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    ctx = _ctx({"chain_id": "ait-detected"})
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")):
        assert staking_mod._get_chain_id(ctx, "http://x") == "ait-probed"


def test_staking_get_chain_id_explicit_wins(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    ctx = _ctx({"chain_id": "ait-detected", "chain_id_explicit": "ait-flag"})
    assert staking_mod._get_chain_id(ctx, "http://x") == "ait-flag"


def test_staking_get_chain_id_env_wins(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-env")
    assert staking_mod._get_chain_id(_ctx(), "http://x") == "ait-env"


def test_staking_get_chain_id_strict_probe_success(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")):
        assert staking_mod._get_chain_id(_ctx(), "http://node:8202") == "ait-probed"


def test_get_account_nonce_aborts_on_lookup_failure():
    client = MagicMock()
    client.base_url = "http://127.0.0.1:1"
    client.get.side_effect = RuntimeError("connection refused")
    with pytest.raises(click.Abort):
        staking_mod._get_account_nonce(client, "0xabc", "ait-test")


def test_get_account_nonce_returns_nonce_on_success():
    client = MagicMock()
    client.base_url = "http://node:8202"
    client.get.return_value = {"nonce": 9}
    assert staking_mod._get_account_nonce(client, "0xabc", "ait-test") == 9


def test_get_account_nonce_aborts_when_response_has_no_nonce():
    """A 200 response without an integer nonce is a failed lookup, not 0."""
    client = MagicMock()
    client.base_url = "http://node:8202"
    client.get.return_value = {}
    with pytest.raises(click.Abort):
        staking_mod._get_account_nonce(client, "0xabc", "ait-test")


def test_send_aborts_when_account_response_has_no_nonce(runner, tmp_path, monkeypatch):
    """wallet send: a nonce-less account response aborts before signing."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://127.0.0.1:3"],
            obj={},
        )
    assert result.exit_code != 0
    assert all(not c.posts for c in fake_client.instances)


# ---------------------------------------------------------------------------
# transactions send (_resolve_nonce feeds the signing path)
# ---------------------------------------------------------------------------


def _write_tx_wallet(tmp_path: Path) -> Path:
    """Plaintext keystore dir for ``transactions send`` (filename = wallet name)."""
    (tmp_path / "w1.json").write_text(
        json.dumps(
            {
                "address": "0x08aB1234567890abcdef1234567890abcdef1234",
                "private_key": "0x" + "11" * 32,
                "encrypted": False,
            }
        )
    )
    return tmp_path


def test_tx_resolve_nonce_aborts_on_lookup_failure(monkeypatch):
    from aitbc_cli.commands import transactions as tx_mod
    from aitbc_cli.utils.error_handling import CLIError

    fake_client = _fake_http_client(get_exc=RuntimeError("connection refused"))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client):
        with pytest.raises(CLIError):
            tx_mod._resolve_nonce("http://127.0.0.1:9", "0xabc")


def test_tx_resolve_nonce_aborts_when_response_has_no_nonce(monkeypatch):
    from aitbc_cli.commands import transactions as tx_mod
    from aitbc_cli.utils.error_handling import CLIError

    fake_client = _fake_http_client(get_data={})
    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client):
        with pytest.raises(CLIError):
            tx_mod._resolve_nonce("http://127.0.0.1:9", "0xabc")


def test_tx_resolve_nonce_returns_nonce_on_success(monkeypatch):
    from aitbc_cli.commands import transactions as tx_mod

    fake_client = _fake_http_client(get_data={"nonce": 12})
    with patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client):
        assert tx_mod._resolve_nonce("http://node:8202", "0xabc") == 12


def test_tx_send_impl_aborts_when_nonce_lookup_fails(tmp_path, monkeypatch):
    """_send_transaction_impl: failed nonce lookup aborts before signing."""
    from aitbc_cli.commands import transactions as tx_mod
    from aitbc_cli.utils.error_handling import CLIError

    keystore_dir = _write_tx_wallet(tmp_path)
    fake_client = _fake_http_client(get_exc=RuntimeError("connection refused"))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client),
    ):
        with pytest.raises(CLIError):
            tx_mod._send_transaction_impl(
                "w1",
                "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
                Decimal("1"),
                Decimal("0.001"),
                "x",
                keystore_dir=keystore_dir,
                rpc_url="http://127.0.0.1:9",
            )
    assert all(not c.posts for c in fake_client.instances)


def test_tx_send_impl_aborts_when_chain_lookup_fails(tmp_path, monkeypatch):
    """_send_transaction_impl: failed chain-id lookup aborts before signing."""
    from aitbc_cli.commands import transactions as tx_mod
    from aitbc_cli.utils.error_handling import CLIError

    keystore_dir = _write_tx_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 4})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client),
    ):
        with pytest.raises(CLIError):
            tx_mod._send_transaction_impl(
                "w1",
                "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
                Decimal("1"),
                Decimal("0.001"),
                "x",
                keystore_dir=keystore_dir,
                rpc_url="http://127.0.0.1:9",
            )
    assert all(not c.posts for c in fake_client.instances)


def test_tx_send_impl_signs_with_looked_up_values_on_success(tmp_path, monkeypatch):
    """Success path unchanged: probed chain id + account nonce are signed."""
    from aitbc_cli.commands import transactions as tx_mod

    keystore_dir = _write_tx_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 9}, post_data={"transaction_hash": "0xfeed"})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", fake_client),
    ):
        tx_hash = tx_mod._send_transaction_impl(
            "w1",
            "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B",
            Decimal("1"),
            Decimal("0.001"),
            "x",
            keystore_dir=keystore_dir,
            rpc_url="http://node:8202",
        )
    assert tx_hash == "0xfeed"
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted
    tx = submitted[-1]
    assert tx["chain_id"] == "ait-probed"
    assert tx["nonce"] == 9
    assert tx["signature"]


# ---------------------------------------------------------------------------
# escrow signing helpers (aitbc ai / market run / gpu rental)
# ---------------------------------------------------------------------------


def test_escrow_get_buyer_nonce_aborts_on_lookup_failure(monkeypatch):
    from aitbc_cli.utils import escrow as escrow_mod
    from aitbc_cli.utils.error_handling import CLIError

    fake_client = _fake_http_client(get_exc=RuntimeError("connection refused"))
    with patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client):
        with pytest.raises(CLIError):
            escrow_mod.get_buyer_nonce(_ctx(), "http://127.0.0.1:9", "0xabc")


def test_escrow_get_buyer_nonce_aborts_when_response_has_no_nonce(monkeypatch):
    from aitbc_cli.utils import escrow as escrow_mod
    from aitbc_cli.utils.error_handling import CLIError

    fake_client = _fake_http_client(get_data={})
    with patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client):
        with pytest.raises(CLIError):
            escrow_mod.get_buyer_nonce(_ctx(), "http://127.0.0.1:9", "0xabc")


def test_escrow_get_buyer_nonce_returns_nonce_on_success(monkeypatch):
    from aitbc_cli.utils import escrow as escrow_mod

    fake_client = _fake_http_client(get_data={"nonce": 8})
    with patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client):
        assert escrow_mod.get_buyer_nonce(_ctx(), "http://node:8202", "0xabc") == 8


ESCROW_ADDR = "0x08aB1234567890abcdef1234567890abcdef1234"


def _escrow_kwargs(**extra):
    base = {
        "job_id": "job-1",
        "buyer": ESCROW_ADDR,
        "provider": "0x1234567890abcdef1234567890abcdef12345678",
        "node_wallet": "0x9999999999999999999999999999999999999999",
        "amount_ait": Decimal("1"),
        "private_key": "0x" + "11" * 32,
    }
    base.update(extra)
    return base


def test_escrow_lock_aborts_when_chain_lookup_fails(monkeypatch):
    """create_signed_escrow_lock: no chain_id arg and a dead RPC aborts — no sign."""
    from aitbc_cli.utils import escrow as escrow_mod
    from aitbc_cli.utils.error_handling import CLIError

    fake_client = _fake_http_client(get_data={"nonce": 2})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client),
        patch("aitbc_cli.utils.escrow.sign_escrow_lock_tx", return_value="SIG") as mock_sign,
    ):
        with pytest.raises(CLIError):
            escrow_mod.create_signed_escrow_lock(_ctx(), "http://127.0.0.1:9", **_escrow_kwargs())
    mock_sign.assert_not_called()


def test_escrow_lock_probes_rpc_for_chain_id_on_success(monkeypatch):
    """No explicit chain_id: the submit RPC is probed and its chain id signed."""
    from aitbc_cli.utils import escrow as escrow_mod

    fake_client = _fake_http_client(get_data={"nonce": 2})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")),
        patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client),
        patch("aitbc_cli.utils.escrow.sign_escrow_lock_tx", return_value="SIG") as mock_sign,
    ):
        lock_tx, sig = escrow_mod.create_signed_escrow_lock(_ctx(), "http://node:8202", **_escrow_kwargs())
    assert sig == "SIG"
    assert lock_tx["chain_id"] == "ait-probed"
    assert lock_tx["nonce"] == 2
    mock_sign.assert_called_once()


def test_escrow_lock_explicit_chain_id_wins(monkeypatch):
    """An explicit chain_id argument beats the probe entirely."""
    from aitbc_cli.utils import escrow as escrow_mod

    fake_client = _fake_http_client(get_data={"nonce": 2})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client),
        patch("aitbc_cli.utils.escrow.sign_escrow_lock_tx", return_value="SIG"),
    ):
        lock_tx, _ = escrow_mod.create_signed_escrow_lock(
            _ctx(), "http://node:8202", **_escrow_kwargs(chain_id="explicit-chain")
        )
    assert lock_tx["chain_id"] == "explicit-chain"


def test_escrow_lock_env_chain_id_wins(monkeypatch):
    from aitbc_cli.utils import escrow as escrow_mod

    fake_client = _fake_http_client(get_data={"nonce": 2})
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.utils.escrow.AITBCHTTPClient", fake_client),
        patch("aitbc_cli.utils.escrow.sign_escrow_lock_tx", return_value="SIG"),
    ):
        lock_tx, _ = escrow_mod.create_signed_escrow_lock(_ctx(), "http://node:8202", **_escrow_kwargs())
    assert lock_tx["chain_id"] == "env-chain"


def test_build_escrow_lock_tx_aborts_without_chain_id():
    from aitbc_cli.utils import escrow as escrow_mod
    from aitbc_cli.utils.error_handling import CLIError

    with pytest.raises(CLIError):
        escrow_mod.build_escrow_lock_tx(
            _ctx(),
            "job-1",
            ESCROW_ADDR,
            "0x1234567890abcdef1234567890abcdef12345678",
            "0x9999999999999999999999999999999999999999",
            Decimal("1"),
            0,
            chain_id=None,
        )


# ---------------------------------------------------------------------------
# market signing helpers (offers / jobs nonce chain)
# ---------------------------------------------------------------------------


def _market_config(rpc_url="http://localx:8202", hub="hubx"):
    from types import SimpleNamespace

    return SimpleNamespace(blockchain_rpc_url=rpc_url, hub_discovery_url=hub)


def _per_url_client(behavior_by_url):
    """AITBCHTTPClient stand-in whose get() depends on the instance base_url."""

    class _C:
        instances: list["_C"] = []

        def __init__(self, base_url: str = "", **kwargs):
            self.base_url = base_url
            _C.instances.append(self)

        def get(self, endpoint: str, **kwargs):
            behavior = behavior_by_url.get(self.base_url)
            if isinstance(behavior, Exception):
                raise behavior
            return behavior or {}

    _C.instances = []
    return _C


def test_market_get_account_nonce_aborts_when_all_urls_fail(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    client = _per_url_client({"http://localx:8202": RuntimeError("refused"), "https://hubx": RuntimeError("refused")})
    with (
        patch("aitbc_cli.commands.market.get_config", return_value=_market_config()),
        patch("aitbc.network.AITBCHTTPClient", client),
    ):
        with pytest.raises(click.Abort):
            market_mod.get_account_nonce("0xabc", "ait-test")


def test_market_get_account_nonce_aborts_when_no_nonce_anywhere(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    client = _per_url_client({"http://localx:8202": {}, "https://hubx": {}})
    with (
        patch("aitbc_cli.commands.market.get_config", return_value=_market_config()),
        patch("aitbc.network.AITBCHTTPClient", client),
    ):
        with pytest.raises(click.Abort):
            market_mod.get_account_nonce("0xabc", "ait-test")


def test_market_get_account_nonce_falls_back_to_hub_and_returns(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    client = _per_url_client({"http://localx:8202": RuntimeError("refused"), "https://hubx": {"nonce": 6}})
    with (
        patch("aitbc_cli.commands.market.get_config", return_value=_market_config()),
        patch("aitbc.network.AITBCHTTPClient", client),
    ):
        assert market_mod.get_account_nonce("0xabc", "ait-test") == 6


def test_market_get_account_nonce_first_hit_short_circuits(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    client = _per_url_client({"http://localx:8202": {"nonce": 11}})
    with (
        patch("aitbc_cli.commands.market.get_config", return_value=_market_config()),
        patch("aitbc.network.AITBCHTTPClient", client),
    ):
        assert market_mod.get_account_nonce("0xabc", "ait-test") == 11
    assert len(client.instances) == 1


def test_market_safe_load_credentials_hub_aborts_without_chain_id(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.setenv("NODE_ROLE", "hub")
    with patch("aitbc_cli.commands.market.load_island_credentials", side_effect=FileNotFoundError("nope")):
        with pytest.raises(click.Abort):
            market_mod.safe_load_credentials()


def test_market_safe_load_credentials_hub_uses_env_chain_id(monkeypatch):
    from aitbc_cli.commands import market as market_mod

    monkeypatch.setenv("CHAIN_ID", "ait-env")
    monkeypatch.setenv("NODE_ROLE", "hub")
    with patch("aitbc_cli.commands.market.load_island_credentials", side_effect=FileNotFoundError("nope")):
        creds = market_mod.safe_load_credentials()
    assert creds["chain_id"] == "ait-env"
