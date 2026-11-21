"""#2415 pins: missing-unit honesty across system/service/health commands.

- ``system show``/``system logs`` must fail when systemd reports
  ``LoadState=not-found`` instead of printing an empty success.
- ``service harden`` must exit non-zero when a targeted unit file is
  missing (the error was previously only inside the JSON payload).
- ``health --role`` must probe only the services that role deploys
  instead of the hard-coded fleet-wide list.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _systemctl_result(stdout: str, rc: int = 0) -> MagicMock:
    result = MagicMock()
    result.returncode = rc
    result.stdout = stdout
    result.stderr = ""
    return result


class TestSystemShowMissingUnit:
    @patch("subprocess.run")
    def test_show_fails_on_not_found(self, mock_run, runner):
        # First subprocess.run is the LoadState probe; it must short-circuit
        # before the property dump runs.
        mock_run.return_value = _systemctl_result("not-found\n")

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["show", "--service", "aitbc-coordinator-api"])

        assert result.exit_code != 0
        assert "not installed" in result.output
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_show_proceeds_when_loaded(self, mock_run, runner):
        mock_run.side_effect = [
            _systemctl_result("loaded\n"),
            _systemctl_result("ActiveState=active\nLoadState=loaded\n"),
        ]

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["show", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output
        assert "ActiveState=active" in result.output

    @patch("subprocess.run")
    def test_show_fail_open_when_systemctl_cannot_answer(self, mock_run, runner):
        # No systemd on the host: the load-state probe fails, the property
        # dump is still attempted (legacy behavior preserved).
        mock_run.side_effect = [
            _systemctl_result("", rc=1),
            _systemctl_result("ActiveState=inactive\n"),
        ]

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["show", "--service", "blockchain-node"])

        assert result.exit_code == 0, result.output


class TestSystemLogsMissingUnit:
    @patch("subprocess.run")
    def test_logs_fails_on_not_found(self, mock_run, runner):
        mock_run.return_value = _systemctl_result("not-found\n")

        from aitbc_cli.commands.system import system

        result = runner.invoke(system, ["logs", "--service", "aitbc-coordinator-api", "--lines", "20"])

        assert result.exit_code != 0
        assert "not installed" in result.output
        # journalctl must never run for a missing unit.
        for call in mock_run.call_args_list:
            assert call[0][0][0] != "journalctl"


class TestServiceHardenMissingUnit:
    def test_harden_dry_run_exits_nonzero_on_missing_unit(self, runner, tmp_path):
        missing = tmp_path / "aitbc-ghost.service"
        present = tmp_path / "aitbc-wallet.service"
        present.write_text("[Service]\nExecStart=/bin/true\n")

        from aitbc_cli.commands import service as service_mod

        with (
            patch.object(service_mod, "_service_unit_path", side_effect=lambda u: str(tmp_path / u)),
            patch.object(service_mod, "_harden_unit", return_value={"changed": False}),
        ):
            result = runner.invoke(
                service_mod.service,
                ["harden", "--service", "aitbc-ghost", "--dry-run"],
            )

        assert result.exit_code == 1, result.output
        assert "unit file not found" in result.output

    def test_harden_exits_zero_when_unit_exists(self, runner, tmp_path):
        present = tmp_path / "aitbc-wallet.service"
        present.write_text("[Service]\nExecStart=/bin/true\n")

        from aitbc_cli.commands import service as service_mod

        with (
            patch.object(service_mod, "_service_unit_path", return_value=str(present)),
            patch.object(service_mod, "_harden_unit", return_value={"changed": False}),
        ):
            result = runner.invoke(
                service_mod.service,
                ["harden", "--service", "aitbc-wallet", "--dry-run"],
            )

        assert result.exit_code == 0, result.output


class TestHealthRoleFilter:
    def _probe_stub(self, monkeypatch):
        from aitbc_cli.commands import health as health_mod

        probed: list[str] = []

        def _fake_probe(service: str):
            probed.append(service)
            return {"service": service, "status": "healthy", "status_code": 200}

        monkeypatch.setattr(health_mod, "_probe_url", lambda url, timeout: {"status": "healthy"})
        # Capture which services get probed by wrapping the loop input instead:
        # patch _role_probe_services indirectly via control._role_services.
        return probed

    def test_role_shop_limits_probes(self, runner, monkeypatch):
        from aitbc_cli.commands import health as health_mod

        shop_units = [
            "aitbc-blockchain-node",
            "aitbc-blockchain-rpc",
            "aitbc-wallet",
            "aitbc-monitoring",
            "aitbc-trading",
            "aitbc-governance",
            "aitbc-market",
            "aitbc-api-gateway",
            "aitbc-blockchain-explorer",
            "aitbc-pool-hub",
            "aitbc-edge",
        ]
        monkeypatch.setattr("aitbc_cli.commands.control._role_services", lambda role: shop_units)
        monkeypatch.setattr(health_mod, "_probe_url", lambda url, timeout: {"status": "healthy", "url": url})

        result = runner.invoke(health_mod.health, ["--host", "node2.example.net", "--role", "shop", "--output", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("["):])
        services = {row["service"] for row in data}
        # Shop-deployed, probeable units only — no coordinator-api/pool-hub? pool-hub IS in
        # the shop manifest above; coordinator-api is not, so it must be absent.
        assert "coordinator-api" not in services
        assert "blockchain-rpc" in services
        assert "market" in services
        assert "explorer" in services

    def test_services_and_role_conflict_aborts(self, runner):
        from aitbc_cli.commands import health as health_mod

        result = runner.invoke(
            health_mod.health,
            ["--host", "node2.example.net", "--services", "wallet", "--role", "shop"],
        )

        assert result.exit_code != 0
        assert "cannot be combined" in result.output

    def test_no_role_keeps_full_probe_list(self, runner, monkeypatch):
        from aitbc_cli.commands import health as health_mod

        monkeypatch.setattr(health_mod, "_probe_url", lambda url, timeout: {"status": "healthy", "url": url})

        result = runner.invoke(health_mod.health, ["--host", "node2.example.net", "--output", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.index("["):])
        assert len(data) == len(health_mod.DEFAULT_SERVICE_PROBES)
