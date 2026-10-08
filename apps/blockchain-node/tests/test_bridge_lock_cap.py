"""BR-3: the per-lock cap fails closed in production.

When locks are enabled and ``BRIDGE_MAX_LOCK_AMOUNT`` is unset or 0, a
production node (``ENVIRONMENT``/``APP_ENV``/``NODE_ENV``) must refuse new
locks — an explicit error and a logged reason — instead of silently running
uncapped. Development/test environments keep the historical
``0 = unlimited`` behaviour; a set cap is enforced in every environment.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import CrossChainTransfer
from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account

_ENV_VARS = ("ENVIRONMENT", "APP_ENV", "NODE_ENV")


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture()
def production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    return True


@pytest.fixture()
def development(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return True


def _seed(engine, chain_id: str, address: str, balance: int) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _balance(engine, chain_id: str, address: str) -> int:
    with Session(engine) as session:
        acc = session.get(Account, (chain_id, address))
        assert acc is not None
        session.expunge(acc)
        return acc.balance


class TestLockCapFailClosed:
    def test_production_unset_cap_refuses_lock(self, bridge, engine, production, monkeypatch):
        monkeypatch.setattr(settings, "bridge_max_lock_amount", 0)
        _seed(engine, "chain-a", "0xsender", 10_000)

        with pytest.raises(ValueError, match="BRIDGE_MAX_LOCK_AMOUNT is unset or 0"):
            bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)

        # Refused before any debit or transfer row.
        assert _balance(engine, "chain-a", "0xsender") == 10_000
        with Session(engine) as session:
            assert session.exec(select(CrossChainTransfer)).all() == []

    def test_production_set_cap_allows_lock(self, bridge, engine, production, monkeypatch):
        monkeypatch.setattr(settings, "bridge_max_lock_amount", 36_000_000_000)
        _seed(engine, "chain-a", "0xsender", 10_000)

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)

        assert transfer.amount == 1000

    def test_production_over_cap_refuses(self, bridge, engine, production, monkeypatch):
        monkeypatch.setattr(settings, "bridge_max_lock_amount", 36_000_000_000)
        _seed(engine, "chain-a", "0xsender", 10_000)

        with pytest.raises(ValueError, match="exceeds bridge max lock amount"):
            bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 36_000_000_001)

        assert _balance(engine, "chain-a", "0xsender") == 10_000

    def test_development_unset_cap_unchanged(self, bridge, engine, development, monkeypatch):
        """0 = unlimited stays for non-production environments."""
        monkeypatch.setattr(settings, "bridge_max_lock_amount", 0)
        _seed(engine, "chain-a", "0xsender", 10_000)

        transfer = bridge.initiate_transfer("chain-a", "chain-b", "0xsender", "0xrecipient", 1000)

        assert transfer.amount == 1000
