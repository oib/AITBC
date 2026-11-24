"""#2881: ``aitbc update --remote`` must name a configured git remote, never a URL.

Before the fix ``git fetch``/``git pull`` accepted an arbitrary repository
URL as <repository>; the fetched code then ran under ``update.sh`` —
remote-code-execution on the node. The pin asserts the command aborts
before any fetch/pull when the remote is not in ``git remote`` output.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_repo(tmp_path):
    """Scratch repo root + stub update.sh, mirroring test_commands_update.py."""
    (tmp_path / ".git").mkdir()
    script = tmp_path / "scripts" / "deployment" / "update.sh"
    script.parent.mkdir(parents=True)
    script.touch()
    return tmp_path, script


def _run_mock(remotes="origin\n"):
    """subprocess.run mock that reports a fixed remote list for `git remote`."""

    def side_effect(cmd, **kwargs):
        if cmd[:2] == ["git", "remote"]:
            return Mock(returncode=0, stdout=remotes, stderr="")
        return Mock(returncode=0, stdout="abc1234\n", stderr="")

    return side_effect


def _invoke(runner, tmp_path, script, argv):
    with patch.multiple(
        "aitbc_cli.commands.update",
        REPO_ROOT=tmp_path,
        UPDATE_SCRIPT=script,
    ):
        from aitbc_cli.commands.update import update

        return runner.invoke(update, argv)


@pytest.mark.parametrize(
    "remote",
    [
        "https://evil.example/repo.git",
        "git@evil.example:repo.git",
        "/tmp/attacker-repo",
        "../outside",
        "origin extra",
        "-evil",
    ],
)
def test_arbitrary_remote_url_is_rejected(runner, fake_repo, remote):
    """A URL/path/option-like --remote aborts before fetch or pull."""
    tmp_path, script = fake_repo
    with patch("aitbc_cli.commands.update.subprocess.run") as mock_run:
        mock_run.side_effect = _run_mock("origin\n")
        result = _invoke(runner, tmp_path, script, ["--remote", remote])

    assert result.exit_code != 0
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert not any(c[:2] in (["git", "fetch"], ["git", "pull"]) for c in calls), calls


def test_configured_remote_name_is_accepted(runner, fake_repo):
    """A name returned by `git remote` still runs the normal update path."""
    tmp_path, script = fake_repo
    with patch("aitbc_cli.commands.update.subprocess.run") as mock_run:
        mock_run.side_effect = _run_mock("origin\nmirror\n")
        result = _invoke(runner, tmp_path, script, ["--remote", "mirror"])

    assert result.exit_code == 0, result.output
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["git", "pull", "--ff-only", "mirror", "main"] in calls


@pytest.mark.parametrize("branch", ["-evil", "+refs/heads/x", "a:b", ""])
def test_option_or_refspec_branch_is_rejected(runner, fake_repo, branch):
    """--branch values that git would parse as options or refspecs abort."""
    tmp_path, script = fake_repo
    argv = ["--branch", branch] if branch else ["--branch", ""]
    with patch("aitbc_cli.commands.update.subprocess.run") as mock_run:
        mock_run.side_effect = _run_mock("origin\n")
        result = _invoke(runner, tmp_path, script, argv)

    assert result.exit_code != 0
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert not any(c[:2] in (["git", "fetch"], ["git", "pull"]) for c in calls), calls


def test_repo_with_no_remotes_rejects_default_origin(runner, fake_repo):
    """`git remote` listing nothing must not let the default 'origin' through."""
    tmp_path, script = fake_repo
    with patch("aitbc_cli.commands.update.subprocess.run") as mock_run:
        mock_run.side_effect = _run_mock("")
        result = _invoke(runner, tmp_path, script, [])

    assert result.exit_code != 0
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert not any(c[:2] in (["git", "fetch"], ["git", "pull"]) for c in calls), calls
