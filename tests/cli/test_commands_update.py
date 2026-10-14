"""Tests for the `aitbc update` command."""

import shutil
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_update_command_is_registered():
    """``update`` is a top-level command on the CLI."""
    from aitbc_cli.core.main import cli

    assert "update" in cli.commands


class TestUpdateCommand:
    """Test `aitbc update` subprocess invocations."""

    @pytest.fixture(autouse=True)
    def _fake_repo_root(self, tmp_path):
        """Satisfy the command's ``.git`` and update.sh gates on any tree.

        Every subprocess call below is mocked, so the tests only need the
        command's own ``REPO_ROOT / ".git"`` existence gate to pass — without
        it a git-less export aborts before the first (mocked) git call.
        """
        (tmp_path / ".git").mkdir()
        script = tmp_path / "scripts" / "deployment" / "update.sh"
        script.parent.mkdir(parents=True)
        script.touch()
        with patch.multiple(
            "aitbc_cli.commands.update",
            REPO_ROOT=tmp_path,
            UPDATE_SCRIPT=script,
        ):
            yield

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_update_pulls_git_and_runs_update_sh(self, mock_run, runner):
        """The command runs `git pull --ff-only origin main` then `bash update.sh`."""
        from aitbc_cli.commands.update import update

        mock_run.return_value = Mock(returncode=0, stdout="abc1234\n", stderr="")

        result = runner.invoke(update, [])

        assert result.exit_code == 0, result.output

        calls = [c.args[0] for c in mock_run.call_args_list]
        pull_calls = [c for c in calls if c[:3] == ["git", "pull", "--ff-only"]]
        bash_calls = [c for c in calls if c[0] == "bash"]
        assert pull_calls == [["git", "pull", "--ff-only", "origin", "main"]]
        assert len(bash_calls) == 1
        assert "scripts/deployment/update.sh" in bash_calls[0][1]

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_update_aborts_when_git_pull_fails(self, mock_run, runner):
        """A non-zero `git pull` stops before running update.sh."""
        from aitbc_cli.commands.update import update

        def side_effect(cmd, **kwargs):
            if cmd[:2] == ["git", "pull"]:
                return Mock(returncode=1, stdout="", stderr="")
            return Mock(returncode=0, stdout="abc1234\n", stderr="")

        mock_run.side_effect = side_effect

        result = runner.invoke(update, [])

        assert result.exit_code != 0
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert not any(c[0] == "bash" for c in calls)

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_no_deploy_skips_update_sh(self, mock_run, runner):
        """--no-deploy pulls but never runs update.sh."""
        from aitbc_cli.commands.update import update

        def side_effect(cmd, **kwargs):
            out = Mock(returncode=0, stdout="abc1234\n", stderr="")
            return out

        mock_run.side_effect = side_effect

        result = runner.invoke(update, ["--no-deploy"])

        assert result.exit_code == 0, result.output
        for call in mock_run.call_args_list:
            assert call.args[0][0] != "bash"
            assert "update.sh" not in " ".join(str(a) for a in call.args[0])

    @patch("aitbc_cli.commands.update.subprocess.run")
    def test_check_only_fetches(self, mock_run, runner):
        """--check fetches and compares; it never pulls or runs update.sh."""
        from aitbc_cli.commands.update import update

        mock_run.return_value = Mock(returncode=0, stdout="abc1234\n", stderr="")

        result = runner.invoke(update, ["--check"])

        assert result.exit_code == 0, result.output
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "fetch", "origin", "main"] in calls
        assert not any(c[:2] == ["git", "pull"] for c in calls)
        assert not any(c[0] == "bash" for c in calls)


def _git(repo, *args):
    import subprocess as sp

    return sp.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_remote_and_clone(tmp_path):
    """Create a bare remote plus a clone with one commit; return (remote, clone)."""
    import subprocess as sp

    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    clone = tmp_path / "clone"
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    sp.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True, env=env)
    sp.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True, env=env)
    (seed / "f.txt").write_text("one")
    sp.run(["git", "-C", str(seed), "add", "f.txt"], check=True, capture_output=True, env=env)
    sp.run(["git", "-C", str(seed), "commit", "-m", "one"], check=True, capture_output=True, env=env)
    sp.run(
        ["git", "-C", str(seed), "remote", "add", "origin", str(remote)],
        check=True,
        capture_output=True,
        env=env,
    )
    sp.run(
        ["git", "-C", str(seed), "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
        env=env,
    )
    sp.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True, env=env)
    return remote, seed, clone, env


class TestUpdateTempRepo:
    """Real-git tests on a throwaway repo (DEV-6)."""

    pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs the git binary")

    def _invoke(self, runner, tmp_path, argv):
        import aitbc_cli.commands.update as upd

        update_script = tmp_path / "update.sh"
        update_script.write_text("#!/bin/sh\ntouch deployed-marker\n")
        update_script.chmod(0o755)
        with (
            patch.object(upd, "REPO_ROOT", tmp_path / "clone"),
            patch.object(upd, "UPDATE_SCRIPT", update_script),
        ):
            return runner.invoke(upd.update, argv)

    def test_check_reports_behind_then_no_deploy_advances(self, runner, tmp_path):
        remote, seed, clone, env = _make_remote_and_clone(tmp_path)
        import json
        import subprocess as sp

        before = _git(clone, "rev-parse", "--short", "HEAD")
        (seed / "f.txt").write_text("two")
        sp.run(["git", "-C", str(seed), "commit", "-am", "two"], check=True, capture_output=True, env=env)
        sp.run(["git", "-C", str(seed), "push", "origin", "main"], check=True, capture_output=True, env=env)

        result = self._invoke(runner, tmp_path, ["--check", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["before"] == before
        assert payload["after"] != before
        assert payload["deployed"] is False
        assert payload["behind"] == 1
        # --check must not move HEAD
        assert _git(clone, "rev-parse", "--short", "HEAD") == before

        result = self._invoke(runner, tmp_path, ["--no-deploy", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["before"] == before
        assert payload["after"] != before
        assert payload["deployed"] is False
        assert _git(clone, "rev-parse", "--short", "HEAD") == payload["after"]
        # update.sh was not run
        assert not (tmp_path / "deployed-marker").exists()
        assert not (clone / "deployed-marker").exists()

    def test_default_runs_update_sh(self, runner, tmp_path):
        remote, seed, clone, env = _make_remote_and_clone(tmp_path)
        result = self._invoke(runner, tmp_path, [])
        assert result.exit_code == 0, result.output
        assert (clone / "deployed-marker").exists() or (tmp_path / "deployed-marker").exists()

    def test_diverged_branch_refuses(self, runner, tmp_path):
        import subprocess as sp

        remote, seed, clone, env = _make_remote_and_clone(tmp_path)
        # Local commit and a different remote commit → non-ff.
        (clone / "local.txt").write_text("local")
        sp.run(["git", "-C", str(clone), "add", "local.txt"], check=True, capture_output=True, env=env)
        sp.run(["git", "-C", str(clone), "commit", "-m", "local"], check=True, capture_output=True, env=env)
        (seed / "f.txt").write_text("three")
        sp.run(["git", "-C", str(seed), "commit", "-am", "three"], check=True, capture_output=True, env=env)
        sp.run(["git", "-C", str(seed), "push", "origin", "main"], check=True, capture_output=True, env=env)

        head = _git(clone, "rev-parse", "--short", "HEAD")
        result = self._invoke(runner, tmp_path, ["--no-deploy"])
        assert result.exit_code != 0
        assert _git(clone, "rev-parse", "--short", "HEAD") == head
