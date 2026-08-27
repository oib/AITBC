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
        result = runner.invoke(ipfs, ["download", cid])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["success"] is True
    assert output["data"]["size"] == 13
