"""Tests for ``aitbc exchange verify`` (CLI-2) — the read-only wrapper
around scripts/ops/exchange_verify.py.

The wrapper execs the script with the CLI's own interpreter as an argv list
(never a shell), validates --db/--bridge-db as absolute existing regular
files under /var/lib/aitbc/ (no '..', no symlinks), defaults to --no-chain
unless an RPC endpoint is given, and passes the script's exit code +
FAIL/WARN lines through.
"""

import os
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.exchange.hub_orders as hub_mod
from aitbc_cli.commands.exchange.hub_orders import verify as verify_cmd


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _db_prefix(tmp_path):
    """Point the /var/lib/aitbc/ containment root at tmp_path for the suite."""
    with mock.patch.object(hub_mod, "_VERIFY_DB_ALLOWED_PREFIX", str(tmp_path) + "/"):
        yield tmp_path


def test_verify_builds_argv_no_chain_default(runner, tmp_path):
    db = tmp_path / "exchange.db"
    db.write_bytes(b"SQLite")
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return mock.Mock(returncode=0, stdout="OK all checks\n", stderr="")

    with (
        mock.patch.object(hub_mod, "_verify_script_path", return_value=tmp_path / "exchange_verify.py"),
        mock.patch.object(hub_mod.subprocess, "run", side_effect=fake_run),
    ):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(db)])
    assert result.exit_code == 0, result.output
    argv = captured["argv"]
    import sys as _sys

    assert argv[0] == _sys.executable
    assert str(tmp_path / "exchange_verify.py") == argv[1]
    assert "--no-chain" in argv
    assert "OK all checks" in result.output


def test_verify_rpc_given_drops_no_chain(runner, tmp_path):
    db = tmp_path / "exchange.db"
    db.write_bytes(b"SQLite")
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return mock.Mock(returncode=0, stdout="", stderr="")

    with (
        mock.patch.object(hub_mod, "_verify_script_path", return_value=tmp_path / "s.py"),
        mock.patch.object(hub_mod.subprocess, "run", side_effect=fake_run),
    ):
        result = runner.invoke(
            verify_cmd, obj={"output_format": "table"}, args=["--db", str(db), "--rpc-url", "http://127.0.0.1:8545"]
        )
    assert result.exit_code == 0, result.output
    assert "--no-chain" not in captured["argv"]
    assert "http://127.0.0.1:8545" in captured["argv"]


def test_verify_passthrough_exit_code_and_fail_lines(runner, tmp_path):
    db = tmp_path / "exchange.db"
    db.write_bytes(b"SQLite")
    script_out = "FAIL nonce reuse: order 7\nWARN lagging rpc\n"
    with (
        mock.patch.object(hub_mod, "_verify_script_path", return_value=tmp_path / "s.py"),
        mock.patch.object(hub_mod.subprocess, "run", return_value=mock.Mock(returncode=1, stdout=script_out, stderr="")),
    ):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(db)])
    assert result.exit_code == 1
    assert "FAIL nonce reuse: order 7" in result.output
    assert "WARN lagging rpc" in result.output


def test_verify_db_omitted_lets_script_default(runner, tmp_path):
    """CLI-5: no --db → argv carries none; exchange_verify.py resolves the
    service default itself (EXCHANGE_DATABASE_URL / AITBC_DATA_DIR)."""
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return mock.Mock(returncode=0, stdout="OK\n", stderr="")

    with (
        mock.patch.object(hub_mod, "_verify_script_path", return_value=tmp_path / "exchange_verify.py"),
        mock.patch.object(hub_mod.subprocess, "run", side_effect=fake_run),
    ):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=[])
    assert result.exit_code == 0, result.output
    assert "--db" not in captured["argv"]
    assert "--no-chain" in captured["argv"]


@pytest.mark.parametrize("bad", ["relative.db", "also/relative.db"])
def test_verify_rejects_relative_db(runner, bad):
    result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", bad])
    assert result.exit_code != 0
    assert "absolute" in result.output


def test_verify_rejects_dotdot(runner, tmp_path):
    result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", f"{tmp_path}/../x.db"])
    assert result.exit_code != 0
    assert ".." in result.output


def test_verify_rejects_missing_file(runner, tmp_path):
    result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(tmp_path / "gone.db")])
    assert result.exit_code != 0


def test_verify_rejects_symlink(runner, tmp_path):
    real = tmp_path / "real.db"
    real.write_bytes(b"x")
    link = tmp_path / "link.db"
    os.symlink(real, link)
    result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(link)])
    assert result.exit_code != 0
    assert "symlink" in result.output


def test_verify_missing_script_clear_error(runner, tmp_path):
    db = tmp_path / "exchange.db"
    db.write_bytes(b"x")
    with mock.patch.object(
        hub_mod, "_verify_script_path", side_effect=hub_mod.click.ClickException("exchange_verify.py not found")
    ):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(db)])
    assert result.exit_code != 0
    assert "exchange_verify.py not found" in result.output


def test_verify_accepts_db_under_prefix(runner, tmp_path):
    db = tmp_path / "data" / "exchange" / "exchange.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"SQLite")
    bridge = tmp_path / "bridge_deposits.db"
    bridge.write_bytes(b"SQLite")
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return mock.Mock(returncode=0, stdout="", stderr="")

    with (
        mock.patch.object(hub_mod, "_verify_script_path", return_value=tmp_path / "s.py"),
        mock.patch.object(hub_mod.subprocess, "run", side_effect=fake_run),
    ):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(db), "--bridge-db", str(bridge)])
    assert result.exit_code == 0, result.output
    assert str(db) in captured["argv"] and str(bridge) in captured["argv"]


def test_verify_rejects_db_outside_prefix(runner):
    # /etc/hosts: absolute, exists, regular file — fails only the prefix check.
    # Re-patch to the production root so the error names it.
    with mock.patch.object(hub_mod, "_VERIFY_DB_ALLOWED_PREFIX", "/var/lib/aitbc/"):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", "/etc/hosts"])
    assert result.exit_code != 0
    assert "--db must be under /var/lib/aitbc: /etc/hosts" in result.output


def test_verify_rejects_bridge_db_outside_prefix(runner, tmp_path):
    db = tmp_path / "exchange.db"
    db.write_bytes(b"x")
    result = runner.invoke(
        verify_cmd,
        obj={"output_format": "table"},
        args=["--db", str(db), "--bridge-db", "/etc/hosts"],
    )
    assert result.exit_code != 0
    assert "--bridge-db must be under" in result.output


def test_verify_prefix_boundary_not_fooled(runner, tmp_path):
    """``<prefix>-evil/`` must not satisfy a startswith check on ``<prefix>/``."""
    evil = tmp_path / "aitbc-evil"
    evil.mkdir()
    db = evil / "exchange.db"
    db.write_bytes(b"x")
    with mock.patch.object(hub_mod, "_VERIFY_DB_ALLOWED_PREFIX", str(tmp_path / "aitbc") + "/"):
        result = runner.invoke(verify_cmd, obj={"output_format": "table"}, args=["--db", str(db)])
    assert result.exit_code != 0
    assert "must be under" in result.output
