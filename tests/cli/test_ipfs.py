"""Tests for aitbc ipfs commands."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.ipfs import ipfs


@pytest.fixture
def runner():
    return CliRunner()


def test_upload_uses_daemon_when_available(runner, tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello ipfs")

    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=True),
        patch("aitbc_cli.commands.ipfs.requests.post") as mock_post,
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"Hash": "QmReal", "Size": "10"}
        result = runner.invoke(ipfs, ["upload", "--file", str(test_file)])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True
    assert output["data"]["cid"] == "QmReal"


def test_download_falls_back_when_daemon_down(runner, tmp_path):
    cid = "QmFake"
    ipfs_dir = tmp_path / "ipfs"
    ipfs_dir.mkdir()
    (ipfs_dir / cid).write_text("local content")

    with (
        patch("aitbc_cli.commands.ipfs._daemon_available", return_value=False),
        patch("aitbc_cli.commands.ipfs.IPFS_DIR", ipfs_dir),
    ):
        result = runner.invoke(ipfs, ["download", "--cid", cid])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True
    assert output["data"]["size"] == 13


def test_resolve_ipfs_api_probes_island_port(runner, monkeypatch):
    """#2263: island Kubo on :5002 must be found when :5001 is down, so uploads
    land in the same daemon market host pins against."""
    from aitbc_cli.commands import ipfs as ipfs_mod

    monkeypatch.delenv("IPFS_API_URL", raising=False)
    with patch.object(ipfs_mod, "_daemon_available", side_effect=lambda url: url.endswith("5002")):
        assert ipfs_mod.resolve_ipfs_api() == "http://127.0.0.1:5002"


def test_resolve_ipfs_api_none_when_no_daemon(monkeypatch):
    from aitbc_cli.commands import ipfs as ipfs_mod

    monkeypatch.delenv("IPFS_API_URL", raising=False)
    with patch.object(ipfs_mod, "_daemon_available", return_value=False):
        assert ipfs_mod.resolve_ipfs_api() is None
