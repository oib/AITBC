"""CLI-FORMAT-OVERRIDE-1 (#530): leaf ``--format`` must win over group ``--output``.

The group callback always populates ``ctx.obj["output_format"]`` (default
``table``), so ``ctx.obj.get("output_format", format)`` resolves the leaf
flag as the *fallback* and silently discards ``--format json`` on every
command that uses that idiom. ``resolve_output_format`` defines the correct
precedence: command-level flag first, then the global ``--output``, then
``table``.

These tests exercise ``trade health`` (the command the issue was verified
on) with a mocked trading client.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tests.fixtures.cli_mocks import make_cli_obj, parse_json_output


def _invoke_health(runner, args, obj):
    from aitbc_cli.commands.trade import trade

    client = MagicMock()
    client.get.return_value = {"status": "healthy", "chain_id": "ait-mainnet"}
    with patch("aitbc_cli.commands.trade._get_client", return_value=client):
        return runner.invoke(trade, ["health", "--chain-id", "ait-mainnet", *args], obj=obj)


class TestLeafFormatWins:
    def test_leaf_json_beats_group_table(self, runner):
        """``--format json`` must produce JSON even when the group default is table."""
        result = _invoke_health(runner, ["--format", "json"], make_cli_obj(output_format="table", output="table"))
        assert result.exit_code == 0, result.output
        payload = parse_json_output(result.output)
        assert payload["status"] == "healthy"

    def test_leaf_table_beats_group_json(self, runner):
        """``--format table`` must produce a table even when the group asks for json."""
        result = _invoke_health(runner, ["--format", "table"], make_cli_obj(output_format="json", output="json"))
        assert result.exit_code == 0, result.output
        assert json.dumps("healthy") not in result.output
        # Table renderer draws grid borders; JSON would start with '{'.
        assert not result.output.lstrip().startswith("{")

    def test_group_json_used_when_leaf_absent(self, runner):
        """With no leaf flag, the group ``--output`` still applies."""
        result = _invoke_health(runner, [], make_cli_obj(output_format="json", output="json"))
        assert result.exit_code == 0, result.output
        payload = parse_json_output(result.output)
        assert payload["status"] == "healthy"
