"""#2587: ``aitbc update --format json`` must keep stdout a single document.

``git pull`` prints its diffstat and ``update.sh`` prints progress on
stdout; with inherited descriptors they preceded the JSON report and broke
``aitbc update --format json | jq``. Machine-readable modes now pass
``stdout=sys.stderr`` to both children so their progress lands on stderr.
"""

import json
import subprocess
import sys

from click.testing import CliRunner


def _setup(monkeypatch, tmp_path, output_format):
    """Point update.py at a scratch repo with a stub update.sh and record,
    per child call, whether stdout= was sys.stderr (evaluated under the
    same patched sys.stderr the command saw)."""
    import aitbc_cli.commands.update as up

    calls = []

    def fake_run(cmd, **kwargs):
        stdout = kwargs.get("stdout")
        calls.append((cmd, "stderr" if stdout is sys.stderr else ("INHERITED" if stdout is None else stdout)))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    (tmp_path / ".git").mkdir()
    script = tmp_path / "scripts" / "deployment" / "update.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\necho stub\n")
    script.chmod(0o755)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(up, "_short_sha", lambda *a, **kw: "abc1234")
    monkeypatch.setattr(up, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(up, "UPDATE_SCRIPT", script)

    runner = CliRunner()
    result = runner.invoke(up.update, ["--format", output_format], obj={"output_format": output_format})
    return result, calls


def _is_child(cmd):
    return cmd[0] == "bash" or (cmd[0] == "git" and "pull" in cmd)


def test_json_mode_children_write_to_stderr(monkeypatch, tmp_path):
    result, calls = _setup(monkeypatch, tmp_path, "json")
    assert result.exit_code == 0
    doc = json.loads(result.output)
    assert doc == {
        "before": "abc1234",
        "after": "abc1234",
        "remote": "origin",
        "branch": "main",
        "deployed": True,
    }
    children = [stdout for cmd, stdout in calls if _is_child(cmd)]
    assert children == ["stderr", "stderr"]


def test_table_mode_children_keep_inherited_stdout(monkeypatch, tmp_path):
    result, calls = _setup(monkeypatch, tmp_path, "table")
    assert result.exit_code == 0
    children = [stdout for cmd, stdout in calls if _is_child(cmd)]
    assert children == ["INHERITED", "INHERITED"]


def test_yaml_mode_children_write_to_stderr(monkeypatch, tmp_path):
    result, calls = _setup(monkeypatch, tmp_path, "yaml")
    assert result.exit_code == 0
    children = [stdout for cmd, stdout in calls if _is_child(cmd)]
    assert children == ["stderr", "stderr"]
