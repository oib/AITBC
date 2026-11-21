"""#2458: `aitbc bridge status --transfer-id` names the RPC backend that
answered — transfer rows are node-local, so the same id can read differently
on different nodes."""

from __future__ import annotations

import json
from unittest import mock

from click.testing import CliRunner

from aitbc_cli.commands.bridge import _transfers as bridge_mod
from aitbc_cli.commands.bridge._transfers import status


def test_status_names_querying_backend():
    runner = CliRunner()
    client = mock.Mock()
    client.__aenter__ = mock.AsyncMock(return_value=client)
    client.__aexit__ = mock.AsyncMock(return_value=None)
    client.get_transfer = mock.AsyncMock(return_value={"transfer_id": "0xTID", "status": "pending", "confirm_time": None})
    with mock.patch.object(bridge_mod, "_get_bridge_client", return_value=client):
        result = runner.invoke(
            status,
            obj={"output_format": "json"},
            args=["--transfer-id", "0xTID", "--rpc-url", "http://node1.example:8202/rpc"],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["rpc_url"] == "http://node1.example:8202/rpc"
    assert payload["status"] == "pending"
