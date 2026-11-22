"""#2588 AUDIT-NODE-MONITOR-1 pins.

1. ``monitor_command`` let the broad ``except Exception`` re-catch the
   ``click.Abort`` it raises for an unknown node — printing an empty
   "Error during monitoring: " on top of the real message.
2. ``--interval`` accepted 0 → ``time.sleep(0)`` busy-poll.
3. The realtime metrics pane did ``str(list_of_rows)`` — a Python repr.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner
from rich.console import Console
from rich.table import Table

from aitbc_cli.commands.node import monitor as monitor_cmd
from aitbc_cli.commands.node.monitor import _monitor_metrics_renderable, monitor_command


def _ctx():
    return SimpleNamespace(obj={"output": "table"})


def test_unknown_node_aborts_without_empty_error(capsys):
    config = SimpleNamespace(nodes={})
    with (
        patch("aitbc_cli.commands.node.monitor.load_multichain_config", return_value=config),
        pytest.raises(click.Abort),
    ):
        monitor_command(_ctx(), "nope", realtime=False, interval=5)
    out = capsys.readouterr()
    assert "Error during monitoring" not in out.err + out.out


def test_interval_zero_rejected():
    result = CliRunner().invoke(monitor_cmd, ["--node-id", "x", "--interval", "0"])
    assert result.exit_code == 2
    assert "interval" in result.output.lower()


def test_metrics_renderable_is_table_not_list_repr():
    info = {"cpu_usage": 12.5, "memory_usage_mb": 512.0, "status": "ok"}
    renderable = _monitor_metrics_renderable(info)
    assert isinstance(renderable, Table)
    console = Console(record=True, width=100)
    console.print(renderable)
    text = console.export_text()
    assert "CPU Usage" in text and "12.5%" in text
    assert "[" not in text.split("CPU Usage")[0]  # no Python list repr
