"""Tests for the 2026-09-15 CLI gap fixes (GAP-04/05/06/11).

Covers ``resource status``/``deallocate`` (new coordinator-api lifecycle
commands), ``ipfs unpin`` (Kubo + filesystem-index paths),
``wallet staking-info --address`` (arbitrary-address query), and
``system env-set`` (unit EnvironmentFile upsert semantics).
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.ipfs import unpin
from aitbc_cli.commands.resource import deallocate, status
from aitbc_cli.commands.system import env_set
from aitbc_cli.commands.wallet.staking import staking_info


def extract_json_from_output(output):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = clean.strip().split("\n")
    json_lines = []
    in_json = False
    brace_depth = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(stripped)
            brace_depth += stripped.count("{")
            brace_depth -= stripped.count("}")
            if brace_depth == 0:
                break
    return json.loads("\n".join(json_lines))


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# GAP-04: resource status / deallocate
# ---------------------------------------------------------------------------


def test_resource_status_lists_allocations(runner):
    client = Mock()
    client.get.return_value = [
        {
            "allocation_id": "alloc_1",
            "agent_id": "agent-1",
            "status": "allocated",
            "cpu_cores": 2.0,
            "memory_gb": 4.0,
            "gpu_count": 0.0,
            "allocated_at": "2026-09-15T10:00:00",
        }
    ]
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(
            status, ["--agent-id", "agent-1", "--status", "allocated"], obj={"output_format": "json"}
        )
    assert result.exit_code == 0, result.output
    args, kwargs = client.get.call_args
    assert args[0] == "/v1/agent-performance/resources"
    assert kwargs["params"]["agent_id"] == "agent-1"
    assert kwargs["params"]["status"] == "allocated"


def test_resource_status_empty(runner):
    client = Mock()
    client.get.return_value = []
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(status, [], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output


def test_resource_deallocate_posts_release(runner):
    client = Mock()
    client.post.return_value = {"allocation_id": "alloc_1", "status": "released"}
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(deallocate, ["alloc_1", "--force"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    args, _ = client.post.call_args
    assert args[0] == "/v1/agent-performance/resources/alloc_1/deallocate"


def test_resource_deallocate_requires_confirmation(runner):
    client = Mock()
    with patch("aitbc_cli.commands.resource._client", return_value=client):
        result = runner.invoke(deallocate, ["alloc_1"], input="n\n", obj={"output_format": "json"})
    assert result.exit_code != 0
    client.post.assert_not_called()


# ---------------------------------------------------------------------------
# GAP-05: ipfs unpin
# ---------------------------------------------------------------------------


def test_ipfs_unpin_daemon_path(runner):
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=True),
        patch("aitbc_cli.commands.ipfs._ipfs_unpin_cid", return_value=True) as unpin_mock,
    ):
        result = runner.invoke(unpin, ["--cid", "QmTest123"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    unpin_mock.assert_called_once()
    data = extract_json_from_output(result.output)
    assert data["success"] is True
    assert data["data"]["pinned"] is False


def test_ipfs_unpin_filesystem_fallback(runner):
    items = [{"cid": "QmA", "pinned": True}, {"cid": "QmB", "pinned": True}]
    saved = []
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=False),
        patch("aitbc_cli.commands.ipfs._ensure_ipfs_dir"),
        patch("aitbc_cli.commands.ipfs._load_index", return_value=items),
        patch("aitbc_cli.commands.ipfs._save_index", side_effect=lambda x: saved.append(x)),
    ):
        result = runner.invoke(unpin, ["--cid", "QmA"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert saved[0][0]["pinned"] is False
    assert saved[0][1]["pinned"] is True


def test_ipfs_unpin_unknown_cid_errors(runner):
    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=False),
        patch("aitbc_cli.commands.ipfs._ensure_ipfs_dir"),
        patch("aitbc_cli.commands.ipfs._load_index", return_value=[]),
    ):
        result = runner.invoke(unpin, ["--cid", "QmMissing"], obj={"output_format": "json"})
    assert result.exit_code != 0
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# GAP-06: wallet staking-info --address
# ---------------------------------------------------------------------------


def _staking_client():
    client = Mock()
    client.get.return_value = {
        "total_staked": 0,
        "active_stake_count": 0,
        "active_stakes": [],
    }
    return client


def test_staking_info_address_override_skips_wallet(runner, tmp_path):
    client = _staking_client()
    missing_wallet = tmp_path / "no-such-wallet.json"
    with (
        patch("aitbc_cli.commands.wallet.staking.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="ait-test"),
    ):
        result = runner.invoke(
            staking_info,
            ["--address", "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d"],
            obj={
                "wallet_name": "doesnotexist",
                "wallet_path": missing_wallet,
                "rpc_url": "http://localhost:8202",
                "output_format": "json",
            },
        )
    assert result.exit_code == 0, result.output
    args, _ = client.get.call_args
    assert "/rpc/staking/0xdb5247d03ca2e40f3995a583b2c097ab703efd4d" in args[0].lower()
    assert "doesnotexist" not in result.output or "(by address)" in result.output


def test_staking_info_address_override_validates(runner, tmp_path):
    client = _staking_client()
    with (
        patch("aitbc_cli.commands.wallet.staking.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="ait-test"),
    ):
        result = runner.invoke(
            staking_info,
            ["--address", "not-an-address"],
            obj={
                "wallet_name": "w",
                "wallet_path": tmp_path / "w.json",
                "rpc_url": "http://localhost:8202",
                "output_format": "json",
            },
        )
    assert "Invalid sender address" in result.output
    client.get.assert_not_called()


def test_staking_info_default_requires_wallet(runner, tmp_path):
    missing_wallet = tmp_path / "gone.json"
    result = runner.invoke(
        staking_info,
        [],
        obj={
            "wallet_name": "gone",
            "wallet_path": missing_wallet,
            "rpc_url": "http://localhost:8202",
            "output_format": "json",
        },
    )
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# GAP-11: system env-set
# ---------------------------------------------------------------------------


def test_env_set_upserts_and_appends(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("FOO=old\nBAR=keep\nexport OLD_EXPORT=x\n")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "FOO=new", "BAZ=added", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    text = env_file.read_text()
    assert "FOO=new" in text
    assert "BAR=keep" in text
    assert "BAZ=added" in text
    assert "FOO=old" not in text
    # values are never echoed — only key names
    assert "added" not in result.output
    assert "BAZ" in result.output


def test_env_set_rejects_malformed_assignment(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("FOO=old\n")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "NOEQUALS", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output
    assert env_file.read_text() == "FOO=old\n"


def test_env_set_rejects_bad_key_name(runner, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("")
    result = runner.invoke(
        env_set,
        ["blockchain-node", "1BAD=x", "--env-file", str(env_file), "--no-restart"],
        obj={},
    )
    assert result.exit_code != 0
    assert "Invalid environment variable name" in result.output


def test_env_set_refuses_unit_without_env_file(runner):
    with patch("aitbc_cli.commands.system._unit_env_file", return_value=None):
        result = runner.invoke(env_set, ["nonexistent-svc", "FOO=1", "--no-restart"], obj={})
    assert result.exit_code != 0
    assert "No EnvironmentFile" in result.output or "--env-file" in result.output
