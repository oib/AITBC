"""AUDIT-SCRIPT-RUN-EXIT-1 (#2535): ``aitbc script run`` exited 0 whatever
the script returned, had no timeout, and split ``--args`` on whitespace.
Now: non-zero script rc propagates, ``--timeout`` kills and reports,
``--args`` goes through ``shlex.split``.
"""

import subprocess

from click.testing import CliRunner

from aitbc_cli.commands.script import script


def _patch_run(monkeypatch, result=None, exc=None, calls=None):
    def fake_run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_failing_script_exit_code_propagates(monkeypatch):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 3, "out", "err"))
    result = CliRunner().invoke(script, ["run", "--script-path", "/tmp/x.sh"], obj={"output_format": "table"})
    assert result.exit_code == 3


def test_successful_script_exit_zero(monkeypatch):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "ok", ""))
    result = CliRunner().invoke(script, ["run", "--script-path", "/tmp/x.sh"], obj={"output_format": "table"})
    assert result.exit_code == 0


def test_signal_returncode_maps_to_nonzero(monkeypatch):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], -9, "", ""))
    result = CliRunner().invoke(script, ["run", "--script-path", "/tmp/x.sh"], obj={"output_format": "table"})
    assert result.exit_code == 1


def test_args_use_shlex_split(monkeypatch):
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(
        script,
        ["run", "--script-path", "/tmp/x.sh", "--args", '--msg "a b" --flag'],
        obj={"output_format": "table"},
    )
    assert result.exit_code == 0, result.output
    cmd, _ = calls[0]
    assert cmd == ["/tmp/x.sh", "--msg", "a b", "--flag"]


def test_timeout_kills_and_reports(monkeypatch):
    calls: list = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CliRunner().invoke(
        script,
        ["run", "--script-path", "/tmp/x.sh", "--timeout", "5"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "timed out" in result.output
    assert calls[0][1].get("timeout") == 5.0


def test_no_timeout_by_default(monkeypatch):
    calls: list = []
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, "", ""), calls=calls)
    result = CliRunner().invoke(script, ["run", "--script-path", "/tmp/x.sh"], obj={"output_format": "table"})
    assert result.exit_code == 0
    assert calls[0][1].get("timeout") is None
