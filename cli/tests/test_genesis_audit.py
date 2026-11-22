"""Regression tests for the genesis sync/verify/reset audit cluster.

Covers #2542 (sync-from-hub placeholder/force clobber), #2543 (verify never
cross-checks file vs DB), #2526 (re.sub replacement-template corruption),
#2528 (_chown_aitbc misses LookupError), #2529 (wallet created_at '+00:00Z'
and group-readable key), #2571 (reset script stderr lost via check=True),
#2572 (wallet DBs cleared before the wallet precondition, no backup), and
#2593 (key-bearing env file created with umask then chmod'ed, non-atomic).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from aitbc_cli.utils import genesis_reset


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    root.mkdir()
    monkeypatch.setenv("AITBC_RESET_SCRATCH", str(root))
    return root


# ------------------------------------------------------------------ #2526


def test_replace_or_append_backslash_round_trip(tmp_path):
    """A value containing backslashes must land verbatim — re.sub's
    replacement template used to eat them or raise (#2526)."""
    env = tmp_path / "node.env"
    env.write_text("CHAIN_ID=bc-2\nGENESIS_PRIVATE_KEY=old\n")
    value = "ab\\cd\\x41"
    genesis_reset._replace_or_append(env, "GENESIS_PRIVATE_KEY", value)
    text = env.read_text()
    assert f"GENESIS_PRIVATE_KEY={value}" in text
    # _load_env must read the same value back byte-for-byte.
    assert genesis_reset._load_env(env)["GENESIS_PRIVATE_KEY"] == value


def test_replace_or_append_backslash_reference_error(tmp_path):
    """'\\g<0>' style content raised re.error under the old template path."""
    env = tmp_path / "secrets.env"
    env.write_text("")
    genesis_reset._replace_or_append(env, "PROPOSER_KEY", "0x\\g<1>tail")
    assert "PROPOSER_KEY=0x\\g<1>tail" in env.read_text()


# ------------------------------------------------------------------ #2593


def test_replace_or_append_mode_at_write_and_atomic(tmp_path):
    """The env file is 0600 from creation (never umask-wide) and a rewrite
    replaces it atomically (#2593)."""
    env = tmp_path / "blockchain-secrets.env"
    env.write_text("A=1\n")
    env.chmod(0o644)
    genesis_reset._replace_or_append(env, "B", "secret")
    assert env.stat().st_mode & 0o777 == 0o600
    assert "B=secret" in env.read_text()
    # No temp files left behind by the atomic write.
    assert not list(tmp_path.glob("*.tmp"))


def test_replace_or_append_preserves_owner(tmp_path):
    """An in-place rewrite keeps the file's owner/group (best-effort)."""
    env = tmp_path / "node.env"
    env.write_text("A=1\n")
    st = env.stat()
    genesis_reset._replace_or_append(env, "B", "2")
    st2 = env.stat()
    assert (st2.st_uid, st2.st_gid) == (st.st_uid, st.st_gid)


# ------------------------------------------------------------------ #2528


def test_chown_aitbc_absent_user_falls_back(tmp_path, monkeypatch):
    """shutil.chown raises LookupError for an absent user — the root
    fallback must still run instead of propagating (#2528)."""
    calls = []

    def _fake_chown(path, user, group):
        calls.append((user, group))
        if user == "aitbc":
            raise LookupError("no such user: 'aitbc'")

    monkeypatch.setattr(genesis_reset.shutil, "chown", _fake_chown)
    genesis_reset._chown_aitbc(tmp_path / "f")
    assert calls == [("aitbc", "aitbc"), ("root", "root")]


def test_chown_chain_data_tolerates_lookup_error(tmp_path, monkeypatch):
    def _fake_chown(path, user, group):
        raise LookupError("no such user")

    monkeypatch.setattr(genesis_reset.shutil, "chown", _fake_chown)
    chain_dir = tmp_path / "chain"
    chain_dir.mkdir()
    (chain_dir / "chain.db").write_text("x")
    genesis_reset._chown_chain_data(chain_dir)  # must not raise


# ------------------------------------------------------------------ #2529


def test_write_default_wallet_timestamp_and_mode(tmp_path):
    wallet_dir = tmp_path / "wallets"
    genesis_reset._write_default_wallet(wallet_dir, "0xabc", "0xpub", "ab" * 32, "bc-2")
    wallet = json.loads((wallet_dir / "default.json").read_text())
    created = wallet["created_at"]
    assert created.endswith("Z")
    assert "+00:00" not in created
    assert (wallet_dir / "default.json").stat().st_mode & 0o777 == 0o600


# ------------------------------------------------------------------ #2571


def test_run_reset_script_failure_prints_stderr(monkeypatch, capsys):
    """A failing reset_chain_0x.py run must surface its stderr — check=True
    used to raise CalledProcessError before the returncode branch (#2571)."""
    proc = subprocess.CompletedProcess(args=["x"], returncode=3, stdout="", stderr="boom-detail")
    monkeypatch.setattr(genesis_reset, "_run_subprocess", lambda *a, **k: proc)
    ok = genesis_reset._run_reset_script(
        Path("/nonexistent/reset_chain_0x.py"), Path("/d/chain.db"), "bc-2", Path("/d"), Path("/e"), Path("/w")
    )
    assert ok is False
    assert "boom-detail" in capsys.readouterr().out


# ------------------------------------------------------------------ #2572


def _reset_env_dirs(scratch: Path) -> tuple[Path, Path, Path]:
    data_dir = scratch / "data"
    etc_dir = scratch / "etc"
    wallet_dir = scratch / "wallets"
    for d in (data_dir, etc_dir, wallet_dir):
        d.mkdir(parents=True, exist_ok=True)
    return data_dir, etc_dir, wallet_dir


def test_reset_genesis_wallet_db_survives_failed_precondition(scratch):
    """Missing GENESIS_ADDRESS + no --new-wallet: the wallet DBs must NOT be
    deleted before the precondition fails (#2572)."""
    data_dir, etc_dir, wallet_dir = _reset_env_dirs(scratch)
    ledger = data_dir / "wallet_ledger.db"
    keystore = data_dir / "keystore.db"
    ledger.write_text("x")
    keystore.write_text("x")
    # etc_dir has no node.env/blockchain.env -> no GENESIS_ADDRESS -> bail.
    result = genesis_reset.reset_genesis(
        chain_id="bc-2",
        new_wallet=False,
        password=None,
        yes=True,
        output_format="json",
        data_dir=data_dir,
        etc_dir=etc_dir,
        wallet_dir=wallet_dir,
    )
    assert result is None
    assert ledger.exists() and keystore.exists()


def test_reset_genesis_wallet_dbs_backed_up_then_cleared(scratch, monkeypatch):
    """On the success path the two DBs are copied into the reset backup dir
    before being cleared (#2572)."""
    data_dir, etc_dir, wallet_dir = _reset_env_dirs(scratch)
    (etc_dir / "node.env").write_text("GENESIS_ADDRESS=0x" + "11" * 20 + "\n")
    ledger = data_dir / "wallet_ledger.db"
    keystore = data_dir / "keystore.db"
    ledger.write_text("ledger-bytes")
    keystore.write_text("keystore-bytes")
    monkeypatch.setattr(genesis_reset, "_run_reset_script", lambda *a, **k: True)
    monkeypatch.setattr(genesis_reset, "_chown_chain_data", lambda p: None)
    result = genesis_reset.reset_genesis(
        chain_id="bc-2",
        new_wallet=False,
        password=None,
        yes=True,
        output_format="json",
        data_dir=data_dir,
        etc_dir=etc_dir,
        wallet_dir=wallet_dir,
    )
    assert result is not None
    assert not ledger.exists() and not keystore.exists()
    backups = list(scratch.glob("aitbc-genesis-reset-*/wallet_ledger.db"))
    assert len(backups) == 1
    assert backups[0].read_text() == "ledger-bytes"
    assert list(scratch.glob("aitbc-genesis-reset-*/keystore.db"))[0].read_text() == "keystore-bytes"


# ------------------------------------------------------------------ #2542


def _fake_httpx_client(payload, status_ok=True):
    class _Resp:
        def raise_for_status(self):
            if not status_ok:
                import httpx

                raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            self.url = url
            return _Resp()

    return _Client


def test_sync_from_hub_refuses_placeholder_document(scratch, monkeypatch):
    """A block-0-shaped row (no chain_id/allocations) must NOT be written as
    genesis.json — the command refuses instead (#2542)."""
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    block_row = {"chain_id": "bc-2", "height": 0, "hash": "0xabc", "proposer": "genesis"}
    monkeypatch.setattr(genesis_cmd.httpx, "Client", _fake_httpx_client(block_row))
    result = CliRunner().invoke(
        genesis_cmd.sync_from_hub,
        ["--chain-id", "bc-2", "--data-dir", str(data_dir), "--rpc-url", "http://hub.example"],
        obj={},
    )
    assert result.exit_code == 1
    assert not (data_dir / "bc-2" / "genesis.json").exists()


def test_sync_from_hub_writes_valid_document_and_backs_up(scratch, monkeypatch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    genesis_dir = data_dir / "bc-2"
    genesis_dir.mkdir(parents=True)
    existing = genesis_dir / "genesis.json"
    existing.write_text('{"chain_id": "bc-2", "genesis_hash": "0xold", "allocations": [{"address": "0x1"}]}')

    doc = {
        "chain_id": "bc-2",
        "genesis_hash": "0xnew",
        "allocations": [{"address": "0x1", "balance": "1"}],
        "state_root": "0x" + "00" * 32,
    }
    monkeypatch.setattr(genesis_cmd.httpx, "Client", _fake_httpx_client(doc))
    result = CliRunner().invoke(
        genesis_cmd.sync_from_hub,
        ["--chain-id", "bc-2", "--data-dir", str(data_dir), "--rpc-url", "http://hub.example", "--force"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    written = json.loads(existing.read_text())
    assert written["genesis_hash"] == "0xnew"
    assert written["allocations"] == doc["allocations"]
    backups = list(genesis_dir.glob("genesis.json.bak-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["genesis_hash"] == "0xold"


def test_sync_from_hub_rejects_wrong_chain_id(scratch, monkeypatch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    doc = {"chain_id": "other-chain", "genesis_hash": "0x1", "allocations": [{"address": "0x1"}]}
    monkeypatch.setattr(genesis_cmd.httpx, "Client", _fake_httpx_client(doc))
    result = CliRunner().invoke(
        genesis_cmd.sync_from_hub,
        ["--chain-id", "bc-2", "--data-dir", str(data_dir), "--rpc-url", "http://hub.example"],
        obj={},
    )
    assert result.exit_code == 1
    assert not (data_dir / "bc-2" / "genesis.json").exists()


# ------------------------------------------------------------------ #2543


def _write_chain_db(data_dir: Path, chain_id: str, genesis_hash: str) -> None:
    chain_dir = data_dir / chain_id
    chain_dir.mkdir(parents=True, exist_ok=True)
    db = chain_dir / "chain.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE block (height INTEGER, hash TEXT, proposer TEXT, chain_id TEXT)")
    conn.execute("CREATE TABLE account (chain_id TEXT)")
    conn.execute("INSERT INTO block VALUES (0, ?, 'genesis', ?)", (genesis_hash, chain_id))
    conn.execute("INSERT INTO account VALUES (?)", (chain_id,))
    conn.commit()
    conn.close()


def _write_genesis_file(data_dir: Path, chain_id: str, doc: dict) -> None:
    chain_dir = data_dir / chain_id
    chain_dir.mkdir(parents=True, exist_ok=True)
    (chain_dir / "genesis.json").write_text(json.dumps(doc))


def test_verify_fails_on_file_db_hash_mismatch(scratch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    _write_chain_db(data_dir, "bc-2", "0xsealed")
    _write_genesis_file(
        data_dir,
        "bc-2",
        {"chain_id": "bc-2", "genesis_hash": "0xdifferent", "allocations": [{"address": "0x1"}]},
    )
    result = CliRunner().invoke(genesis_cmd.verify, ["--chain-id", "bc-2", "--data-dir", str(data_dir)], obj={})
    assert result.exit_code == 1
    assert "does not match sealed block-0 hash" in result.output


def test_verify_fails_on_missing_required_fields(scratch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    _write_chain_db(data_dir, "bc-2", "0xsealed")
    _write_genesis_file(data_dir, "bc-2", {"note": "placeholder", "allocations": []})
    result = CliRunner().invoke(genesis_cmd.verify, ["--chain-id", "bc-2", "--data-dir", str(data_dir)], obj={})
    assert result.exit_code == 1
    assert "missing required fields" in result.output


def test_verify_passes_when_file_and_db_agree(scratch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    _write_chain_db(data_dir, "bc-2", "0xsealed")
    _write_genesis_file(
        data_dir,
        "bc-2",
        {"chain_id": "bc-2", "genesis_hash": "0xsealed", "allocations": [{"address": "0x1"}]},
    )
    result = CliRunner().invoke(genesis_cmd.verify, ["--chain-id", "bc-2", "--data-dir", str(data_dir)], obj={})
    assert result.exit_code == 0, result.output


def test_verify_fails_on_chain_id_mismatch(scratch):
    from aitbc_cli.commands import genesis as genesis_cmd

    data_dir = scratch / "data"
    _write_chain_db(data_dir, "bc-2", "0xsealed")
    _write_genesis_file(
        data_dir,
        "bc-2",
        {"chain_id": "other", "genesis_hash": "0xsealed", "allocations": [{"address": "0x1"}]},
    )
    result = CliRunner().invoke(genesis_cmd.verify, ["--chain-id", "bc-2", "--data-dir", str(data_dir)], obj={})
    assert result.exit_code == 1
    assert "does not match requested chain" in result.output
