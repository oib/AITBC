"""Pins for CLI-TX-PENDING-UNITS-1 (#2197).

``aitbc transactions pending`` printed raw compute-units with an ``AIT``
suffix (``TRANSFER 108000 AIT`` was really 0.003 AIT), and
``aitbc transactions status`` on a mempool tx returned a bare 404 instead of
reporting ``pending``.
"""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

from aitbc_cli.commands.transactions import transactions
from aitbc_cli.utils.http_client import NetworkError


def _runner():
    return CliRunner()


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.models.Response()
    resp.status_code = status
    resp.url = "http://node.test/rpc/transaction/0xabc"
    return requests.HTTPError(f"{status} Client Error", response=resp)


def _network_error(status: int) -> NetworkError:
    err = NetworkError(f"GET request failed: {_http_error(status)}")
    err.__cause__ = _http_error(status)
    return err


def _tx_hash(tx: dict) -> str:
    """Same canonicalization as aitbc_chain.mempool_common.compute_tx_hash."""
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    return f"0x{hashlib.sha256(canonical).hexdigest()}"


PENDING_TX = {
    "amount": 180000,  # 0.005 AIT at 36_000_000 units/AIT
    "chain_id": "bc-2",
    "fee": 360000,
    "from": "0x08aB801150eF3496344cFA78fe025c3B48Caf435",
    "nonce": 67,
    "payload": {"amount": 180000, "to": "0xd902F0831C81F150B2249Ae570fd05b3dCDFbbaF"},
    "signature": "0xsig",
    "to": "0xd902F0831C81F150B2249Ae570fd05b3dCDFbbaF",
    "type": "TRANSFER",
    "value": 180000,
}


def _client(get_side_effect):
    client = MagicMock()
    client.get.side_effect = get_side_effect
    return client


class TestPendingUnitsDisplay:
    def test_pending_shows_ait_not_raw_units(self):
        """180000 units must render as 0.005 AIT, never '180000 AIT'."""
        def get(path, **kw):
            assert path == "/rpc/pending"
            return {"transactions": [PENDING_TX], "count": 1}

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["pending", "--rpc-url", "http://node.test"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        assert "0.005 AIT" in result.output
        assert "180000 AIT" not in result.output

    def test_pending_json_output_unchanged(self):
        """JSON mode keeps raw units — machine consumers rely on it."""
        def get(path, **kw):
            return {"transactions": [PENDING_TX], "count": 1}

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["pending", "--rpc-url", "http://node.test"],
                obj={"output_format": "json"},
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data[0]["amount"] == 180000


class TestStatusPendingLookup:
    TX_HASH = _tx_hash(PENDING_TX)

    def test_status_reports_pending_for_mempool_tx(self):
        """404 on /rpc/transaction + hash match in /rpc/pending -> pending."""
        calls = []

        def get(path, **kw):
            calls.append(path)
            if path == f"/rpc/transaction/{self.TX_HASH}":
                raise _network_error(404)
            if path == "/rpc/pending":
                return {"transactions": [PENDING_TX], "count": 1}
            raise AssertionError(f"unexpected path {path}")

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["status", "--tx-hash", self.TX_HASH, "--rpc-url", "http://node.test"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        assert '"status": "pending"' in result.output
        assert f'"tx_hash": "{self.TX_HASH}"' in result.output
        assert "/rpc/pending" in calls

    def test_status_404_without_mempool_match_aborts_not_found(self):
        other_tx = dict(PENDING_TX, nonce=999)

        def get(path, **kw):
            if path.startswith("/rpc/transaction/"):
                raise _network_error(404)
            if path == "/rpc/pending":
                return {"transactions": [other_tx], "count": 1}
            raise AssertionError(f"unexpected path {path}")

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["status", "--tx-hash", self.TX_HASH, "--rpc-url", "http://node.test"],
                obj={"output_format": "table"},
            )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
        assert "mempool" in result.output.lower()

    def test_status_pending_lookup_failure_still_reports_not_found(self):
        """If /rpc/pending itself fails, the original 404 stands."""

        def get(path, **kw):
            if path.startswith("/rpc/transaction/"):
                raise _network_error(404)
            if path == "/rpc/pending":
                raise _network_error(500)
            raise AssertionError(f"unexpected path {path}")

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["status", "--tx-hash", self.TX_HASH, "--rpc-url", "http://node.test"],
                obj={"output_format": "table"},
            )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_status_confirmed_path_unchanged(self):
        """A sealed tx still returns the node's status body verbatim and
        never touches /rpc/pending."""
        body = {"status": "confirmed", "block_height": 30731, "tx_hash": "0xsealed"}
        calls = []

        def get(path, **kw):
            calls.append(path)
            assert path.startswith("/rpc/transaction/")
            return body

        with patch(
            "aitbc_cli.commands.transactions.AITBCHTTPClient",
            return_value=_client(get),
        ):
            result = _runner().invoke(
                transactions,
                ["status", "--tx-hash", "0xsealed", "--rpc-url", "http://node.test"],
                obj={"output_format": "table"},
            )
        assert result.exit_code == 0, result.output
        assert '"status": "confirmed"' in result.output
        assert "/rpc/pending" not in calls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
