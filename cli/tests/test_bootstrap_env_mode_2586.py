"""#2586: bootstrap-env must write owner-only and both generators must emit
the CLI's real service ports, not dead ones.

- ``bootstrap-env`` created ``.env`` under the process umask (0644) around
  empty ``AITBC_API_KEY=`` slots the operator is told to fill — a
  world-readable secret on shared hosts.
- The template's ``COORDINATOR_API_URL=http://localhost:8000`` and
  ``init-platform``'s manifest endpoints (``:8000`` coordinator, ``:8001``
  wallet) point at ports nothing listens on; the CLI defaults are
  ``:8203`` (coordinator) and ``:8108`` (wallet daemon).
"""

import json
import os
import stat
from types import SimpleNamespace

from click.testing import CliRunner


def _invoke_bootstrap(monkeypatch, tmp_path, argv):
    import aitbc_cli.commands.bootstrap as bootstrap_mod

    monkeypatch.setattr(
        bootstrap_mod,
        "get_config",
        lambda: SimpleNamespace(coordinator_api_url=""),
    )
    target = tmp_path / ".env"
    result = CliRunner().invoke(
        bootstrap_mod.bootstrap_env,
        ["--output", str(target), *argv],
        obj={"output": "table"},
    )
    return result, target


def test_env_file_created_owner_only_under_umask_022(monkeypatch, tmp_path):
    old = os.umask(0o022)
    try:
        result, target = _invoke_bootstrap(monkeypatch, tmp_path, [])
    finally:
        os.umask(old)
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    body = target.read_text()
    assert "AITBC_API_KEY=" in body
    assert "COORDINATOR_API_URL=http://localhost:8203" in body
    assert "localhost:8000" not in body


def test_overwrite_tightens_preexisting_world_readable_file(monkeypatch, tmp_path):
    target = tmp_path / ".env"
    target.write_text("AITBC_API_KEY=old\n")
    target.chmod(0o644)
    result, _ = _invoke_bootstrap(monkeypatch, tmp_path, ["--overwrite"])
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_init_platform_endpoints_use_cli_default_ports(monkeypatch, tmp_path):
    import aitbc_cli.commands.platform as platform_mod

    monkeypatch.setattr(
        platform_mod,
        "get_config",
        lambda: SimpleNamespace(coordinator_api_url="", wallet_daemon_url=""),
    )
    result = CliRunner().invoke(
        platform_mod.init_platform,
        ["--name", "Test Platform", "--output", str(tmp_path)],
        obj={"output": "table"},
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "brand-manifest.json").read_text())
    assert manifest["endpoints"]["coordinator"] == "http://localhost:8203"
    assert manifest["endpoints"]["wallet"] == "http://localhost:8108"
