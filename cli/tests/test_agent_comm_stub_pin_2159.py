"""#2159 — pin the exit code of the unimplemented agent-comm stubs.

#2152 turned ``collaborate`` / ``reputation`` / ``monitor`` from a silent exit-0
"not available" message into ``abort()``; nothing pinned it, so a revert survived
the suite. Each stub must exit non-zero, say "not implemented", and never claim
success on stdout (table and json output both).
"""

from __future__ import annotations

import pytest
from aitbc_cli.commands.agent_comm import agent_comm
from aitbc_cli.utils.error_handling import CLIError
from click.testing import CliRunner

STUBS = [
    ("collaborate", ["collaborate", "--agent-ids", "a1", "--agent-ids", "a2", "--collaboration-type", "pool"]),
    ("reputation", ["reputation", "--agent-id", "a1", "--interaction-result", "success"]),
    ("monitor", ["monitor"]),
]


def _run(args, fmt):
    return CliRunner().invoke(agent_comm, args, obj={"output_format": fmt})


@pytest.mark.parametrize("fmt", ["table", "json"])
@pytest.mark.parametrize(("name", "args"), STUBS, ids=[s[0] for s in STUBS])
def test_stub_exits_non_zero_with_not_implemented(name, args, fmt):
    result = _run(args, fmt)
    assert result.exit_code != 0, f"{name} must not exit 0"
    assert isinstance(result.exception, CLIError), f"{name} must abort via CLIError"
    assert "not implemented" in result.output.lower()


@pytest.mark.parametrize(("name", "args"), STUBS, ids=[s[0] for s in STUBS])
def test_stub_never_reports_the_old_silent_success(name, args):
    """The pre-#2152 behaviour printed 'not available' and exited 0."""
    result = _run(args, "table")
    assert "not available via the coordinator api" not in result.output.lower()
