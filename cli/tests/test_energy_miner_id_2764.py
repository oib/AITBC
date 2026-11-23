"""#2764 — `energy provider register` / `suggest --register` must send
``X-Miner-ID`` on the native rail so unbound miner keys resolve to the
profile-owning miner instead of the derived ``miner_<hash>`` (which 403s on
GPURegistry ownership).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import energy as energy_mod
from aitbc_cli.commands.energy import _native_energy_request, _resolve_miner_id, energy


class _FakeClient:
    """Captures constructor kwargs; answers every call with {}."""

    instances: list[_FakeClient] = []

    def __init__(self, base_url=None, timeout=None, **kwargs):
        self.base_url = base_url
        self.timeout = timeout
        self.kwargs = kwargs
        self.headers = dict(kwargs.get("headers") or {})
        if kwargs.get("api_key"):
            self.headers["X-API-Key"] = kwargs["api_key"]
        _FakeClient.instances.append(self)

    def post(self, path, json=None, **_kw):
        self.last_post = (path, json)
        return {"status": "registered"}

    def get(self, path, params=None, **_kw):
        self.last_get = (path, params)
        return {}


@pytest.fixture(autouse=True)
def _fake_transport(monkeypatch):
    _FakeClient.instances = []
    monkeypatch.setattr(energy_mod, "AITBCHTTPClient", _FakeClient)
    monkeypatch.setattr(energy_mod, "auth_client_kwargs", lambda *a, **k: {"api_key": "miner-key"})
    # Deterministic "no miner env files" — node2 really has /etc/aitbc/aitbc-miner.env.
    monkeypatch.setattr("aitbc_cli.commands.dashboard._miner_env", lambda: {})


def _native_config():
    return SimpleNamespace(
        evm_rpc_url=None,
        energy_pricing_contract_address=None,
        coordinator_api_url="http://localhost:8203",
        native_coordinator_url="http://coord.test",
        api_key=None,
    )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def native_cfg(monkeypatch):
    cfg = _native_config()
    monkeypatch.setattr(energy_mod, "get_config", lambda: cfg)
    monkeypatch.setattr("aitbc_cli.config.get_config", lambda: cfg)
    return cfg


REGISTER_ARGS = [
    "provider",
    "register",
    "--resource-id",
    "res-1",
    "--provider-address",
    "0x" + "22" * 20,
    "--model-id",
    "test-gpu",
    "--tbp-watts",
    "300",
    "--eur-per-kwh",
    "0.30",
]


class TestMinerIdResolution:
    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv("MINER_ID", "env-miner")
        assert _resolve_miner_id("flag-miner") == "flag-miner"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("MINER_ID", "env-miner")
        assert _resolve_miner_id(None) == "env-miner"

    def test_unresolved_is_empty(self, monkeypatch):
        monkeypatch.delenv("MINER_ID", raising=False)
        assert _resolve_miner_id(None) == ""


class TestNativeEnergyRequestHeader:
    def test_miner_id_sets_header_alongside_api_key(self, monkeypatch):
        monkeypatch.setattr(
            energy_mod,
            "auth_client_kwargs",
            lambda *a, **k: {"headers": {"Authorization": "Bearer jwt"}, "api_key": "k"},
        )
        monkeypatch.setattr(energy_mod, "get_config", lambda: _native_config())
        _native_energy_request(None, "post", "/v1/market/native-energy/profile", miner=True, miner_id="miner-1", json_body={})
        client = _FakeClient.instances[0]
        assert client.headers["X-Miner-ID"] == "miner-1"
        assert client.headers["Authorization"] == "Bearer jwt"
        assert client.headers["X-API-Key"] == "k"

    def test_no_miner_id_sends_no_header(self, monkeypatch):
        monkeypatch.setattr(energy_mod, "get_config", lambda: _native_config())
        _native_energy_request(None, "post", "/v1/market/native-energy/profile", miner=True, json_body={})
        assert "X-Miner-ID" not in _FakeClient.instances[0].headers


class TestProviderRegister:
    def test_miner_id_flag_reaches_header(self, runner, native_cfg):
        result = runner.invoke(energy, REGISTER_ARGS + ["--miner-id", "miner-1"], obj={})
        assert result.exit_code == 0, result.output
        assert _FakeClient.instances[0].headers["X-Miner-ID"] == "miner-1"
        assert _FakeClient.instances[0].last_post[0] == "/v1/market/native-energy/profile"

    def test_miner_id_env_fallback_reaches_header(self, runner, native_cfg, monkeypatch):
        monkeypatch.setenv("MINER_ID", "env-miner")
        result = runner.invoke(energy, REGISTER_ARGS, obj={})
        assert result.exit_code == 0, result.output
        assert _FakeClient.instances[0].headers["X-Miner-ID"] == "env-miner"

    def test_no_miner_id_warns_and_omits_header(self, runner, native_cfg, monkeypatch):
        monkeypatch.delenv("MINER_ID", raising=False)
        result = runner.invoke(energy, REGISTER_ARGS, obj={})
        assert result.exit_code == 0, result.output
        assert "miner_<hash>" in result.output
        assert "X-Miner-ID" not in _FakeClient.instances[0].headers
