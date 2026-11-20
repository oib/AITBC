"""#2294: the miner→ollama inference timeout is env-tunable and defaults high.

The market-job path hardcoded ``timeout=180`` on the ollama client; on
CPU-only nodes a cold model load or serialized inference legitimately
exceeds that and the miner reports FAILURE, forcing an escrow sweep.
``_ollama_timeout_seconds`` reads ``MINER_OLLAMA_TIMEOUT_SECONDS`` with a
600s default — matching the agent-task executor's ollama timeout — and
falls back on garbage values.
"""

from __future__ import annotations

import miner_job_execution as mje

ENV = "MINER_OLLAMA_TIMEOUT_SECONDS"


def test_default_is_600(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert mje._ollama_timeout_seconds() == 600


def test_env_override(monkeypatch):
    monkeypatch.setenv(ENV, "900")
    assert mje._ollama_timeout_seconds() == 900


def test_zero_and_negative_clamped_to_one(monkeypatch):
    for bad in ("0", "-5"):
        monkeypatch.setenv(ENV, bad)
        assert mje._ollama_timeout_seconds() == 1


def test_garbage_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(ENV, "not-a-number")
    assert mje._ollama_timeout_seconds() == 600
