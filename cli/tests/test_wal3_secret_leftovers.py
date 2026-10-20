"""WAL-3 tests — the last three secret paths on the WAL-1 standard.

1. ``wallet bridge sell lock`` / ``sell quote`` take the standard
   ``--password*`` trio and forward it through ``_resolve_wallet`` into
   ``_load_wallet``'s lazy resolution — an agent on a headless host can sign
   the sell-lock TRANSFER with ``--password-file``/``--password-stdin``.
2. ``staking.py``'s liquidity re-save paths no longer fall back to the old
   private-TTY ``_get_wallet_password`` — the resolved secret is reused, and
   a headless host with no source fails closed before any submit.
3. ``genesis init`` hands the password to ``unified_genesis.py`` through the
   child environment (``AITBC_GENESIS_PASSWORD``), never argv; ``genesis
   reset`` resolves the flag trio instead of a bare ``--password`` option.

Everything runs against REAL encrypted wallets written by ``_save_wallet``
and the REAL resolvers — only the hub HTTP client, the chain RPC client,
``_submit_liquidity_transaction`` and ``subprocess.run`` are faked.
Throwaway in-process keys and passwords per the WAL-3 prompt.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc_cli.commands import genesis as genesis_module
from aitbc_cli.commands.wallet import _save_wallet
from aitbc_cli.commands.wallet import bridge as bridge_module
from aitbc_cli.commands.wallet import staking as staking_module

PASSWORD = "wal3-test-pass-9"
ESCROW = "0x40c7181b639A2642294A802b1CD60C7a0d531a07"
TX_HASH = "0x" + "ab" * 32


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def enc_wallet(tmp_path, monkeypatch):
    """A REAL encrypted file wallet via ``_save_wallet`` (PBKDF2+Fernet).

    Returns (wallet_path, address, plaintext private key hex)."""
    acct = Account.create()
    wdir = tmp_path / "wallets"
    wdir.mkdir()
    wpath = wdir / "encwallet.json"
    _save_wallet(
        wpath,
        {
            "wallet_id": "encwallet",
            "address": acct.address,
            "private_key": acct.key.hex(),
            "balance": "500",
        },
        password=PASSWORD,
    )
    for var in ("AITBC_WALLET_PASSWORD", "AITBC_WALLET_PASSWORD_FILE", "AITBC_WALLET_PASSWORD_ENCWALLET"):
        monkeypatch.delenv(var, raising=False)
    return wpath, acct.address, acct.key.hex()


@pytest.fixture
def pw_file(tmp_path):
    """A real 0600 password file (``_read_password_file`` enforces it)."""
    f = tmp_path / "pw.txt"
    f.write_text(PASSWORD + "\n")
    f.chmod(0o600)
    return f


def _wallet_obj(enc_wallet):
    wpath, _addr, _key = enc_wallet
    return {
        "wallet_name": "encwallet",
        "wallet_dir": wpath.parent,
        "wallet_path": wpath,
        "wallet_sign_path": wpath,
        "output_format": "json",
    }


# ---------------------------------------------------------------------------
# 1. wallet bridge sell quote / sell lock
# ---------------------------------------------------------------------------


class _FakeClient:
    """Fake AITBCHTTPClient — records calls, serves per-substring canned GETs
    and a canned POST body. Both the hub client and the chain-RPC client in
    ``sell_lock`` are this class; ``instances`` tells them apart."""

    instances: list = []
    get_responses: dict[str, Any] = {}
    post_response: Any = {}

    def __init__(self, base_url=None, timeout=None, **kw):
        self.base_url = base_url
        self.gets: list = []
        self.posts: list = []
        _FakeClient.instances.append(self)

    def get(self, path, params=None, **kw):
        self.gets.append(path)
        for key, resp in _FakeClient.get_responses.items():
            if key in path:
                if isinstance(resp, BaseException):
                    raise resp
                return resp
        return {}

    def post(self, path, json=None, **kw):
        self.posts.append({"path": path, "json": json})
        if isinstance(_FakeClient.post_response, BaseException):
            raise _FakeClient.post_response
        return _FakeClient.post_response


@pytest.fixture
def fake_http(monkeypatch):
    """Patch the sell lane's HTTP + chain-id resolution; no network."""
    _FakeClient.instances = []
    _FakeClient.get_responses = {
        "/v1/bridge/sell/status/": {
            "kind": "quote",
            "status": "quoted",
            "escrow_address": ESCROW,
            "ait_amount": "10",
        },
        "/rpc/account/": {"nonce": 0},
    }
    _FakeClient.post_response = {"transaction_hash": TX_HASH}
    monkeypatch.setattr(bridge_module, "AITBCHTTPClient", _FakeClient)
    monkeypatch.setattr(bridge_module, "resolve_chain_id", lambda ctx, rpc_url, **kw: "ait-test")
    return _FakeClient


def _broadcasts() -> list:
    """The /rpc/transaction POSTs across all fake clients — the only place a
    signed lock can leave the node."""
    return [p for inst in _FakeClient.instances for p in inst.posts if p["path"] == "/rpc/transaction"]


class TestSellLockPasswords:
    """``sell lock`` signs with the node wallet — the trio must reach the
    lazy resolver inside ``_load_wallet`` (resolved once, reused verbatim)."""

    def test_password_file_signs_and_broadcasts(self, runner, enc_wallet, pw_file, fake_http):
        result = runner.invoke(
            bridge_module.sell_lock,
            ["--quote-id", "sellq_1", "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert len(_broadcasts()) == 1
        body = _broadcasts()[0]["json"]
        assert body["to"] == ESCROW
        assert body["payload"]["sell_quote"] == "sellq_1"
        assert PASSWORD not in result.output

    def test_wrong_password_fails_closed(self, runner, enc_wallet, tmp_path, fake_http):
        bad = tmp_path / "bad.txt"
        bad.write_text("wrong-pass\n")
        bad.chmod(0o600)
        result = runner.invoke(
            bridge_module.sell_lock,
            ["--quote-id", "sellq_1", "--password-file", str(bad)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code != 0
        assert "Invalid password" in result.output
        assert not _broadcasts()

    def test_no_password_fails_closed(self, runner, enc_wallet, fake_http):
        """Encrypted wallet, no source, no TTY — fail closed, nothing sent."""
        result = runner.invoke(bridge_module.sell_lock, ["--quote-id", "sellq_1"], obj=_wallet_obj(enc_wallet))
        assert result.exit_code != 0
        assert "No wallet password available" in result.output
        assert not _broadcasts()

    def test_password_stdin_read_exactly_once(self, runner, enc_wallet, fake_http):
        """One line on stdin signs the lock. A second readline would return ''
        and abort — success proves the resolution ran exactly once."""
        result = runner.invoke(
            bridge_module.sell_lock,
            ["--quote-id", "sellq_1", "--password-stdin"],
            input=PASSWORD + "\n",
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert len(_broadcasts()) == 1
        assert PASSWORD not in result.output

    def test_secret_never_in_output_or_logs(self, runner, enc_wallet, pw_file, fake_http, caplog):
        result = runner.invoke(
            bridge_module.sell_lock,
            ["--quote-id", "sellq_1", "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert PASSWORD not in result.output
        assert PASSWORD not in caplog.text


class TestSellQuotePasswords:
    """``sell quote`` only needs the address, but it still loads the wallet
    file — an encrypted wallet triggers the same lazy resolution, so it gets
    the same trio."""

    def test_password_file_unlocks_for_quote(self, runner, enc_wallet, pw_file, fake_http):
        _FakeClient.post_response = {
            "quote_id": "sellq_9",
            "rate": "0.001",
            "eth_amount": "0.01",
            "expires_at": "2026-10-15T16:00:00",
            "escrow_address": ESCROW,
        }
        result = runner.invoke(
            bridge_module.sell_quote,
            ["--amount", "10", "--eth-address", ESCROW, "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert "sellq_9" in result.output
        assert PASSWORD not in result.output

    def test_encrypted_wallet_no_password_fails_closed(self, runner, enc_wallet, fake_http):
        result = runner.invoke(
            bridge_module.sell_quote,
            ["--amount", "10", "--eth-address", ESCROW],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code != 0
        assert "No wallet password available" in result.output


# ---------------------------------------------------------------------------
# 2. staking liquidity re-save — no _get_wallet_password fallback remains
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_submit(monkeypatch):
    """``_submit_liquidity_transaction`` is the only network hop; fake it."""
    calls: list = []

    def fake(ctx, wallet_data, tx):
        calls.append({"wallet_data": wallet_data, "tx": tx})
        return TX_HASH

    monkeypatch.setattr(staking_module, "_submit_liquidity_transaction", fake)
    return calls


def _no_prompt(monkeypatch):
    """Any getpass attempt explodes — proves nothing prompts headless."""
    import getpass

    def boom(prompt=""):
        raise AssertionError("getpass was called — a prompt fired on a headless run")

    monkeypatch.setattr(getpass, "getpass", boom)


class TestLiquidityStakePasswords:
    """The re-save after a liquidity tx must reuse the already-resolved
    password — never a second private prompt helper."""

    def test_encrypted_wallet_password_file_resaves_encrypted(self, runner, enc_wallet, pw_file, mock_submit, monkeypatch):
        _no_prompt(monkeypatch)
        wpath, addr, plain_key = enc_wallet
        result = runner.invoke(
            staking_module.liquidity_stake,
            ["--amount", "1", "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert len(mock_submit) == 1
        # The wallet file was re-saved under the resolved password — the key
        # still decrypts to the same material and the blob is still encrypted.
        saved = json.loads(Path(wpath).read_text())
        assert saved.get("encrypted") is True
        assert saved["private_key"] != plain_key  # never stored plaintext
        from aitbc_cli.commands.wallet import decrypt_value

        assert decrypt_value(saved["private_key"], PASSWORD).lstrip("0x") == plain_key.lstrip("0x")
        assert PASSWORD not in result.output

    def test_no_password_fails_closed_before_submit(self, runner, enc_wallet, mock_submit, monkeypatch):
        _no_prompt(monkeypatch)
        result = runner.invoke(
            staking_module.liquidity_stake,
            ["--amount", "1"],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code != 0
        assert "No wallet password available" in result.output
        assert not mock_submit

    def test_password_stdin_signs_unstake(self, runner, enc_wallet, mock_submit, monkeypatch):
        """liquidity-unstake exercises the second ex-call-site (line ~707)."""
        _no_prompt(monkeypatch)
        wpath, addr, _key = enc_wallet
        saved = json.loads(Path(wpath).read_text())
        saved["liquidity"] = [{"stake_id": "lstake-1", "status": "active", "amount": "1"}]
        Path(wpath).write_text(json.dumps(saved))
        result = runner.invoke(
            staking_module.liquidity_unstake,
            ["--stake-id", "lstake-1", "--password-stdin"],
            input=PASSWORD + "\n",
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert len(mock_submit) == 1


# ---------------------------------------------------------------------------
# 3. genesis init / reset — the secret travels by child env, never argv
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_genesis_run(monkeypatch):
    """Capture subprocess.run's argv/env instead of spawning the generator."""
    calls: list = []

    def fake_run(cmd, **kw):
        calls.append({"cmd": cmd, "env": kw.get("env")})

        class _R:
            stdout = "genesis ok"
            stderr = ""

        return _R()

    monkeypatch.setattr(genesis_module.subprocess, "run", fake_run)
    return calls


class TestGenesisInitPassword:
    # GAP-GENESIS-INIT-1: init is retired and refuses before spawning the
    # generator — no password flag can reach a child process at all, which
    # is strictly stronger than the env-not-argv contract this class used
    # to pin.

    def test_password_file_never_reaches_a_child(self, runner, mock_genesis_run, pw_file):
        result = runner.invoke(
            genesis_module.init,
            ["--chain-id", "ait-test", "--create-wallet", "--password-file", str(pw_file)],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1
        assert "build-genesis.py" in result.output
        assert mock_genesis_run == []
        assert PASSWORD not in result.output

    def test_deprecated_password_flag_refused_before_any_spawn(self, runner, mock_genesis_run):
        result = runner.invoke(
            genesis_module.init,
            ["--chain-id", "ait-test", "--create-wallet", "--password", PASSWORD],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1
        assert "build-genesis.py" in result.output
        assert mock_genesis_run == []
        assert PASSWORD not in result.output

    def test_no_flag_still_refuses(self, runner, mock_genesis_run):
        result = runner.invoke(
            genesis_module.init,
            ["--chain-id", "ait-test", "--create-wallet"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1
        assert "build-genesis.py" in result.output
        assert mock_genesis_run == []

    def test_password_stdin_refused_without_reading(self, runner, mock_genesis_run):
        result = runner.invoke(
            genesis_module.init,
            ["--chain-id", "ait-test", "--create-wallet", "--password-stdin"],
            input=PASSWORD + "\n",
            obj={"output_format": "json"},
        )
        assert result.exit_code == 1
        assert "build-genesis.py" in result.output
        assert mock_genesis_run == []
        assert PASSWORD not in result.output


class TestGenesisResetPassword:
    @pytest.fixture
    def mock_reset(self, monkeypatch):
        calls: list = []

        def fake_reset(**kw):
            calls.append(kw)
            return {"ok": True}

        monkeypatch.setattr(genesis_module.genesis_reset, "reset_genesis", fake_reset)
        return calls

    def test_password_file_reaches_reset_genesis(self, runner, mock_reset, pw_file):
        result = runner.invoke(
            genesis_module.reset,
            ["--chain-id", "ait-test", "--new-wallet", "--yes", "--password-file", str(pw_file)],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert mock_reset[0]["password"] == PASSWORD
        assert PASSWORD not in result.output

    def test_no_flag_keeps_auto_generate(self, runner, mock_reset):
        result = runner.invoke(
            genesis_module.reset,
            ["--chain-id", "ait-test", "--new-wallet", "--yes"],
            obj={"output_format": "json"},
        )
        assert result.exit_code == 0, result.output
        assert mock_reset[0]["password"] is None


# ---------------------------------------------------------------------------
# 4. unified_genesis.py — the env var is honoured script-side
# ---------------------------------------------------------------------------


class _Sentinel(Exception):
    pass


def _import_unified_genesis():
    scripts_dir = Path(__file__).resolve().parents[2] / "apps/blockchain-node/scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import unified_genesis

        return unified_genesis
    finally:
        sys.path.pop()


class TestUnifiedGenesisEnv:
    def test_env_password_reaches_create_wallet(self, monkeypatch):
        """AITBC_GENESIS_PASSWORD feeds create_genesis_wallet when no
        --password argv is given — the boundary the CLI now relies on."""
        ug = _import_unified_genesis()
        got: dict = {}

        def fake_create(password, chain_id):
            got["password"] = password
            raise _Sentinel  # stop main() before any real file/db writes

        monkeypatch.setattr(ug, "create_genesis_wallet", fake_create)
        monkeypatch.setenv("AITBC_GENESIS_PASSWORD", PASSWORD)
        monkeypatch.setattr(sys, "argv", ["unified_genesis.py", "--chain-id", "ait-test", "--create-wallet"])
        with pytest.raises(_Sentinel):
            ug.main()
        assert got["password"] == PASSWORD

    def test_argv_password_still_wins_for_direct_use(self, monkeypatch):
        """Direct script invocation keeps its own --password flag."""
        ug = _import_unified_genesis()
        got: dict = {}

        def fake_create(password, chain_id):
            got["password"] = password
            raise _Sentinel

        monkeypatch.setattr(ug, "create_genesis_wallet", fake_create)
        monkeypatch.setenv("AITBC_GENESIS_PASSWORD", "env-pass")
        monkeypatch.setattr(
            sys, "argv", ["unified_genesis.py", "--chain-id", "ait-test", "--create-wallet", "--password", "argv-pass"]
        )
        with pytest.raises(_Sentinel):
            ug.main()
        assert got["password"] == "argv-pass"


# ---------------------------------------------------------------------------
# CLI-7: sell subcommand names + http_error_detail on non-2xx responses
# ---------------------------------------------------------------------------


class _FakeHTTPError(Exception):
    """HTTP-looking error: ``.response.json()`` returns the FastAPI body."""

    def __init__(self, detail: str) -> None:
        super().__init__("500 Server Error")
        self.response = _FakeHTTPError._Resp(detail)

    class _Resp:
        def __init__(self, detail: str) -> None:
            self._detail = detail

        def json(self):
            return {"detail": self._detail}


def _http_err(detail: str) -> _FakeHTTPError:
    return _FakeHTTPError(detail)


class TestSellCommandNames:
    """Click derived ``sell-quote``/``sell-lock``/``sell-status`` from the
    function names while every epilog and printed ``next`` hint said
    ``sell quote`` — the registered names are pinned to the short forms."""

    def test_sell_group_lists_short_names(self, runner):
        result = runner.invoke(bridge_module.sell, ["--help"])
        assert result.exit_code == 0, result.output
        for name in ("quote", "lock", "status"):
            assert re.search(rf"(?m)^\s+{name}\b", result.output), result.output
        for bad in ("sell-quote", "sell-lock", "sell-status"):
            assert bad not in result.output

    def test_next_hints_use_short_names(self, runner, enc_wallet, pw_file, fake_http):
        """The printed 'next' hint must name a command that actually exists."""
        _FakeClient.post_response = {
            "quote_id": "sellq_9",
            "rate": "0.001",
            "eth_amount": "0.01",
            "expires_at": "2026-10-15T16:00:00",
            "escrow_address": ESCROW,
        }
        result = runner.invoke(
            bridge_module.sell_quote,
            ["--amount", "10", "--eth-address", ESCROW, "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code == 0, result.output
        assert "sell lock --quote-id" in result.output
        assert "sell-lock" not in result.output


class TestSellErrorDetail:
    """Row 64: a non-2xx sell response must surface the JSON ``detail``,
    not collapse to the bare exception text."""

    def test_quote_error_keeps_detail(self, runner, enc_wallet, pw_file, fake_http):
        _FakeClient.post_response = _http_err("escrow at capacity")
        result = runner.invoke(
            bridge_module.sell_quote,
            ["--amount", "10", "--eth-address", ESCROW, "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code != 0
        assert "escrow at capacity" in result.output
        assert "500 Server Error" not in result.output

    def test_lock_fetch_quote_error_keeps_detail(self, runner, enc_wallet, pw_file, fake_http):
        _FakeClient.get_responses["/v1/bridge/sell/status/"] = _http_err("sell quote expired")
        result = runner.invoke(
            bridge_module.sell_lock,
            ["--quote-id", "sellq_1", "--password-file", str(pw_file)],
            obj=_wallet_obj(enc_wallet),
        )
        assert result.exit_code != 0
        assert "sell quote expired" in result.output
        assert "500 Server Error" not in result.output
        assert not _broadcasts()

    def test_status_error_keeps_detail(self, runner, fake_http):
        _FakeClient.get_responses["/v1/bridge/sell/status/"] = _http_err("unknown sell id")
        result = runner.invoke(bridge_module.sell_status, ["--id", "sellq_1"], obj={"output_format": "json"})
        assert result.exit_code != 0
        assert "unknown sell id" in result.output
        assert "500 Server Error" not in result.output
