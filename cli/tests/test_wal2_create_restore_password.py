"""WAL-2: wallet create/restore under the WAL-1 secret standard.

``resolve_new_wallet_password`` reuses the signing resolver's sources and
precedence, but creation semantics differ: non-TTY sources are
self-confirming (returned once), only the TTY fallback runs the two-prompt
confirm loop, and only the TTY path writes the system keyring. A password
supplied by file, stdin or env is never copied into another store.

``wallet create`` resolves through it unless ``--no-encrypt`` is given
(which skips resolution entirely and conflicts with a password flag).
``wallet restore`` keeps a verbatim copy by default; a plaintext backup +
``--password-file``/``--password-stdin`` encrypts under the resolved
password (verified against the backup's own address before the atomic
0600 write), while a password source on an already-encrypted backup is an
explicit non-zero refusal before anything is written.

All keys and passwords here are throwaway values generated in-process;
the secret must never appear in stdout, stderr or logs.
"""

import io
import json
import secrets
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.wallet_secret import (
    ENV_PASSWORD,
    ENV_PASSWORD_FILE,
    resolve_new_wallet_password,
)

SECRET = secrets.token_urlsafe(24)
ALT_SECRET = secrets.token_urlsafe(24)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No password env may leak between tests; stdin defaults to non-TTY."""
    for var in (ENV_PASSWORD, ENV_PASSWORD_FILE, "WALLET_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    for var in list(__import__("os").environ):
        if var.startswith(f"{ENV_PASSWORD}_"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    yield


def _password_file(tmp_path: Path, content: str = SECRET, mode: int = 0o600, name: str = "wallet.pass") -> Path:
    path = tmp_path / name
    path.write_text(content)
    path.chmod(mode)
    return path


class TestNewPasswordSources:
    """Same precedence as signing; every non-TTY source returns once."""

    def test_file_source_accepted_0600(self, tmp_path):
        path = _password_file(tmp_path)
        assert resolve_new_wallet_password("w", password_file=str(path), interactive_ok=False) == SECRET

    def test_file_source_refused_0644(self, tmp_path):
        path = _password_file(tmp_path, mode=0o644)
        with pytest.raises(CLIError, match="accessible by group or others"):
            resolve_new_wallet_password("w", password_file=str(path), interactive_ok=False)

    def test_stdin_reads_exactly_once(self, monkeypatch):
        stream = io.StringIO(SECRET + "\n")
        monkeypatch.setattr(sys, "stdin", stream)
        assert resolve_new_wallet_password("w", password_stdin=True, interactive_ok=False) == SECRET
        # one readline only — nothing else may be consumed or re-read
        assert stream.tell() == len(SECRET) + 1

    def test_env_password_file(self, tmp_path, monkeypatch):
        path = _password_file(tmp_path)
        monkeypatch.setenv(ENV_PASSWORD_FILE, str(path))
        assert resolve_new_wallet_password("w", interactive_ok=False) == SECRET

    def test_env_password(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, SECRET)
        assert resolve_new_wallet_password("w", interactive_ok=False) == SECRET

    def test_per_wallet_env_beats_generic(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, "generic")
        monkeypatch.setenv(f"{ENV_PASSWORD}_SHOP", SECRET)
        assert resolve_new_wallet_password("shop", interactive_ok=False) == SECRET

    def test_deprecated_password_flag_warns_self_confirming(self, capsys):
        assert resolve_new_wallet_password("w", password=SECRET, interactive_ok=False) == SECRET
        err = capsys.readouterr().err
        assert "deprecated" in err or "process lists" in err
        assert SECRET not in err

    def test_empty_password_flag_refused(self):
        with pytest.raises(CLIError, match="empty wallet password"):
            resolve_new_wallet_password("w", password="", interactive_ok=False)

    def test_empty_password_env_refused(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, "")
        with pytest.raises(CLIError, match="empty wallet password"):
            resolve_new_wallet_password("w", interactive_ok=False)

    def test_two_flag_sources_fail(self, tmp_path):
        path = _password_file(tmp_path)
        with pytest.raises(CLIError, match="Conflicting password sources"):
            resolve_new_wallet_password("w", password=SECRET, password_file=str(path), interactive_ok=False)

    def test_non_tty_no_source_fails_closed(self):
        with pytest.raises(CLIError) as exc:
            resolve_new_wallet_password("w", interactive_ok=False)
        for needle in ("--password-stdin", "--password-file", ENV_PASSWORD_FILE, ENV_PASSWORD):
            assert needle in str(exc.value)


class TestNewPasswordTty:
    """Only the TTY path confirms twice and writes the keyring."""

    def _fake_tty(self, monkeypatch, responses):
        class _Tty(io.StringIO):
            def isatty(self):
                return True

        monkeypatch.setattr(sys, "stdin", _Tty(""))
        answers = iter(responses)
        monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))

    def test_tty_confirms_twice_and_stores_keyring(self, monkeypatch):
        stored: dict[str, str] = {}
        monkeypatch.setattr("keyring.set_password", lambda service, name, pw: stored.update(service=service, name=name, pw=pw))
        self._fake_tty(monkeypatch, [SECRET, SECRET])
        assert resolve_new_wallet_password("w") == SECRET
        assert stored == {"service": "aitbc-wallet", "name": "w", "pw": SECRET}

    def test_tty_mismatch_reprompts(self, monkeypatch, capsys):
        stored: list[tuple[str, str]] = []
        monkeypatch.setattr("keyring.set_password", lambda service, name, pw: stored.append((name, pw)))
        self._fake_tty(monkeypatch, [SECRET, "wrong", SECRET, SECRET])
        assert resolve_new_wallet_password("w") == SECRET
        assert "do not match" in capsys.readouterr().err
        # exactly one keyring write — only after the successful confirm
        assert stored == [("w", SECRET)]

    def test_tty_empty_password_reprompts(self, monkeypatch, capsys):
        self._fake_tty(monkeypatch, ["", SECRET, SECRET])
        monkeypatch.setattr("keyring.set_password", lambda *a: None)
        assert resolve_new_wallet_password("w") == SECRET
        assert "empty" in capsys.readouterr().err

    def test_keyring_read_but_never_written_from_non_tty(self, monkeypatch):
        monkeypatch.setattr("keyring.get_password", lambda service, name: SECRET)
        monkeypatch.setattr("keyring.set_password", lambda *a: pytest.fail("non-TTY source must not write keyring"))
        assert resolve_new_wallet_password("w", interactive_ok=False) == SECRET

    def test_env_source_never_written_to_keyring(self, monkeypatch):
        monkeypatch.setenv(ENV_PASSWORD, SECRET)
        monkeypatch.setattr("keyring.set_password", lambda *a: pytest.fail("env source must not write keyring"))
        assert resolve_new_wallet_password("w", interactive_ok=False) == SECRET


class TestNewPasswordNeverLeaks:
    def test_secret_in_no_output_surface(self, tmp_path, capsys, caplog):
        bad = _password_file(tmp_path, content=SECRET, mode=0o644)
        with pytest.raises(CLIError) as exc:
            resolve_new_wallet_password("w", password_file=str(bad), interactive_ok=False)
        out = capsys.readouterr()
        assert SECRET not in str(exc.value)
        assert SECRET not in out.out and SECRET not in out.err
        assert SECRET not in caplog.text


# ---------------------------------------------------------------- commands


def _new_key_wallet(tmp_path: Path, name: str = "w") -> tuple[Path, str]:
    """A throwaway plaintext wallet file with a real generated key."""
    from eth_account import Account

    account = Account.create()
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "wallet_id": name,
                "address": account.address,
                "private_key": account.key.hex(),
                "created_at": "2024-01-01T00:00:00Z",
            }
        )
    )
    return path, account.address


def _encrypted_backup(tmp_path: Path, name: str = "enc") -> Path:
    """A throwaway wallet backup in the dict-encrypted form."""
    from aitbc_cli.commands.wallet import encrypt_value
    from eth_account import Account

    account = Account.create()
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "wallet_id": name,
                "address": account.address,
                "private_key": encrypt_value(account.key.hex(), ALT_SECRET),
                "encrypted": True,
            }
        )
    )
    return path


@pytest.fixture
def _wallet_ctx(tmp_path, monkeypatch):
    """Neutralise the wallet group's chain-id probe and daemon adapter."""
    monkeypatch.setattr("aitbc_cli.utils.chain_id.get_chain_id", lambda *a, **k: "test-chain")
    monkeypatch.setattr(
        "aitbc_cli.utils.dual_mode_wallet_adapter.DualModeWalletAdapter.is_daemon_available", lambda self: False
    )
    return tmp_path


def _invoke_wallet(runner, tmp_path, args, **kw):
    from aitbc_cli.commands.wallet import wallet

    target = tmp_path / "newwallet.json"
    return runner.invoke(wallet, ["--wallet-path", str(target), *args], **kw), target


class TestCreateCommand:
    def test_create_password_file_encrypts(self, runner, tmp_path, _wallet_ctx):
        pf = _password_file(tmp_path)
        result, target = _invoke_wallet(
            runner, tmp_path, ["create", "--name", "newwallet", "--type", "simple", "--password-file", str(pf)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert data["encrypted"] is True
        assert isinstance(data["private_key"], dict)
        # and the blob round-trips under the supplied password to the same key
        from aitbc_cli.commands.wallet import decrypt_value
        from eth_account import Account

        assert Account.from_key(decrypt_value(data["private_key"], SECRET)).address == data["address"]
        assert SECRET not in result.output

    def test_create_stdin_password(self, runner, tmp_path, _wallet_ctx):
        result, target = _invoke_wallet(
            runner,
            tmp_path,
            ["create", "--name", "newwallet", "--type", "simple", "--password-stdin"],
            input=SECRET + "\n",
        )
        assert result.exit_code == 0, result.output
        assert json.loads(target.read_text())["encrypted"] is True
        assert SECRET not in result.output

    def test_create_no_encrypt_skips_resolution(self, runner, tmp_path, _wallet_ctx):
        """--no-encrypt needs no password source at all — even with no TTY."""
        result, target = _invoke_wallet(
            runner, tmp_path, ["create", "--name", "newwallet", "--type", "simple", "--no-encrypt"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert "encrypted" not in data or data["encrypted"] is False
        assert isinstance(data["private_key"], str)

    def test_create_no_encrypt_plus_password_flag_refused(self, runner, tmp_path, _wallet_ctx):
        pf = _password_file(tmp_path)
        result, target = _invoke_wallet(
            runner,
            tmp_path,
            ["create", "--name", "newwallet", "--type", "simple", "--no-encrypt", "--password-file", str(pf)],
        )
        assert result.exit_code != 0
        assert not target.exists()
        assert SECRET not in result.output

    def test_create_password_flag_encrypts_and_warns(self, runner, tmp_path, _wallet_ctx):
        """The deprecated argv password still reaches the resolver."""
        result, target = _invoke_wallet(
            runner, tmp_path, ["create", "--name", "newwallet", "--type", "simple", "--password", SECRET]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert data["encrypted"] is True
        from aitbc_cli.commands.wallet import decrypt_value
        from eth_account import Account

        assert Account.from_key(decrypt_value(data["private_key"], SECRET)).address == data["address"]
        assert SECRET not in result.output

    def test_create_no_source_no_tty_fails_closed(self, runner, tmp_path, _wallet_ctx):
        result, target = _invoke_wallet(runner, tmp_path, ["create", "--name", "newwallet", "--type", "simple"])
        assert result.exit_code != 0
        assert not target.exists()


class TestRestoreCommand:
    def test_restore_plaintext_no_flags_is_verbatim(self, runner, tmp_path, _wallet_ctx):
        backup, _addr = _new_key_wallet(tmp_path / "bak", "bak")
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            ["--wallet-path", str(target), "restore", "--backup-path", str(backup), "--name", "restored"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert isinstance(data["private_key"], str)  # still plaintext
        assert "encrypted" not in data or data["encrypted"] is False

    def test_restore_encrypted_no_flags_is_verbatim(self, runner, tmp_path, _wallet_ctx):
        backup = _encrypted_backup(tmp_path)
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            ["--wallet-path", str(target), "restore", "--backup-path", str(backup), "--name", "restored"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert isinstance(data["private_key"], dict)  # still encrypted with the ORIGINAL password
        from aitbc_cli.commands.wallet import decrypt_value
        from eth_account import Account

        assert Account.from_key(decrypt_value(data["private_key"], ALT_SECRET)).address == data["address"]

    def test_restore_plaintext_with_password_file_encrypts(self, runner, tmp_path, _wallet_ctx):
        backup, addr = _new_key_wallet(tmp_path / "bak", "bak")
        pf = _password_file(tmp_path)
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            [
                "--wallet-path",
                str(target),
                "restore",
                "--backup-path",
                str(backup),
                "--name",
                "restored",
                "--password-file",
                str(pf),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert data["encrypted"] is True
        assert isinstance(data["private_key"], dict)
        # mode 0600, address preserved, blob round-trips to the same key
        assert target.stat().st_mode & 0o777 == 0o600
        from aitbc_cli.commands.wallet import decrypt_value
        from eth_account import Account

        assert Account.from_key(decrypt_value(data["private_key"], SECRET)).address == addr
        assert data["address"] == addr
        assert SECRET not in result.output

    def test_restore_plaintext_with_stdin_encrypts(self, runner, tmp_path, _wallet_ctx):
        backup, addr = _new_key_wallet(tmp_path / "bak", "bak")
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            ["--wallet-path", str(target), "restore", "--backup-path", str(backup), "--name", "restored", "--password-stdin"],
            input=SECRET + "\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(target.read_text())
        assert data["encrypted"] is True
        from aitbc_cli.commands.wallet import decrypt_value
        from eth_account import Account

        assert Account.from_key(decrypt_value(data["private_key"], SECRET)).address == addr

    def test_restore_encrypted_with_password_source_aborts(self, runner, tmp_path, _wallet_ctx):
        backup = _encrypted_backup(tmp_path)
        pf = _password_file(tmp_path)
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            [
                "--wallet-path",
                str(target),
                "restore",
                "--backup-path",
                str(backup),
                "--name",
                "restored",
                "--password-file",
                str(pf),
            ],
        )
        assert result.exit_code != 0
        assert "already encrypted" in result.output
        assert not target.exists()  # nothing written on the conflict path
        assert SECRET not in result.output

    def test_restore_no_password_flag_offered(self, runner, tmp_path, _wallet_ctx):
        """restore deliberately has no ``--password`` argv source."""
        backup, _ = _new_key_wallet(tmp_path / "bak", "bak")
        target = tmp_path / "out" / "restored.json"
        target.parent.mkdir()
        result = runner.invoke(
            __import__("aitbc_cli.commands.wallet", fromlist=["wallet"]).wallet,
            [
                "--wallet-path",
                str(target),
                "restore",
                "--backup-path",
                str(backup),
                "--name",
                "restored",
                "--password",
                SECRET,
            ],
        )
        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "No such option" in result.output
