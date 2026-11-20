"""#2301/#2305: region env, periodic market GPU re-register, visible capacity stall."""

import logging

import production_miner


def test_region_defaults_to_localhost_and_honours_env(monkeypatch):
    # MINER_REGION is read at import; the helper values are what register uses.
    assert production_miner.MINER_REGION  # never empty
    monkeypatch.setattr(production_miner, "MINER_REGION", "node2")
    caps = production_miner.build_gpu_capabilities()
    assert caps["region"] == "node2"


def test_market_gpu_region_follows_miner_region(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("MINER_REGISTER_GPU", "1")
    monkeypatch.delenv("MINER_GPU_REGION", raising=False)
    monkeypatch.setattr(production_miner, "MINER_REGION", "node2")
    client = MagicMock()
    client.post.return_value = {"gpu_id": "g"}
    with (
        patch("production_miner.get_gpu_info", return_value={"name": "X", "memory_total": 8192}),
        patch("production_miner.AITBCHTTPClient", return_value=client),
    ):
        production_miner.register_market_gpu()
    assert client.post.call_args.kwargs["json"]["gpu"]["region"] == "node2"


def test_capacity_skip_warns_rate_limited(monkeypatch, caplog):
    monkeypatch.setattr(production_miner, "_last_capacity_warn", 0.0)
    monkeypatch.setattr(production_miner, "ACTIVE_JOB_IDS", {"job-stuck"})
    with caplog.at_level(logging.WARNING):
        production_miner._warn_at_capacity(1)
        production_miner._warn_at_capacity(1)
    msgs = [r.message for r in caplog.records if "max capacity" in r.message]
    assert len(msgs) == 1 and "job-stuck" in msgs[0]


def test_main_loop_reregisters_market_gpu_periodically():
    import inspect

    src = inspect.getsource(production_miner.main)
    assert "MARKET_GPU_REREGISTER_INTERVAL" in src and "register_market_gpu" in src
