"""WAL-1: one wallet-secret input standard for every signing command.

Covers the shared ``resolve_wallet_password`` helper — every source, the
precedence order, source conflicts, file safety checks, and the guarantee
that the secret never reaches stdout/stderr/logs/exceptions — plus one
command-level test per signing family asserting the resolved secret reaches
the signing call (bridge withdraw, transactions send, operations message).
"""

import io
import json
import os
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.wallet_secret import (
    ENV_PASSWORD,
    ENV_PASSWORD_FILE,
    resolve_wallet_password,
)

SECRET = "unittest-secret-3f9c-no-real-wallet"
ALT_SECRET = "unittest-alt-secret-77b1-no-real-wallet"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No password env may leak between tests."""
    for var in (ENV_PASSWORD, ENV_PASSWORD_FILE, "WALLET_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    for var in list(os.environ):
        if var.startswith(f"{ENV_PASSWORD}_"):
            monkeypatch.delenv(var, raising=False)
    # Non-interactive by default: a StringIO has no TTY, so an unresolvable
    # secret must fail rather than hang a CI run on a getpass prompt.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    yield


def _password_file(tmp_path: Path, content: str = SECRET + "\n", mode: int = 0o600, name: str = "wallet.pass") -> Path:
    path = tmp_path / name
    path.write_text(content)
    path.chmod(mode)
    return path


class TestSources:
    def test_stdin_reads_one_line_strips_one_newline(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(SECRET + "\nignored-second-line\n"))
        assert resolve_wallet_password("w", password_stdin=True, interactive_ok=False) == SECRET

    def test_stdin_preserves_inner_whitespace(self, monkeypatch):
        padded = "  spaced secret  "
        monkeypatch.setattr(sys, "stdin", io.StringIO(padded + "\n"))
        assert resolve_wallet_password("w", password_stdin=True, interactive_ok=False) == padded

    def test_stdin_eof_fails(self):
        with pytest.raises(CLIError):
            resolve_wallet_password("w", password_stdin=True, interactive_ok=False)

    def test_password_file(self, tmp_path):
        path = _password_file(tmp_path)
        assert resolve_wallet_password("w", password_file=str(path), interactive_ok=False) == SECRET

    def test_password_file_keeps_whitespace(self, tmp_path):
        path = _password_file(tmp_path, content=" padded \n")
        assert resolve_wallet_password("w", password_file=str(path), interactive_ok=False) == " padded "

    def test_env_password_file(self, tmp_path, monkeypatch):
        path = _password_file(tmp_path)
        monkeypatch.setenv(ENV_PASSWORD_FILE, str(path))
        assert resolve_wallet_password("w", interactive_ok=False) == SECRET

    def test_env_password(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, SECRET)
        assert resolve_wallet_password("w", interactive_ok=False) == SECRET

    def test_per_wallet_env_beats_generic(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, "generic")
        monkeypatch.setenv("AITBC_WALLET_PASSWORD_SHOP", SECRET)
        assert resolve_wallet_password("shop", interactive_ok=False) == SECRET

    def test_legacy_env_name(self, monkeypatch):
        monkeypatch.setenv("WALLET_PASSWORD", SECRET)
        assert resolve_wallet_password("w", legacy_env_names=("WALLET_PASSWORD",), interactive_ok=False) == SECRET

    def test_deprecated_password_flag_warns_but_returns(self, capsys):
        assert resolve_wallet_password("w", password=SECRET, interactive_ok=False) == SECRET
        err = capsys.readouterr().err
        assert "deprecated" in err or "process lists" in err
        assert SECRET not in err

    def test_unencrypted_wallet_needs_no_password(self, tmp_path, monkeypatch):
        wallet = tmp_path / "w.json"
        wallet.write_text(json.dumps({"address": "0x" + "11" * 20, "private_key": "0x" + "11" * 32}))
        assert resolve_wallet_password("w", allow_unencrypted=True, wallet_path=wallet, interactive_ok=False) == ""


class TestPrecedenceAndConflicts:
    def test_stdin_beats_everything(self, tmp_path, monkeypatch):
        # env sources never conflict — the flag source wins by precedence
        _password_file(tmp_path, content=ALT_SECRET + "\n")
        monkeypatch.setenv(ENV_PASSWORD, ALT_SECRET)
        monkeypatch.setenv(ENV_PASSWORD_FILE, str(tmp_path / "wallet.pass"))
        monkeypatch.setattr(sys, "stdin", io.StringIO(SECRET + "\n"))
        assert resolve_wallet_password("w", password_stdin=True, interactive_ok=False) == SECRET

    def test_file_beats_env(self, tmp_path, monkeypatch):
        path = _password_file(tmp_path)
        monkeypatch.setenv(ENV_PASSWORD, ALT_SECRET)
        monkeypatch.setenv(ENV_PASSWORD_FILE, str(tmp_path / "missing.pass"))
        assert resolve_wallet_password("w", password_file=str(path), interactive_ok=False) == SECRET

    def test_env_beats_deprecated_flag(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, ALT_SECRET)
        assert resolve_wallet_password("w", password=SECRET, interactive_ok=False) == ALT_SECRET

    def test_two_flag_sources_fail(self, tmp_path):
        path = _password_file(tmp_path)
        with pytest.raises(CLIError, match="Conflicting password sources"):
            resolve_wallet_password("w", password=SECRET, password_file=str(path), interactive_ok=False)

    def test_stdin_and_file_fail(self, tmp_path):
        path = _password_file(tmp_path)
        with pytest.raises(CLIError, match="Conflicting password sources"):
            resolve_wallet_password("w", password_file=str(path), password_stdin=True, interactive_ok=False)


class TestFileSafety:
    def test_group_readable_refused(self, tmp_path):
        path = _password_file(tmp_path, mode=0o640)
        with pytest.raises(CLIError, match="accessible by group or others"):
            resolve_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_world_readable_refused(self, tmp_path):
        path = _password_file(tmp_path, mode=0o604)
        with pytest.raises(CLIError, match="accessible by group or others"):
            resolve_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_wrong_owner_refused(self, tmp_path, monkeypatch):
        path = _password_file(tmp_path)
        real_euid = os.geteuid()
        monkeypatch.setattr(os, "geteuid", lambda: real_euid + 1)
        with pytest.raises(CLIError, match="not owned by the current user"):
            resolve_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_symlink_to_unsafe_file_refused(self, tmp_path):
        # the check applies to the resolved target, not the link's own mode
        target = _password_file(tmp_path, mode=0o644)
        link = tmp_path / "link.pass"
        link.symlink_to(target)
        with pytest.raises(CLIError, match="accessible by group or others"):
            resolve_wallet_password("w", password_file=str(link), interactive_ok=False)

    def test_symlink_to_safe_file_accepted(self, tmp_path):
        target = _password_file(tmp_path)
        link = tmp_path / "link.pass"
        link.symlink_to(target)
        assert resolve_wallet_password("w", password_file=str(link), interactive_ok=False) == SECRET

    def test_directory_refused(self, tmp_path):
        with pytest.raises(CLIError, match="not a regular file"):
            resolve_wallet_password("w", password_file=str(tmp_path), interactive_ok=False)

    def test_oversize_refused(self, tmp_path):
        path = _password_file(tmp_path, content="x" * 5000)
        with pytest.raises(CLIError, match="larger than"):
            resolve_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_empty_file_refused(self, tmp_path):
        path = _password_file(tmp_path, content="")
        with pytest.raises(CLIError, match="empty"):
            resolve_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_missing_file(self, tmp_path):
        with pytest.raises(CLIError, match="Cannot read password file"):
            resolve_wallet_password("w", password_file=str(tmp_path / "nope"), interactive_ok=False)


class TestNoTtyFailure:
    def test_failure_lists_supported_ways(self):
        with pytest.raises(CLIError) as exc:
            resolve_wallet_password("w", interactive_ok=False)
        msg = str(exc.value)
        for needle in ("--password-stdin", "--password-file", ENV_PASSWORD_FILE, ENV_PASSWORD):
            assert needle in msg


class TestSecretNeverLeaks:
    """The throwaway secret must appear in no output surface, success or failure."""

    def test_failure_paths_do_not_echo_secret(self, tmp_path, capsys):
        # conflict: two sources, one holds the secret
        path = _password_file(tmp_path)
        with pytest.raises(CLIError) as exc:
            resolve_wallet_password("w", password=SECRET, password_file=str(path), interactive_ok=False)
        assert SECRET not in str(exc.value)

        # refused file mode — env var holds the secret but resolution fails on the file
        bad = _password_file(tmp_path, mode=0o644, name="bad.pass")
        with pytest.raises(CLIError) as exc:
            resolve_wallet_password("w", password_file=str(bad), interactive_ok=False)
        assert SECRET not in str(exc.value)
        out = capsys.readouterr()
        assert SECRET not in out.out
        assert SECRET not in out.err

    def test_deprecation_warning_does_not_echo_secret(self, capsys):
        resolve_wallet_password("w", password=SECRET, interactive_ok=False)
        assert SECRET not in capsys.readouterr().err


class TestCommandWiring:
    """One per signing family: the resolved secret reaches the signing call."""

    def _wallet_file(self, tmp_path: Path) -> Path:
        wallet = tmp_path / "w.json"
        wallet.write_text(json.dumps({"address": "0x" + "ab" * 20, "private_key": "0x" + "11" * 32}))
        return wallet

    def test_bridge_withdraw_stdin_reaches_load_wallet(self, runner, tmp_path, monkeypatch):
        wallet = self._wallet_file(tmp_path)
        from aitbc_cli.commands.wallet import bridge as bridge_mod

        captured: dict[str, object] = {}

        def _fake_load(path, name, password=None):
            captured["password"] = password
            raise RuntimeError("stop-after-capture")

        monkeypatch.setattr(bridge_mod, "_load_wallet", _fake_load)
        result = runner.invoke(
            bridge_mod.withdraw,
            [
                "--amount",
                "1",
                "--eth-address",
                "0x" + "cd" * 20,
                "--wallet-name",
                "w",
                "--password-stdin",
            ],
            obj={"wallet_name": "other", "wallet_dir": tmp_path, "wallet_path": wallet},
            input=SECRET + "\n",
        )
        assert captured["password"] == SECRET
        assert SECRET not in result.output

    def test_bridge_withdraw_file_mode_refused_before_signing(self, runner, tmp_path, monkeypatch):
        wallet = self._wallet_file(tmp_path)
        weak = _password_file(tmp_path, mode=0o644)
        from aitbc_cli.commands.wallet import bridge as bridge_mod

        monkeypatch.setattr(bridge_mod, "_load_wallet", lambda *a, **k: pytest.fail("must not reach signing"))
        result = runner.invoke(
            bridge_mod.withdraw,
            [
                "--amount",
                "1",
                "--eth-address",
                "0x" + "cd" * 20,
                "--wallet-name",
                "w",
                "--password-file",
                str(weak),
            ],
            obj={"wallet_name": "other", "wallet_dir": tmp_path, "wallet_path": wallet},
        )
        assert result.exit_code != 0
        assert SECRET not in result.output

    def test_transactions_send_password_file(self, runner, tmp_path, monkeypatch):
        self._wallet_file(tmp_path)
        secret_file = _password_file(tmp_path)
        from aitbc_cli.commands import transactions as tx_mod

        captured: dict[str, object] = {}
        monkeypatch.setattr(tx_mod, "_resolve_transaction_rpc_url", lambda url: "http://test")
        monkeypatch.setattr(
            tx_mod,
            "_send_transaction_impl",
            lambda *a, **kw: captured.update(password=a[4]) or "0xhash",
        )
        monkeypatch.setattr("aitbc_cli.commands.transactions.wallet_dir", lambda: tmp_path)
        result = runner.invoke(
            tx_mod.send,
            [
                "--from",
                "w",
                "--to",
                "0x" + "ab" * 20,
                "--amount",
                "1",
                "--password-file",
                str(secret_file),
            ],
        )
        assert captured["password"] == SECRET, captured
        assert SECRET not in result.output

    def test_operations_message_stdin(self, runner, tmp_path, monkeypatch):
        self._wallet_file(tmp_path)
        from aitbc_cli.commands import operations as ops_mod

        captured: dict[str, object] = {}

        def _fake_decrypt(path, password):
            captured["password"] = password
            raise RuntimeError("stop-after-capture")

        monkeypatch.setattr(ops_mod, "decrypt_private_key", _fake_decrypt)
        monkeypatch.setattr(ops_mod, "wallet_dir", lambda: tmp_path)
        result = runner.invoke(
            ops_mod.message,
            ["--agent", "0xabc", "--message", "hi", "--wallet", "w", "--password-stdin"],
            obj={},
            input=SECRET + "\n",
        )
        assert captured["password"] == SECRET
        assert SECRET not in result.output
