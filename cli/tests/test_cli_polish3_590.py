"""CLI-POLISH-3 (#590): CLIError must pass broad excepts once; credential
abort carries the full explanation."""

from __future__ import annotations

from click.testing import CliRunner

from aitbc_cli.commands import workflow as wf_mod
from aitbc_cli.commands.market import safe_load_credentials
from aitbc_cli.utils.error_handling import CLIError


def test_workflow_failed_start_prints_once(monkeypatch, tmp_path):
    """Inner abort inside the try must not be re-wrapped by 'Error running
    workflow' — one message, non-zero exit."""
    import types

    cfg = tmp_path / "wf.yaml"
    cfg.write_text("k: v\n")
    resp = types.SimpleNamespace(status_code=500, text="boom", json=lambda: {})
    monkeypatch.setattr(wf_mod, "get_config", lambda: object())
    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: resp)
    result = CliRunner().invoke(wf_mod.run, ["--workflow-name", "x", "--config", str(cfg)], obj={"output_format": "table"})
    assert result.exit_code != 0
    assert result.output.count("Failed to start workflow") == 1, result.output
    assert "Error running workflow" not in result.output


def test_credentials_abort_carries_full_text(monkeypatch):
    """The credential abort message holds the whole explanation in one doc."""
    import pytest

    monkeypatch.delenv("NODE_ROLE", raising=False)
    import aitbc_cli.commands.market as mk

    monkeypatch.setattr(mk, "load_island_credentials", lambda: (_ for _ in ()).throw(FileNotFoundError("creds.json")))
    with pytest.raises(CLIError) as ei:
        safe_load_credentials()
    msg = str(ei.value)
    assert "Island credentials required" in msg
    assert "Hub nodes do not need" in msg
    assert "node island join" in msg
    assert "my-chain-id" in msg
