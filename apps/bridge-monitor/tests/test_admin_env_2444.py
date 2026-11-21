"""#2444 CLI-STDERR-NOISE-1 — bridge admin env-file warning is opt-in.

``python -m bridge_monitor.admin`` (what ``aitbc bridge deposits`` shells)
used to warn ``cannot read env file /etc/aitbc/aitbc-bridge-monitor.env``
on every read on nodes that do not run the monitor. The warning now only
fires when the env file was explicitly requested (``--env-file`` or
``BRIDGE_MONITOR_ENV``); the compiled-in default missing is silent.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bridge_monitor.admin import _load_env_file  # noqa: E402


def test_env_file_quiet_when_not_explicit(tmp_path, capsys):
    """Default-path env file missing → silent on read-only admin commands."""
    _load_env_file(str(tmp_path / "absent.env"), warn_missing=False)
    assert capsys.readouterr().err == ""


def test_env_file_warns_when_explicit(tmp_path, capsys):
    """An explicitly requested but unreadable env file still warns."""
    _load_env_file(str(tmp_path / "absent.env"), warn_missing=True)
    assert "cannot read env file" in capsys.readouterr().err


def test_env_file_still_loads(tmp_path, monkeypatch):
    env = tmp_path / "monitor.env"
    env.write_text("BRIDGE_TEST_KEY_2444=hello\n")
    monkeypatch.delenv("BRIDGE_TEST_KEY_2444", raising=False)
    _load_env_file(str(env), warn_missing=False)
    assert os.environ["BRIDGE_TEST_KEY_2444"] == "hello"
