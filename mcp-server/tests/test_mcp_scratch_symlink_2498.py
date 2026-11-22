"""#2498: realpath enforcement for scratch files and CLI cwd/env paths.

The lexical ``/var/tmp`` check let a symlink inside the root redirect
scratch reads/writes/deletes and remote ``cd``/env paths outside it — and
the MCP tools run as root on the node. The fix resolves realpaths on the
target and refuses anything leaving the resolved scratch root.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aitbc_mcp_server as mcp_server  # noqa: E402
import aitbc_mcp_scratch_tools  # noqa: E402,F401  (registers aitbc_scratch_file)


def _run_snippet(snippet: str, *args: str, stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", snippet, *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture()
def scratch_link(tmp_path):
    """A symlink under /var/tmp pointing outside the scratch root."""
    link = Path("/var/tmp") / f"aitbc2498-link-{os.getpid()}"
    link.symlink_to(tmp_path)
    yield link
    link.unlink(missing_ok=True)


@pytest.fixture()
def scratch_dir():
    """A real directory under /var/tmp for positive-path checks."""
    d = Path("/var/tmp") / f"aitbc2498-real-{os.getpid()}"
    d.mkdir(exist_ok=True)
    yield d
    for child in d.iterdir():
        child.unlink()
    d.rmdir()


class TestScratchSnippetRealpath:
    def test_write_refuses_symlink_escape(self, scratch_link, tmp_path):
        target = scratch_link / "evil.txt"
        res = _run_snippet(
            aitbc_mcp_scratch_tools._PY_WRITE,
            str(target),
            stdin_text=base64.b64encode(b"pwned").decode(),
        )
        assert res.returncode == 3
        assert "escapes" in res.stderr
        assert not (tmp_path / "evil.txt").exists()

    def test_write_allows_real_scratch_dir(self, scratch_dir):
        target = scratch_dir / "ok.txt"
        res = _run_snippet(
            aitbc_mcp_scratch_tools._PY_WRITE,
            str(target),
            stdin_text=base64.b64encode(b"fine").decode(),
        )
        assert res.returncode == 0
        assert target.read_bytes() == b"fine"

    def test_read_refuses_symlink_escape(self, scratch_link, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("outside")
        res = _run_snippet(aitbc_mcp_scratch_tools._PY_READ, str(scratch_link / "secret.txt"))
        assert res.returncode == 3
        assert "outside" not in res.stdout

    def test_delete_refuses_symlinked_parent(self, scratch_link, tmp_path):
        victim = tmp_path / "victim.txt"
        victim.write_text("keep")
        res = _run_snippet(aitbc_mcp_scratch_tools._PY_DELETE, str(scratch_link / "victim.txt"))
        assert res.returncode == 3
        assert victim.exists()

    def test_delete_unlinks_symlink_itself_not_target(self, scratch_dir, tmp_path):
        """Deleting a symlink must remove the link, never the resolved target."""
        real = tmp_path / "real.txt"
        real.write_text("keep")
        link = scratch_dir / "link.txt"
        link.symlink_to(real)
        res = _run_snippet(aitbc_mcp_scratch_tools._PY_DELETE, str(link))
        assert res.returncode == 0
        assert not link.exists() and real.exists()

    def test_list_refuses_symlink_escape(self, scratch_link):
        res = _run_snippet(aitbc_mcp_scratch_tools._PY_LIST, str(scratch_link))
        assert res.returncode == 3

    def test_list_allows_real_scratch_dir(self, scratch_dir):
        (scratch_dir / "a.txt").write_text("x")
        res = _run_snippet(aitbc_mcp_scratch_tools._PY_LIST, str(scratch_dir))
        assert res.returncode == 0
        assert "a.txt" in res.stdout


class TestScratchToolCommandsCarryGuard:
    def _capture(self):
        captured: list[str] = []

        def fake(host, command, timeout=60, **kwargs):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "0\n", "stderr": ""}

        return captured, mock.patch.object(aitbc_mcp_scratch_tools, "_run_remote", fake)

    def test_every_action_uses_realpath_guarded_python(self):
        captured, patcher = self._capture()
        with patcher:
            for action, kwargs in (
                ("write", {"content": "x"}),
                ("read", {}),
                ("delete", {}),
                ("list", {}),
            ):
                json.loads(mcp_server.aitbc_scratch_file(action=action, path="/var/tmp/s/x", host="node2", **kwargs))
        assert len(captured) == 4
        for cmd in captured:
            assert cmd.startswith("python3 -c ")
            assert "realpath" in cmd


class TestCliCwdEnvRealpath:
    def _capture_remote(self):
        captured: list[str] = []

        def fake(host, command, timeout=60, **kwargs):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        return captured, mock.patch.object(mcp_server, "_run_remote", fake)

    def test_ssh_mode_prepends_realpath_guard(self):
        captured, patcher = self._capture_remote()
        with patcher:
            result = json.loads(
                mcp_server.read_aitbc_cli(
                    group="ai",
                    subcommand=["jobs"],
                    env={"AITBC_DATA_DIR": "/var/tmp/s/data"},
                    cwd="/var/tmp/s",
                    host="node2",
                )
            )
        assert result["returncode"] == 0
        cmd = captured[0]
        assert cmd.startswith("python3 -c ")
        assert "realpath" in cmd
        assert "/var/tmp/s/data" in cmd and "/var/tmp/s" in cmd
        assert "&& cd /var/tmp/s" in cmd or "cd /var/tmp/s &&" in cmd

    def test_scalar_env_values_skip_the_guard(self):
        captured, patcher = self._capture_remote()
        with patcher:
            json.loads(
                mcp_server.read_aitbc_cli(
                    group="ai",
                    subcommand=["jobs"],
                    env={"SHOP_WALLET_ADDRESS": "0x" + "ab" * 20},
                    host="node2",
                )
            )
        assert "realpath" not in captured[0]

    def test_no_paths_means_no_guard(self):
        captured, patcher = self._capture_remote()
        with patcher:
            json.loads(mcp_server.read_aitbc_cli(group="ai", subcommand=["jobs"], host="node2"))
        assert "realpath" not in captured[0]

    def test_local_mode_refuses_symlinked_cwd(self, scratch_link):
        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=True),
            mock.patch.object(mcp_server, "_run_remote") as run_remote,
        ):
            result = json.loads(
                mcp_server.read_aitbc_cli(group="ai", subcommand=["jobs"], cwd=str(scratch_link), host="localhost")
            )
        assert result["ok"] is False
        assert "escapes" in result["error"] or "outside" in result["error"]
        run_remote.assert_not_called()

    def test_local_mode_allows_real_scratch_cwd(self, scratch_dir):
        captured: list[str] = []

        def fake(host, command, timeout=60, **kwargs):
            captured.append(command)
            return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

        with (
            mock.patch.object(mcp_server, "_is_local_host", return_value=True),
            mock.patch.object(mcp_server, "_run_remote", fake),
        ):
            result = json.loads(
                mcp_server.read_aitbc_cli(group="ai", subcommand=["jobs"], cwd=str(scratch_dir), host="localhost")
            )
        assert result["returncode"] == 0
        # local mode validates in-process: no remote pre-flight prefix
        assert not captured[0].startswith("python3 -c ")
