"""AUDIT-MINER-* cluster (#2594/#2595/#2537/#2538): miner_cli +
miner_management truthfulness fixes.

- #2594 argparse defaults read MINER_API_KEY/COORDINATOR_URL, --api-key-file
  is preferred, an empty key refuses, admin calls use ADMIN_API_KEY.
- #2595 list_market_offers filters on the offer's provider_id/provider
  field exactly — no more substring scan over str(o).
- #2537 update_capabilities merges onto the current record (GET admin
  miners) and omits unset fields — no null concurrency/region, no wiped
  capabilities.
- #2538 miner_cli exits non-zero on failure results, unknown actions and
  missing keys.
"""

import json
import sys
from types import SimpleNamespace

import miner_cli
import miner_management as mm
import pytest


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def market_get(monkeypatch):
    state = SimpleNamespace(calls=[], result=_Resp())

    def _get(url, headers=None, params=None, timeout=None, **kw):
        state.calls.append({"url": url, "headers": headers, "params": params})
        return state.result

    monkeypatch.setattr(mm.requests, "get", _get)
    return state


# --- #2595: exact miner filter -------------------------------------------


def test_market_list_filters_on_provider_field_exactly(market_get):
    market_get.result = _Resp(
        payload=[
            {"provider": "miner-1", "provider_id": "miner-1", "price": "0.5"},
            {"provider": "miner-10", "provider_id": "miner-10", "price": "0.6"},
            {"provider": "Miner-2", "provider_id": "Miner-2", "price": "0.7"},
        ]
    )
    out = mm.list_market_offers(miner_id="miner-1", api_key="k", coordinator_url="http://c")
    assert out is not None
    assert [o["provider_id"] for o in out["offers"]] == ["miner-1"]
    assert out["count"] == 1


def test_market_list_miner_id_is_case_sensitive(market_get):
    """Exact compare: 'Miner-2' does not match 'miner-2'."""
    market_get.result = _Resp(payload=[{"provider_id": "miner-2", "price": "0.5"}])
    out = mm.list_market_offers(miner_id="Miner-2", api_key="k", coordinator_url="http://c")
    assert out is not None
    assert out["offers"] == []
    assert out["count"] == 0


# --- #2537: update merges with current record ----------------------------


@pytest.fixture
def update_calls(monkeypatch):
    state = SimpleNamespace(get_result=_Resp(), put_result=_Resp(), put_payload=None)

    def _get(url, headers=None, params=None, timeout=None, **kw):
        return state.get_result

    def _put(url, headers=None, json=None, timeout=None, **kw):
        state.put_payload = json
        return state.put_result

    monkeypatch.setattr(mm.requests, "get", _get)
    monkeypatch.setattr(mm.requests, "put", _put)
    return state


def _admin_list(capabilities=None, concurrency=4, region="eu-1"):
    return _Resp(
        payload={
            "items": [
                {
                    "miner_id": "m1",
                    "status": "ONLINE",
                    "concurrency": concurrency,
                    "region": region,
                    "capabilities": capabilities if capabilities is not None else {"models": ["llama3"], "gpu_memory": 8192},
                }
            ]
        }
    )


def test_update_capabilities_merges_and_omits_nulls(update_calls):
    update_calls.get_result = _admin_list()
    update_calls.put_result = _Resp(payload={"status": "updated"})

    out = mm.update_capabilities("m1", api_key="k", coordinator_url="http://c", pricing=0.9)

    assert out is not None and out["status"].startswith("✅")
    sent = update_calls.put_payload
    assert sent["concurrency"] == 4  # current value preserved, not null
    assert sent["region"] == "eu-1"  # current value preserved, not null
    # existing caps kept, new pricing merged in
    assert sent["capabilities"]["models"] == ["llama3"]
    assert sent["capabilities"]["gpu_memory"] == 8192
    assert sent["capabilities"]["pricing_per_hour"] == 0.9
    assert "wallet_address" not in sent


def test_update_capabilities_explicit_values_win(update_calls):
    update_calls.get_result = _admin_list()
    update_calls.put_result = _Resp(payload={"status": "updated"})

    mm.update_capabilities("m1", api_key="k", coordinator_url="http://c", concurrency=2, region="us-1", gpu_memory=4096)
    sent = update_calls.put_payload
    assert sent["concurrency"] == 2
    assert sent["region"] == "us-1"
    assert sent["capabilities"]["gpu_memory"] == 4096
    assert sent["capabilities"]["models"] == ["llama3"]


def test_update_capabilities_refuses_when_current_record_unreadable(update_calls):
    """A partial PUT without the current record would wipe fields — refuse."""
    update_calls.get_result = _Resp(status_code=503, payload={})
    called = {"put": False}

    def _put(*a, **kw):
        called["put"] = True
        return _Resp()

    import miner_management

    orig = miner_management.requests.put
    miner_management.requests.put = _put
    try:
        out = mm.update_capabilities("m1", api_key="k", coordinator_url="http://c", pricing=1.0)
    finally:
        miner_management.requests.put = orig
    assert out is not None and out["status"].startswith("❌")
    assert called["put"] is False


def test_update_capabilities_miner_not_found(update_calls):
    update_calls.get_result = _Resp(payload={"items": []})
    out = mm.update_capabilities("ghost", api_key="k", coordinator_url="http://c", pricing=1.0)
    assert out is not None and out["status"].startswith("❌")
    assert "not found" in out["error"]


# --- #2594: env defaults, key file, admin credential ----------------------


def test_admin_calls_use_admin_api_key_env(monkeypatch, market_get):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    market_get.result = _Resp(payload=[{"provider_id": "m1"}])
    mm.list_market_offers(api_key="miner_abc", coordinator_url="http://c")
    assert market_get.calls[0]["headers"]["X-Api-Key"] == "admin-secret"


def test_admin_calls_fall_back_to_legacy_rewrite(monkeypatch, market_get):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    market_get.result = _Resp(payload=[])
    mm.list_market_offers(api_key="miner_abc", coordinator_url="http://c")
    assert market_get.calls[0]["headers"]["X-Api-Key"] == "admin_abc"


def test_parser_defaults_read_environment(monkeypatch):
    monkeypatch.setenv("MINER_API_KEY", "env-key")
    monkeypatch.setenv("COORDINATOR_URL", "http://env:9999")
    parser = miner_cli._build_parser()
    args = parser.parse_args(["status", "--miner-id", "m1"])
    assert args.api_key == "env-key"
    assert args.coordinator_url == "http://env:9999"


def test_api_key_file_wins_over_flag_and_env(monkeypatch, tmp_path):
    keyfile = tmp_path / "key"
    keyfile.write_text("file-key\n")
    monkeypatch.setenv("MINER_API_KEY", "env-key")
    parser = miner_cli._build_parser()
    args = parser.parse_args(["--api-key", "flag-key", "--api-key-file", str(keyfile), "status", "--miner-id", "m1"])
    assert miner_cli._resolve_api_key(args) == "file-key"


def test_empty_key_refuses(monkeypatch):
    monkeypatch.delenv("MINER_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["miner_cli.py", "status", "--miner-id", "m1"])
    with pytest.raises(SystemExit) as exc:
        miner_cli.main()
    assert exc.value.code == 1


# --- #2538: failure exits non-zero ----------------------------------------


def _run_main(monkeypatch, result):
    # Top-level options precede the subcommand in argparse.
    monkeypatch.setattr(sys, "argv", ["miner_cli.py", "--api-key", "k", "status", "--miner-id", "m1"])
    monkeypatch.setattr(miner_cli, "miner_cli_dispatcher", lambda action, **kw: result)
    miner_cli.main()


def test_main_exits_1_on_failure_status(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, {"action": "status", "status": "❌ Connection error: refused"})
    assert exc.value.code == 1


def test_main_exits_1_on_none_result(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, None)
    assert exc.value.code == 1


def test_main_exits_0_on_success(monkeypatch):
    _run_main(monkeypatch, {"action": "status", "status": "✅ ONLINE"})


def test_main_exits_1_on_unknown_market_action(monkeypatch):
    # `market` with no sub-action resolves to None in _market_kwargs.
    monkeypatch.setattr(sys, "argv", ["miner_cli.py", "--api-key", "k", "market"])
    with pytest.raises(SystemExit) as exc:
        miner_cli.main()
    assert exc.value.code == 1
