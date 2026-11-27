"""#3082 (AUDIT-PERIMETER-RESIDUAL-1 / M-2b): wallet export/backup destinations
are bounded to a backup root.

``aitbc wallet export``/``backup`` write key material to a caller-chosen
``--destination``; through the MCP layer ``confirm=true`` is
model-controlled, so arbitrary-path write/arbitrary-overwrite was gated only
by the model's own confirmation. ``_run_aitbc_cli`` — the one choke point
the generated wrappers and the generic ``run_aitbc_cli`` share — now requires
an absolute path under ``AITBC_MCP_WALLET_BACKUP_ROOT`` (default
``/var/backups/aitbc/wallets``), refuses existing targets, and injects a
timestamped default inside the root when ``--destination`` is omitted.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aitbc_mcp_server as mcp_server  # noqa: E402


@pytest.fixture()
def backup_root(tmp_path, monkeypatch):
    root = tmp_path / "wallet-backups"
    monkeypatch.setattr(mcp_server, "WALLET_BACKUP_ROOT", str(root))
    return root


def _remote_spy():
    return mock.Mock(return_value={"host": "hub", "command": "", "returncode": 0, "stdout": "{}", "stderr": ""})


class TestPathValidation:
    @pytest.mark.parametrize(
        "dest",
        [
            "relative/path.json",
            "wallet_export.json",
            "/etc/aitbc/evil.json",
            "/var/backups/aitbc/wallets/../../etc/evil.json",
            "/var/backups/aitbc/wallets",  # the root itself is not a file target
        ],
    )
    def test_refuses_outside_or_relative(self, dest):
        # WALLET_BACKUP_ROOT default is /var/backups/aitbc/wallets
        assert mcp_server._wallet_backup_path_error(dest) is not None

    def test_accepts_path_under_root(self):
        assert mcp_server._wallet_backup_path_error("/var/backups/aitbc/wallets/genesis-export.json") is None


class TestDestinationExtraction:
    def test_option_map_and_args_sources(self):
        dests = mcp_server._wallet_export_destinations(
            ["--destination=/etc/sneaky"], {"destination": "/var/backups/aitbc/wallets/a.json"}
        )
        assert dests == ["/var/backups/aitbc/wallets/a.json", "/etc/sneaky"]

    def test_split_flag_form_in_args(self):
        dests = mcp_server._wallet_export_destinations(["--destination", "/etc/sneaky"], {})
        assert dests == ["/etc/sneaky"]


class TestRunRefusals:
    def test_export_destination_outside_root_refused(self):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = mcp_server._run_aitbc_cli("hub", "wallet", ["export"], None, {"destination": "/etc/aitbc/stolen.json"})
        assert "under" in out["error"]
        spy.assert_not_called()

    def test_backup_destination_outside_root_refused(self):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = mcp_server._run_aitbc_cli(
                "hub", "wallet", ["backup"], None, {"name": "genesis", "destination": "/root/.ssh/authorized_keys"}
            )
        assert "under" in out["error"]
        spy.assert_not_called()

    def test_destination_smuggled_via_args_refused(self):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = mcp_server._run_aitbc_cli("hub", "wallet", ["export"], ["--destination=/etc/evil.json"], {})
        assert "under" in out["error"]
        spy.assert_not_called()

    def test_existing_destination_refused_local(self, backup_root):
        existing = backup_root / "genesis-export.json"
        backup_root.mkdir(parents=True)
        existing.write_text("{}")
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = mcp_server._run_aitbc_cli(
                "localhost",
                "wallet",
                ["export"],
                None,
                {"destination": str(existing)},
                group_options={"wallet-name": "genesis"},
            )
        assert "already exists" in out["error"] or "refused" in out["error"]
        spy.assert_not_called()


class TestAllowedPaths:
    def test_explicit_destination_under_root_reaches_remote_with_guard(self, backup_root):
        dest = backup_root / "genesis-export.json"
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            mcp_server._run_aitbc_cli(
                "hub",
                "wallet",
                ["export"],
                None,
                {"destination": str(dest)},
                group_options={"wallet-name": "genesis"},
            )
        spy.assert_called_once()
        command = spy.call_args[0][1]
        assert f"--destination={dest}" in command
        # remote realpath/existence pre-flight precedes the aitbc command
        assert command.startswith("python3 -c ")
        assert " && " in command
        assert "aitbc" in command.split("&&", 1)[1]

    def test_missing_destination_injected_under_root(self, backup_root):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            mcp_server._run_aitbc_cli(
                "hub",
                "wallet",
                ["export"],
                None,
                {},
                group_options={"wallet-name": "genesis"},
            )
        spy.assert_called_once()
        command = spy.call_args[0][1]
        assert f"--destination={backup_root}/genesis-export-" in command
        assert command.endswith(".json") or ".json" in command

    def test_backup_missing_destination_uses_name(self, backup_root):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            mcp_server._run_aitbc_cli("hub", "wallet", ["backup"], None, {"name": "shop"})
        spy.assert_called_once()
        command = spy.call_args[0][1]
        assert f"--destination={backup_root}/shop-backup-" in command

    def test_non_wallet_commands_unaffected(self, backup_root):
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            mcp_server._run_aitbc_cli("hub", "wallet", ["balance"], ["genesis"], {"destination": "/etc/x"})
        spy.assert_called_once()
        command = spy.call_args[0][1]
        assert not command.startswith("python3 -c ")

    def test_local_mode_existing_destination_refused_without_remote(self, backup_root):
        dest = backup_root / "taken.json"
        backup_root.mkdir(parents=True)
        dest.write_text("{}")
        spy = _remote_spy()
        with mock.patch.object(mcp_server, "_run_remote", spy):
            out = mcp_server._run_aitbc_cli("localhost", "wallet", ["export"], None, {"destination": str(dest)})
        assert "refused" in out["error"]
        spy.assert_not_called()
