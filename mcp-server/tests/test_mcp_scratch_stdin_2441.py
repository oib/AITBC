"""#2441: scalar env names, stdin forwarding, and /var/tmp scratch-file tool."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aitbc_mcp_server as mcp_server  # noqa: E402
import aitbc_mcp_scratch_tools  # noqa: E402,F401  (registers aitbc_scratch_file)

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent


def _isolated_server():
    """Fresh module instance — test_aitbc_mcp_cli_tools replaces
    ``mcp_server._run_remote`` process-wide, so real-runner tests need an
    isolated copy (same pattern as test_aitbc_mcp_server)."""
    spec = importlib.util.spec_from_file_location("aitbc_mcp_server_isolated_2441", MCP_SERVER_DIR / "aitbc_mcp_server.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str = "{}", stderr: str = "", returncode: int = 0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestScalarEnvNames:
    def _capture(self):
        captured: list[tuple] = []

        def fake(host, command, timeout=60, **kwargs):
            captured.append((command, kwargs))
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        return captured, mock.patch.object(mcp_server, "_run_remote", fake)

    def test_shop_wallet_address_scalar_accepted(self):
        captured, patcher = self._capture()
        with patcher:
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="ai",
                    subcommand=["jobs"],
                    env={"SHOP_WALLET_ADDRESS": "0xAbCdEf0123456789abcdef0123456789abcdef01"},
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        assert captured[0][0].startswith("SHOP_WALLET_ADDRESS=0xAbCdEf0123456789abcdef0123456789abcdef01 ")

    def test_default_wallet_name_scalar_accepted(self):
        captured, patcher = self._capture()
        with patcher:
            result = json.loads(
                mcp_server.run_aitbc_cli(
                    group="agent",
                    subcommand="register",
                    env={"AITBC_DEFAULT_WALLET": "scratch-shop"},
                    dry_run=False,
                    confirm=True,
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        assert "AITBC_DEFAULT_WALLET=scratch-shop" in captured[0][0]

    def test_scalar_value_with_control_chars_refused(self):
        result = json.loads(
            mcp_server.read_aitbc_cli(
                group="wallet",
                subcommand=["list"],
                env={"SHOP_WALLET_ADDRESS": "0x1234\nEVIL=1"},
                host="node2",
            )
        )
        assert "control characters" in result["error"]

    def test_scalar_value_empty_and_oversize_refused(self):
        for value in ("", "x" * 300):
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={"AITBC_DEFAULT_WALLET": value},
                    host="node2",
                )
            )
            assert "scalar value" in result["error"]

    def test_secret_names_still_refused(self):
        for name in ("TRADING_API_KEY", "AITBC_API_KEY", "SHOP_WALLET_PASSWORD"):
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="wallet",
                    subcommand=["list"],
                    env={name: "whatever"},
                    host="node2",
                )
            )
            assert "not allowed" in result["error"], name

    def test_path_valued_aitbc_var_still_needs_scratch_path(self):
        result = json.loads(
            mcp_server.read_aitbc_cli(
                group="wallet",
                subcommand=["list"],
                env={"AITBC_WALLET_DIR": "/var/lib/aitbc/wallets"},
                host="node2",
            )
        )
        assert "under /var/tmp" in result["error"]


class TestRunStdin:
    def test_stdin_forwarded_to_run_remote(self):
        captured: list[dict] = []

        def fake(host, command, timeout=60, **kwargs):
            captured.append(kwargs)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        with mock.patch.object(mcp_server, "_run_remote", fake):
            result = json.loads(
                mcp_server.run_aitbc_cli(
                    group="exchange",
                    subcommand="withdraw-eth",
                    args=["0xabc"],
                    options={"amount": "1"},
                    stdin="correct horse battery staple\n",
                    dry_run=False,
                    confirm=True,
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        assert captured[0].get("stdin_text") == "correct horse battery staple\n"
        # stdin content must not leak into the echoed command
        assert "correct horse" not in result.get("command", "")

    def test_stdin_oversize_refused(self):
        result = json.loads(
            mcp_server.run_aitbc_cli(
                group="wallet",
                subcommand="list",
                stdin="x" * (mcp_server.STDIN_MAX_LEN + 1),
                dry_run=False,
                confirm=True,
                host="node2",
            )
        )
        assert "stdin exceeds" in result["error"]

    def test_dry_run_with_stdin_does_not_execute(self):
        with mock.patch.object(mcp_server, "_run_remote") as run:
            result = json.loads(
                mcp_server.run_aitbc_cli(
                    group="wallet",
                    subcommand="list",
                    stdin="n\n",
                    dry_run=True,
                    host="node2",
                )
            )
        assert result["dry_run"] is True
        run.assert_not_called()

    def test_local_run_remote_passes_input(self):
        server = _isolated_server()
        run = mock.Mock(return_value=_completed())
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "aitbc wallet list", stdin_text="yes\n")
        assert run.call_args.kwargs.get("input") == "yes\n"

    def test_ssh_run_remote_passes_input(self):
        server = _isolated_server()
        run = mock.Mock(return_value=_completed())
        with (
            mock.patch.object(server, "_is_local_host", return_value=False),
            mock.patch.object(server, "_ssh_opts", return_value=[]),
            mock.patch.object(server, "_role_for_host", return_value="shop"),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("node2", "aitbc wallet list", stdin_text="yes\n")
        assert run.call_args.kwargs.get("input") == "yes\n"

    def test_no_stdin_keeps_devnull(self):
        server = _isolated_server()
        run = mock.Mock(return_value=_completed())
        with (
            mock.patch.object(server, "_is_local_host", return_value=True),
            mock.patch.object(server.subprocess, "run", run),
        ):
            server._run_remote("localhost", "aitbc wallet list")
        import subprocess as sp

        assert run.call_args.kwargs.get("stdin") == sp.DEVNULL
        assert "input" not in run.call_args.kwargs


class TestScratchFileTool:
    def _fake_remote(self, captured):
        def fake(host, command, timeout=60, **kwargs):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        return fake

    def test_path_outside_scratch_refused(self):
        for bad in ("/etc/passwd", "/var/tmp/../etc/x", "/var/lib/aitbc/wallets/default.json", "relative/x", "/var/tmpx/y"):
            result = json.loads(mcp_server.aitbc_scratch_file(action="read", path=bad, host="node2"))
            assert "under" in result["error"] or "/var/tmp" in result["error"], bad

    def test_write_uses_base64_and_mkdir(self):
        captured: list[str] = []
        with mock.patch.object(aitbc_mcp_scratch_tools, "_run_remote", self._fake_remote(captured)):
            result = json.loads(
                mcp_server.aitbc_scratch_file(
                    action="write",
                    path="/var/tmp/s76/quote.json",
                    content='{"price": "1.5"}',
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        cmd = captured[0]
        assert "mkdir -p /var/tmp/s76" in cmd
        assert "base64 -d" in cmd
        assert base64.b64encode(b'{"price": "1.5"}').decode() in cmd
        # content must not appear raw in the shell command
        assert '"price"' not in cmd

    def test_write_requires_content_and_size_cap(self):
        result = json.loads(mcp_server.aitbc_scratch_file(action="write", path="/var/tmp/x", host="node2"))
        assert "content is required" in result["error"]
        result = json.loads(
            mcp_server.aitbc_scratch_file(
                action="write",
                path="/var/tmp/x",
                content="x" * (aitbc_mcp_scratch_tools.SCRATCH_WRITE_MAX_BYTES + 1),
                host="node2",
            )
        )
        assert "exceeds" in result["error"]

    def test_read_parses_size_and_truncates(self):
        def fake(host, command, timeout=60, **kwargs):
            return {
                "host": host,
                "command": command,
                "returncode": 0,
                "stdout": f"{aitbc_mcp_scratch_tools.SCRATCH_READ_MAX_BYTES + 5}\n" + "a" * 10,
                "stderr": "",
            }

        with mock.patch.object(aitbc_mcp_scratch_tools, "_run_remote", fake):
            result = json.loads(mcp_server.aitbc_scratch_file(action="read", path="/var/tmp/big.bin", host="node2"))
        assert result["size_bytes"] == aitbc_mcp_scratch_tools.SCRATCH_READ_MAX_BYTES + 5
        assert result["truncated"] is True
        assert result["stdout"] == "a" * 10

    def test_delete_and_list_commands(self):
        captured: list[str] = []
        with mock.patch.object(aitbc_mcp_scratch_tools, "_run_remote", self._fake_remote(captured)):
            json.loads(mcp_server.aitbc_scratch_file(action="delete", path="/var/tmp/s/x", host="node2"))
            json.loads(mcp_server.aitbc_scratch_file(action="list", path="/var/tmp/s", host="node2"))
        assert "rm -f -- /var/tmp/s/x" in captured[0]
        assert "ls -1A -- /var/tmp/s" in captured[1]

    def test_scratch_root_itself_allowed_for_list(self):
        captured: list[str] = []
        with mock.patch.object(aitbc_mcp_scratch_tools, "_run_remote", self._fake_remote(captured)):
            result = json.loads(mcp_server.aitbc_scratch_file(action="list", path="/var/tmp", host="node2"))
        assert result["returncode"] == 0
        assert "ls -1A -- /var/tmp" in captured[0]
