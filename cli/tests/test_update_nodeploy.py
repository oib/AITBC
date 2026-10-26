"""CLI-UPDATE-NODEPLOY-1: --no-deploy must not touch the worktree (no pull)."""

import subprocess
from click.testing import CliRunner


def test_no_deploy_never_pulls(monkeypatch, tmp_path):
    """Record subprocess calls; mutation (pull path) makes pull appear."""
    import aitbc_cli.commands.update as up

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(up, "_short_sha", lambda *a, **kw: "abc1234")
    monkeypatch.setattr(up, "_ahead_behind", lambda *a, **kw: (0, 0))
    monkeypatch.setattr(up, "REPO_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()

    runner = CliRunner()
    runner.invoke(up.update, ["--no-deploy"], obj={"output_format": "plain"})
    assert not any("pull" in c for c in calls), f"pull ran under --no-deploy: {calls}"


def test_no_deploy_still_reports(monkeypatch, tmp_path):
    """The flag still fetches + reports (the _check path)."""
    import aitbc_cli.commands.update as up

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(up, "_short_sha", lambda *a, **kw: "abc1234")
    monkeypatch.setattr(up, "_ahead_behind", lambda *a, **kw: (0, 0))
    monkeypatch.setattr(up, "REPO_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()

    runner = CliRunner()
    runner.invoke(up.update, ["--no-deploy"], obj={"output_format": "plain"})
    assert any("fetch" in c for c in calls)


def test_no_deploy_help_text_is_fetch_and_report():
    """Pin the corrected help string — mutation restores 'fast-forward'."""
    import aitbc_cli.commands.update as up

    result = CliRunner().invoke(up.update, ["--help"])
    assert result.exit_code == 0
    flat = " ".join(result.output.split())
    assert "Fetch and report only; do not pull or run update.sh" in flat
    assert "fast-forward only" not in flat
