"""Pins for AUDIT-CLI-EXAMPLES-1 (#2602).

The example scripts under ``cli/examples/`` are user-facing starting points:
the API key must come from the environment (not a literal ``${...}``
placeholder), the mock miner must not claim earnings or GPU figures it never
measured, the wallet demo must reject non-positive amounts and never silently
replace a corrupt ledger, and printed follow-up commands must point at real
paths.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _load_example(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "module_name,env_var",
    [
        ("miner", "MINER_API_KEY"),
        ("client", "CLIENT_API_KEY"),
        ("client_enhanced", "CLIENT_API_KEY"),
    ],
)
def test_api_key_default_reads_env(monkeypatch, module_name, env_var):
    monkeypatch.delenv(env_var, raising=False)
    module = _load_example(module_name)
    assert module.DEFAULT_API_KEY is None

    monkeypatch.setenv(env_var, "test-key-123")
    module = _load_example(module_name)
    assert module.DEFAULT_API_KEY == "test-key-123"


@pytest.mark.parametrize(
    "module_name,env_var",
    [
        ("miner", "MINER_API_KEY"),
        ("client", "CLIENT_API_KEY"),
        ("client_enhanced", "CLIENT_API_KEY"),
    ],
)
def test_main_refuses_missing_api_key(monkeypatch, module_name, env_var, capsys):
    monkeypatch.delenv(env_var, raising=False)
    module = _load_example(module_name)
    argv = {
        "miner": [f"{module_name}.py", "heartbeat"],
        "client": [f"{module_name}.py", "status", "j1"],
        "client_enhanced": [f"{module_name}.py", "status", "j1"],
    }[module_name]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert "api-key" in capsys.readouterr().err


def test_miner_heartbeat_reports_no_fabricated_gpu_metrics(monkeypatch):
    miner_mod = _load_example("miner")
    miner = miner_mod.AITBCMiner("http://localhost:1", "k", "m1")
    sent: dict[str, Any] = {}

    class _Resp:
        status_code = 200

    def _post(url, **kwargs):
        sent.update(kwargs.get("json") or {})
        return _Resp()

    monkeypatch.setattr(miner.client, "post", _post)
    assert miner.send_heartbeat() is True
    metadata = sent["metadata"]
    assert "gpu_utilization" not in metadata
    assert "gpu_memory_used" not in metadata
    assert "gpu_temperature" not in metadata
    assert metadata.get("mock") is True


def test_client_enhanced_track_command_points_at_real_path(capsys):
    module = _load_example("client_enhanced")

    class _StubClient:
        def submit_job(self, job_type, task_data, ttl):
            return "job-1"

    args = type(
        "Args",
        (),
        {
            "type": "inference",
            "file": None,
            "prompt": "hi",
            "model": None,
            "ttl": 900,
            "output": "json",
        },
    )()
    with pytest.raises(SystemExit) as exc:
        module._cmd_submit(args, _StubClient())
    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["track_command"] == "python3 cli/examples/client_enhanced.py status job-1"


def test_wallet_rejects_nonpositive_amounts(tmp_path):
    wallet_mod = _load_example("wallet")
    wallet = wallet_mod.Wallet(str(tmp_path / "w.json"))
    wallet.data["balance"] = 100.0

    assert wallet.spend(-100, "refund") is False
    assert wallet.data["balance"] == 100.0
    assert wallet.spend(0, "nothing") is False
    assert wallet.data["balance"] == 100.0

    wallet.add_earnings(-500, "j1")
    assert wallet.data["balance"] == 100.0
    assert wallet.data["transactions"] == []

    wallet.spend(float("nan"), "nan")
    assert wallet.data["balance"] == 100.0


def test_wallet_corrupt_file_is_preserved(tmp_path):
    wallet_mod = _load_example("wallet")
    wallet_file = tmp_path / "w.json"
    wallet_file.write_text('{"balance": 50.0, "transactions": [')

    with pytest.raises(SystemExit):
        wallet_mod.Wallet(str(wallet_file))

    # The damaged ledger must still be there byte-for-byte — no silent reset.
    assert wallet_file.read_text() == '{"balance": 50.0, "transactions": ['


def test_wallet_save_is_atomic_and_leaves_no_tmp(tmp_path):
    wallet_mod = _load_example("wallet")
    wallet_file = tmp_path / "w.json"
    wallet = wallet_mod.Wallet(str(wallet_file))
    wallet.add_earnings(5.0, "j1")

    assert not (tmp_path / "w.json.tmp").exists()
    reloaded = wallet_mod.Wallet(str(wallet_file))
    assert reloaded.data["balance"] == 5.0
