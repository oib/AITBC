"""#3082 (AUDIT-PERIMETER-RESIDUAL-1 / M-2a): ``aitbc system cat`` must mask
secret-shaped ``Environment=`` values.

``systemctl cat`` prints inline unit/drop-in Environment assignments
verbatim; unit files on the fleet carry KEY/SECRET/TOKEN-shaped values that
used to flow unredacted into agent transcripts via the MCP ``system cat``
tool. The mask reuses the same ``_field_name_denied`` rules ``system
env-set``/``env-names`` enforce.
"""

from __future__ import annotations

import subprocess
from unittest import mock

from click.testing import CliRunner

import aitbc_cli.commands.system as system_mod
from aitbc_cli.commands.system import system


UNIT_TEXT = """# /etc/systemd/system/aitbc-blockchain-node.service
[Unit]
Description=AITBC Blockchain Node

[Service]
Environment=BLOCKCHAIN_MODE=hub DATA_DIR=/var/lib/aitbc
Environment="AITBC_RPC_API_KEY=abc123secret" NODE_WALLET_ADDRESS=0xabc
EnvironmentFile=/etc/aitbc/aitbc-blockchain-node.env
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain
"""


def _cat_result(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["systemctl", "cat"], returncode=0, stdout=stdout, stderr="")


def test_redact_unit_environment_masks_secret_names():
    out = system_mod._redact_unit_environment(UNIT_TEXT)
    assert "abc123secret" not in out
    assert "AITBC_RPC_API_KEY=<redacted>" in out
    # the variable name stays visible so the unit remains diagnosable
    assert "AITBC_RPC_API_KEY=" in out
    # non-secret assignments stay visible
    assert "BLOCKCHAIN_MODE=hub" in out
    assert "DATA_DIR=/var/lib/aitbc" in out
    assert "NODE_WALLET_ADDRESS=0xabc" in out
    # EnvironmentFile= is a path, not a secret — untouched
    assert "EnvironmentFile=/etc/aitbc/aitbc-blockchain-node.env" in out


def test_redact_unit_environment_leaves_non_env_lines_alone():
    text = "[Service]\nExecStart=/bin/true --api-key=hunter2\nEnvironment=PORT=8202\n"
    out = system_mod._redact_unit_environment(text)
    # ExecStart is out of scope for this mask (documented residual); the
    # Environment line keeps its non-secret value.
    assert "--api-key=hunter2" in out
    assert "Environment=PORT=8202" in out


def test_cat_command_echoes_redacted_output():
    runner = CliRunner()
    with mock.patch.object(system_mod.subprocess, "run", return_value=_cat_result(UNIT_TEXT)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["cat", "--service", "blockchain-node"])
    assert result.exit_code == 0, result.output
    assert "abc123secret" not in result.output
    assert "<redacted>" in result.output
    assert "BLOCKCHAIN_MODE=hub" in result.output
