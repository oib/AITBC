"""#2339 residual pins: ``_ipfs_object_size`` must work on Kubo versions that
removed ``object/stat``.

Live evidence (node2, 21 Nov): the island Kubo answers ``object/stat`` with
HTTP 200 + ``{"Type": "error", "Message": "removed, use 'ipfs dag'..."}`` —
``raise_for_status`` passes, ``CumulativeSize`` is absent, and every
daemon-held CID read as missing. ``dag/stat`` returns ``TotalSize``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from aitbc_cli.commands.ipfs import _ipfs_object_size


def _resp(payload: dict, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def _post_side_effect(mapping):
    """mapping: path-substring -> response or Exception"""

    def _post(url, **kwargs):
        for key, value in mapping.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected POST {url}")

    return _post


class TestDagStatPrimary:
    def test_dag_stat_total_size_returned(self):
        resp = _resp({"TotalSize": 26, "DagStats": []})
        with patch("aitbc_cli.commands.ipfs.requests.post", side_effect=_post_side_effect({"dag/stat": resp})):
            assert _ipfs_object_size("http://x", "QmCid") == 26

    def test_object_stat_not_called_when_dag_stat_answers(self):
        resp = _resp({"TotalSize": 7})
        calls = []

        def _post(url, **kwargs):
            calls.append(url)
            return resp

        with patch("aitbc_cli.commands.ipfs.requests.post", side_effect=_post):
            _ipfs_object_size("http://x", "QmCid")
        assert all("dag/stat" in u for u in calls)


class TestFallbackAndFailure:
    def test_error_envelope_falls_back_to_object_stat(self):
        dag_err = _resp({"Message": "removed", "Code": 0, "Type": "error"})
        obj_ok = _resp({"CumulativeSize": 42})
        with patch(
            "aitbc_cli.commands.ipfs.requests.post",
            side_effect=_post_side_effect({"dag/stat": dag_err, "object/stat": obj_ok}),
        ):
            assert _ipfs_object_size("http://x", "QmCid") == 42

    def test_both_missing_returns_none(self):
        err = _resp({"Type": "error", "Message": "not found"})
        with patch(
            "aitbc_cli.commands.ipfs.requests.post",
            side_effect=_post_side_effect({"dag/stat": err, "object/stat": err}),
        ):
            assert _ipfs_object_size("http://x", "QmMissing") is None

    def test_network_error_on_dag_still_tries_object_stat(self):
        obj_ok = _resp({"CumulativeSize": 9})
        with patch(
            "aitbc_cli.commands.ipfs.requests.post",
            side_effect=_post_side_effect({"dag/stat": requests.ConnectionError("refused"), "object/stat": obj_ok}),
        ):
            assert _ipfs_object_size("http://x", "QmCid") == 9

    def test_non_dict_json_treated_as_miss(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = ["not", "a", "dict"]
        resp.raise_for_status.return_value = None
        with patch("aitbc_cli.commands.ipfs.requests.post", return_value=resp):
            assert _ipfs_object_size("http://x", "QmCid") is None

    def test_double_json_body_parses_first_document(self):
        """Live Kubo 0.43 dag/stat emits two newline-separated JSON docs —
        response.json() raises 'Extra data', so the first doc must be parsed
        directly (node2 repro, #2339 verify)."""
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            '{"TotalSize":4,"DagStats":[{"Cid":"QmX","Size":4,"NumBlocks":1}]}\n'
            '{"UniqueBlocks":1,"TotalSize":4,"Ratio":1,"DagStats":[]}\n'
        )
        resp.json.side_effect = ValueError("Extra data")
        resp.raise_for_status.return_value = None
        with patch("aitbc_cli.commands.ipfs.requests.post", return_value=resp):
            assert _ipfs_object_size("http://x", "QmCid") == 4
