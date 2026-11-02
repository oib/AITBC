"""MCP tool path-arg validation (CLI-SYSTEM-FILE-TRAVERSAL-1).

``get_remote_file`` (read_only_hint) and ``run_cron_job`` pass their path
argument straight to ``aitbc system file`` / ``aitbc system run-script`` on the
target host. The tools now refuse ``..`` segments and relative paths before any
remote call, so a client cannot lean on the CLI-side allowlist alone.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server


def _remote_spy():
    return mock.Mock(return_value={"host": "hub", "command": "", "returncode": 0, "stdout": "{}", "stderr": ""})


class TestGetRemoteFilePathArgs:
    @pytest.mark.parametrize(
        "path",
        [
            "/opt/aitbc/../../etc/hostname",
            "/opt/aitbc/./../etc/hostname",
            "/opt/aitbc/scripts/../../tmp/x.sh",
            "etc/hostname",
            "opt/aitbc/file",
        ],
    )
    def test_refuses_traversal_and_relative(self, path):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = json.loads(mcp_server.get_remote_file(file_path=path, role="hub"))
        assert out.get("error") == "invalid file path"
        spy.assert_not_called()

    def test_normal_path_reaches_remote(self):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            mcp_server.get_remote_file(file_path="/opt/aitbc/pyproject.toml", role="hub")
        spy.assert_called_once()
        assert "--path=/opt/aitbc/pyproject.toml" in spy.call_args[0][1]


class TestRunCronJobPathArgs:
    @pytest.mark.parametrize(
        "path",
        [
            "/opt/aitbc/scripts/../../tmp/x.sh",
            "tmp/x.sh",
        ],
    )
    def test_refuses_traversal_and_relative(self, path):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = json.loads(mcp_server.run_cron_job(role="hub", script_path=path, dry_run=False, confirm=True))
        assert out.get("error") == "invalid script path"
        spy.assert_not_called()
