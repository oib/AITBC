"""Tests for aitbc.utils.reset_guard and the guarded reset entry points.

The legacy destructive tools (``aitbc genesis reset``, ``unified_genesis.py``,
``create-genesis-block.py``, ``reset_chain_0x.py``,
``reset-follower-to-genesis.sh``) must refuse unless every target resolves
under ``AITBC_RESET_SCRATCH`` — and must never write (or read a keystore from)
the live paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aitbc.utils import reset_guard

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UNIFIED_GENESIS = PROJECT_ROOT / "apps" / "blockchain-node" / "scripts" / "unified_genesis.py"
CREATE_GENESIS_BLOCK = PROJECT_ROOT / "scripts" / "ops" / "create-genesis-block.py"
RESET_CHAIN = PROJECT_ROOT / "scripts" / "utils" / "reset_chain_0x.py"
RESET_FOLLOWER_SH = PROJECT_ROOT / "scripts" / "ops" / "reset-follower-to-genesis.sh"
MCP_GENESIS_MODULE = PROJECT_ROOT / "mcp-server" / "aitbc_mcp_cli_tools_generated_genesis.py"


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    root = tmp_path / "scratch"
    root.mkdir()
    monkeypatch.setenv("AITBC_RESET_SCRATCH", str(root))
    return root


@pytest.fixture
def no_scratch(monkeypatch):
    monkeypatch.delenv("AITBC_RESET_SCRATCH", raising=False)


def test_scratch_root_required(no_scratch):
    with pytest.raises(reset_guard.ResetGuardError, match="AITBC_RESET_SCRATCH"):
        reset_guard.scratch_root()


def test_scratch_root_must_be_absolute(monkeypatch):
    monkeypatch.setenv("AITBC_RESET_SCRATCH", "relative/scratch")
    with pytest.raises(reset_guard.ResetGuardError, match="absolute"):
        reset_guard.scratch_root()


@pytest.mark.parametrize("bad", ["/var/lib/aitbc/scratch", "/etc/aitbc/scratch", "/root/scratch"])
def test_scratch_root_not_under_live_prefix(monkeypatch, bad):
    monkeypatch.setenv("AITBC_RESET_SCRATCH", bad)
    with pytest.raises(reset_guard.ResetGuardError, match="live path"):
        reset_guard.scratch_root()


def test_targets_under_scratch_pass(scratch):
    assert reset_guard.assert_scratch_targets(scratch / "data" / "chain.db") == scratch


def test_target_outside_scratch_refuses(scratch, tmp_path):
    with pytest.raises(reset_guard.ResetGuardError, match="outside scratch root"):
        reset_guard.assert_scratch_targets(tmp_path / "elsewhere")


@pytest.mark.parametrize(
    "target",
    ["/var/lib/aitbc/data/chain.db", "/etc/aitbc/node.env", "/root/.ssh/id"],
)
def test_live_targets_refuse(scratch, target):
    with pytest.raises(reset_guard.ResetGuardError):
        reset_guard.assert_scratch_targets(target)


def test_data_dir_env_unset_refuses(scratch, monkeypatch):
    monkeypatch.delenv("AITBC_DATA_DIR", raising=False)
    with pytest.raises(reset_guard.ResetGuardError, match="AITBC_DATA_DIR"):
        reset_guard.assert_data_dir_env()


def test_data_dir_env_under_scratch_passes(scratch, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(scratch / "data"))
    assert reset_guard.assert_data_dir_env() == scratch


def test_live_chain_id_refuses(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "blockchain.env").write_text("CHAIN_ID=ait-localnet\n")
    data = tmp_path / "data"
    (data / "ait-mainnet").mkdir(parents=True)
    with pytest.raises(reset_guard.ResetGuardError, match="live chain id"):
        reset_guard.assert_not_live_chain("ait-localnet", etc_dir=etc, data_dir=data)
    with pytest.raises(reset_guard.ResetGuardError, match="live chain id"):
        reset_guard.assert_not_live_chain("ait-mainnet", etc_dir=etc, data_dir=data)
    reset_guard.assert_not_live_chain("bc-2", etc_dir=etc, data_dir=data)


def test_single_proposer_rules(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    reset_guard.assert_single_proposer(etc)
    (etc / "blockchain.env").write_text('VALIDATOR_SET=[{"address":"0x1","stake":"1000"}]\n')
    reset_guard.assert_single_proposer(etc)
    (etc / "blockchain.env").write_text(
        'VALIDATOR_SET=[{"address":"0x1"},{"address":"0x2"},{"address":"0x3"},{"address":"0x4"}]\n'
    )
    with pytest.raises(reset_guard.ResetGuardError, match="multi-proposer|proposers"):
        reset_guard.assert_single_proposer(etc)


# --- Tool-level refusals -------------------------------------------------


def test_genesis_reset_refuses_without_marker(no_scratch, monkeypatch):
    from aitbc_cli.utils import genesis_reset

    calls: list[list[str]] = []

    def _record(cmd, **kw):
        calls.append(cmd)

    monkeypatch.setattr(genesis_reset, "_run_subprocess", _record)
    result = genesis_reset.reset_genesis(chain_id="bc-2", new_wallet=False, password=None, yes=True, output_format="json")
    assert result is None
    assert calls == []  # never reached systemctl


def test_genesis_reset_live_dirs_refuse(scratch):
    from aitbc_cli.utils import genesis_reset

    result = genesis_reset.reset_genesis(chain_id="bc-2", new_wallet=False, password=None, yes=True, output_format="json")
    assert result is None  # default /var/lib/aitbc + /etc/aitbc + wallet dirs refuse


def test_clear_wallet_dbs_honours_data_dir(tmp_path):
    from aitbc_cli.utils import genesis_reset

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ledger = data_dir / "wallet_ledger.db"
    ledger.write_text("x")
    keystore = data_dir / "keystore.db"
    keystore.write_text("x")
    genesis_reset._clear_wallet_dbs(data_dir)
    assert not ledger.exists()
    assert not keystore.exists()


@pytest.mark.skipif(not UNIFIED_GENESIS.exists(), reason="unified_genesis.py not in this checkout/archive")
def test_unified_genesis_refuses_without_marker(no_scratch):
    r = subprocess.run(
        [sys.executable, str(UNIFIED_GENESIS), "--chain-id", "bc-2"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "AITBC_RESET_SCRATCH": ""},
    )
    combined = r.stdout + r.stderr
    assert "reset-guard" in combined or "AITBC_RESET_SCRATCH" in combined


@pytest.mark.skipif(not UNIFIED_GENESIS.exists(), reason="unified_genesis.py not in this checkout/archive")
def test_unified_genesis_live_defaults_refuse(scratch):
    r = subprocess.run(
        [sys.executable, str(UNIFIED_GENESIS), "--chain-id", "bc-2"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "AITBC_RESET_SCRATCH": str(scratch)},
    )
    combined = r.stdout + r.stderr
    # Defaults point at /var/lib/aitbc — every one refuses.
    assert "refus" in combined or "reset-guard" in combined


def test_create_genesis_block_refuses_without_marker(no_scratch, tmp_path):
    out = tmp_path / "genesis.json"
    r = subprocess.run(
        [sys.executable, str(CREATE_GENESIS_BLOCK), "--chain-id", "bc-2", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        env={k: v for k, v in os.environ.items() if k != "AITBC_RESET_SCRATCH"},
    )
    assert r.returncode != 0
    assert not out.exists()


def test_create_genesis_block_update_env_always_refuses(scratch, tmp_path):
    keystore = scratch / "keystore.json"
    keystore.write_text('{"private_key": "0x' + "11" * 32 + '", "address": "0x0000000000000000000000000000000000000000"}')
    r = subprocess.run(
        [
            sys.executable,
            str(CREATE_GENESIS_BLOCK),
            "--chain-id",
            "bc-2",
            "--out",
            str(scratch / "genesis.json"),
            "--keystore",
            str(keystore),
            "--update-env",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "AITBC_RESET_SCRATCH": str(scratch)},
    )
    assert r.returncode != 0
    assert "update-env" in r.stderr + r.stdout


def test_reset_chain_0x_refuses_without_marker(no_scratch, tmp_path):
    db = tmp_path / "chain.db"
    r = subprocess.run(
        [sys.executable, str(RESET_CHAIN)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
        env={k: v for k, v in os.environ.items() if k != "AITBC_RESET_SCRATCH" and not k.startswith("AITBC_")}
        | {"CHAIN_ID": "bc-2", "DB_PATH": str(db)},
    )
    assert r.returncode == 1
    assert not db.exists()


def test_reset_follower_refuses_without_marker(no_scratch):
    r = subprocess.run(
        ["bash", str(RESET_FOLLOWER_SH)],
        capture_output=True,
        text=True,
        timeout=30,
        env={k: v for k, v in os.environ.items() if k != "AITBC_RESET_SCRATCH"} | {"CHAIN_ID": "test-chain"},
    )
    assert r.returncode == 1
    assert "AITBC_RESET_SCRATCH" in r.stderr


def test_reset_follower_live_defaults_refuse(scratch):
    r = subprocess.run(
        ["bash", str(RESET_FOLLOWER_SH)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "AITBC_RESET_SCRATCH": str(scratch), "CHAIN_ID": "test-chain"},
    )
    assert r.returncode == 1  # /var/lib/aitbc + /etc/aitbc defaults refuse


def test_guard_has_no_live_override():
    """No opt-out env: the only switch is the scratch marker itself."""
    import inspect

    src = inspect.getsource(reset_guard)
    for forbidden in ("AITBC_RESET_LIVE", "AITBC_RESET_FORCE", "AITBC_ALLOW_LIVE"):
        assert forbidden not in src


# --- MCP inheritance ------------------------------------------------------


@pytest.mark.skipif(not UNIFIED_GENESIS.exists(), reason="unified_genesis.py not in this checkout/archive")
def test_generated_mcp_genesis_tools_carry_guard():
    """The MCP genesis wrappers inherit the guard through the CLI layer.

    Regeneration rewrites the split module; this test fails if a future
    regen drops the mutating genesis tools, or if the code paths they shell
    out to ever lose the reset_guard wiring.
    """
    module = MCP_GENESIS_MODULE.read_text()
    assert "def aitbc_genesis_init(" in module
    assert "def aitbc_genesis_sync_from_hub(" in module
    guarded = (
        (PROJECT_ROOT / "cli" / "aitbc_cli" / "utils" / "genesis_reset.py").read_text()
        + (PROJECT_ROOT / "apps" / "blockchain-node" / "scripts" / "unified_genesis.py").read_text()
        + (PROJECT_ROOT / "cli" / "aitbc_cli" / "commands" / "genesis.py").read_text()
    )
    assert "reset_guard" in guarded


# --- Scratch-root depth -----------------------------------------------------


@pytest.mark.parametrize("bad", ["/", "/tmp", "/var", "/home", "/etc"])
def test_scratch_root_shallow_refuses(bad):
    """Filesystem root and top-level dirs are refused even though they sit
    outside the live prefixes: a scratch root must be a dedicated
    subdirectory (e.g. ``/tmp/<name>``)."""
    with pytest.raises(reset_guard.ResetGuardError, match="fewer than three"):
        reset_guard.scratch_root({"AITBC_RESET_SCRATCH": bad})


def test_scratch_root_symlink_to_root_refuses(tmp_path):
    link = tmp_path / "scratch-link"
    link.symlink_to("/")
    with pytest.raises(reset_guard.ResetGuardError, match="fewer than three"):
        reset_guard.scratch_root({"AITBC_RESET_SCRATCH": str(link)})


def test_scratch_root_dotdot_normalised_then_refused():
    # "/tmp/../tmp" resolves to /tmp — shallow after normalisation.
    with pytest.raises(reset_guard.ResetGuardError, match="fewer than three"):
        reset_guard.scratch_root({"AITBC_RESET_SCRATCH": "/tmp/../tmp"})


@pytest.mark.parametrize("ok", ["/tmp/bc2-rehearsal", "/tmp/a/b", "/var/tmp/scratch"])
def test_scratch_root_dedicated_subdir_accepted(ok):
    assert reset_guard.scratch_root({"AITBC_RESET_SCRATCH": ok}) == Path(ok)


def test_scratch_root_trailing_slash_accepted():
    assert reset_guard.scratch_root({"AITBC_RESET_SCRATCH": "/tmp/bc2-rehearsal/"}) == Path("/tmp/bc2-rehearsal")


# --- CLI refusal exit codes -------------------------------------------------


@pytest.fixture
def runner():
    from click.testing import CliRunner

    return CliRunner()


def test_sync_from_hub_refusal_exits_1(no_scratch, runner, tmp_path):
    """A reset-guard refusal exits 1 and writes nothing."""
    from aitbc_cli.core.main import cli

    data_dir = tmp_path / "data"
    result = runner.invoke(
        cli,
        ["genesis", "sync-from-hub", "--chain-id", "bc-2", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 1
    assert "reset-guard" in result.output or "AITBC_RESET_SCRATCH" in result.output
    assert not (data_dir / "bc-2" / "genesis.json").exists()


def test_sync_from_hub_existing_no_force_exits_1(scratch, runner):
    """Existing genesis.json without --force is a refusal too: exit 1, file
    left byte-identical."""
    from aitbc_cli.core.main import cli

    data_dir = scratch / "data"
    genesis_path = data_dir / "bc-2" / "genesis.json"
    genesis_path.parent.mkdir(parents=True)
    genesis_path.write_text('{"sentinel": true}')
    result = runner.invoke(
        cli,
        ["genesis", "sync-from-hub", "--chain-id", "bc-2", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 1
    assert genesis_path.read_text() == '{"sentinel": true}'


def test_genesis_reset_refusal_exits_1(no_scratch, runner):
    """`genesis reset` on an unguarded context exits 1 (reset_genesis returns
    None; the command must not report success)."""
    from aitbc_cli.core.main import cli

    result = runner.invoke(cli, ["genesis", "reset", "--chain-id", "bc-2", "--yes"])
    assert result.exit_code == 1


def test_genesis_reset_unknown_chain_id_exits_1(no_scratch, runner, monkeypatch):
    """No --chain-id and nothing resolvable: refusal exit 1, not 0."""
    import aitbc_cli.config as cli_config
    from aitbc_cli.core.main import cli

    class _EmptyConfig:
        chain_id = ""

    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.setattr(cli_config, "get_config", lambda: _EmptyConfig())
    result = runner.invoke(cli, ["genesis", "reset", "--yes"])
    assert result.exit_code == 1
