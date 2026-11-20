"""#2291: opt-in market GPU registration from the miner."""

from unittest.mock import MagicMock, patch

import production_miner
from aitbc.exceptions import NetworkError

_GPU = {"name": "RTX 4060 Ti", "memory_total": 16384}


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("MINER_REGISTER_GPU", raising=False)
    with patch("production_miner.AITBCHTTPClient") as c:
        assert production_miner.register_market_gpu() is None
    c.assert_not_called()


def test_registers_when_enabled(monkeypatch):
    monkeypatch.setenv("MINER_REGISTER_GPU", "1")
    monkeypatch.setenv("MINER_GPU_RESOURCE_ID", "node2-rtx4060ti")
    client = MagicMock()
    client.post.return_value = {"gpu_id": "gpu_ab12"}
    with (
        patch("production_miner.get_gpu_info", return_value=_GPU),
        patch("production_miner.AITBCHTTPClient", return_value=client),
    ):
        assert production_miner.register_market_gpu() == "gpu_ab12"
    path, kwargs = client.post.call_args.args[0], client.post.call_args.kwargs
    assert path == "/v1/market/gpu/register"
    assert kwargs["json"]["gpu"]["name"] == "RTX 4060 Ti"
    assert kwargs["json"]["gpu"]["memory_gb"] == 16
    assert kwargs["json"]["gpu"]["resource_id"] == "node2-rtx4060ti"


def test_no_gpu_skips(monkeypatch):
    monkeypatch.setenv("MINER_REGISTER_GPU", "1")
    with patch("production_miner.get_gpu_info", return_value=None), patch("production_miner.AITBCHTTPClient") as c:
        assert production_miner.register_market_gpu() is None
    c.assert_not_called()


def test_network_error_is_non_fatal(monkeypatch):
    monkeypatch.setenv("MINER_REGISTER_GPU", "1")
    client = MagicMock()
    client.post.side_effect = NetworkError("down")
    with (
        patch("production_miner.get_gpu_info", return_value=_GPU),
        patch("production_miner.AITBCHTTPClient", return_value=client),
    ):
        assert production_miner.register_market_gpu() is None
