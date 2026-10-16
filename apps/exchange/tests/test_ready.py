"""The exchange's /ready probe reports unready when an enabled required
feature is unavailable — its own database always, plus the bridge monitor's
deposits store whenever bridge deposits or withdrawals are enabled."""

import dataclasses
import json
import sqlite3
import sys

import pytest

from starlette.responses import Response

from apps.exchange.simple_exchange.main import _dispatch

from .test_idempotent_operations import _request


def _config_module():
    # test_http_contract pops and re-imports the whole simple_exchange package,
    # so module-level imports made at collection time can go stale — resolve
    # whichever instance is live in sys.modules right now.
    return sys.modules["apps.exchange.simple_exchange.config"]


async def _ready() -> Response:
    return await _dispatch(_request("GET", "/ready"), "GET")


def _make_bridge_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS eth_deposits (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


@pytest.fixture
def bridge_disabled(monkeypatch):
    cfg_mod = _config_module()
    cfg = dataclasses.replace(cfg_mod.bridge_config, deposit_enabled=False, withdraw_enabled=False)
    monkeypatch.setattr(cfg_mod, "bridge_config", cfg)


@pytest.fixture
def bridge_storage(tmp_path, monkeypatch):
    """A bridge deposits store under the test DATA_DIR."""
    import aitbc.constants as constants

    db_path = constants.DATA_DIR / "data" / "bridge_deposits.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _make_bridge_db(db_path)
    return db_path


class TestExchangeReadiness:
    async def test_ready_when_all_required_features_available(self, exchange_db, bridge_storage):
        resp = await _ready()
        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert body["status"] == "ready"
        assert body["checks"] == ["bridge_storage", "database"]

    async def test_bridge_storage_checked_by_default(self, exchange_db):
        # Deposits are enabled by default; with no monitor db the surface is dead.
        import aitbc.constants as constants

        (constants.DATA_DIR / "data" / "bridge_deposits.db").unlink(missing_ok=True)
        resp = await _ready()
        assert resp.status_code == 503
        assert json.loads(resp.body)["failed"] == ["bridge_storage"]

    async def test_bridge_not_required_when_disabled(self, exchange_db, bridge_disabled):
        resp = await _ready()
        assert resp.status_code == 200
        assert json.loads(resp.body)["checks"] == ["database"]

    async def test_database_failure_reports_not_ready(self, exchange_db, bridge_storage, monkeypatch, tmp_path):
        # A directory is not a sqlite file — connecting to it fails, which is
        # also how a mispointed EXCHANGE_DATABASE_URL breaks in deployment.
        monkeypatch.setenv("EXCHANGE_DATABASE_URL", str(tmp_path))
        resp = await _ready()
        assert resp.status_code == 503
        body = json.loads(resp.body)
        assert body["failed"] == ["database"]
        # The reason stays server-side — /ready is unauthenticated.
        assert "unable to open" not in resp.body.decode()

    async def test_api_ready_alias(self, exchange_db, bridge_disabled):
        resp = await _dispatch(_request("GET", "/api/ready"), "GET")
        assert resp.status_code == 200

    async def test_settlement_envs_checked_when_enabled(self, exchange_db, bridge_storage, monkeypatch):
        # With the settlement flag on, both funding destinations must be
        # configured EIP-55 addresses — readiness surfaces the misconfig
        # instead of refusing every order at placement.
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
        resp = await _ready()
        assert resp.status_code == 503
        assert "settlement_envs" in json.loads(resp.body)["failed"]

    async def test_settlement_envs_pass_when_configured(self, exchange_db, bridge_storage, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SETTLEMENT_ENABLED", "true")
        monkeypatch.setenv("AIT_SELL_ESCROW", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
        monkeypatch.setenv("BRIDGE_ETH_ADDRESS", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359")
        resp = await _ready()
        assert resp.status_code == 200
        assert "settlement_envs" in json.loads(resp.body)["checks"]

    async def test_settlement_envs_absent_when_flag_off(self, exchange_db, bridge_storage, monkeypatch):
        monkeypatch.delenv("EXCHANGE_SETTLEMENT_ENABLED", raising=False)
        monkeypatch.delenv("AIT_SELL_ESCROW", raising=False)
        monkeypatch.delenv("BRIDGE_ETH_ADDRESS", raising=False)
        resp = await _ready()
        assert resp.status_code == 200
        assert "settlement_envs" not in json.loads(resp.body)["checks"]
