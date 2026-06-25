"""
Multi-chain test fixtures for v0.5.17 test infrastructure.

Provides fixtures to spin up multiple chains with separate in-memory databases,
per-chain sync source mapping, island-to-chain registry, and multi-chain mempool.

These fixtures are the foundation for v0.5.16 regression tests, bridge tests,
and all subsequent multi-chain/multi-island releases (v0.6.3, v0.6.4, v0.7.0).
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Ensure blockchain-node src is on path
_BLOCKCHAIN_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "blockchain-node", "src")
_BLOCKCHAIN_SRC = os.path.abspath(_BLOCKCHAIN_SRC)
if _BLOCKCHAIN_SRC not in os.path.dirname(__file__):
    import sys

    if _BLOCKCHAIN_SRC not in sys.path:
        sys.path.insert(0, _BLOCKCHAIN_SRC)


@dataclass
class ChainContext:
    """Represents a single chain's test context."""

    chain_id: str
    engine: Any
    session_factory: Any
    db_path: str
    is_hub: bool = False
    sync_sources: dict[str, str] = field(default_factory=dict)

    @contextmanager
    def session(self) -> Generator[Session]:
        with Session(self.engine) as session:
            yield session
            session.rollback()


@dataclass
class MultiChainSetup:
    """Container for multiple chain contexts."""

    chains: dict[str, ChainContext] = field(default_factory=dict)
    hub_chain_id: str = ""

    @property
    def hub(self) -> ChainContext:
        return self.chains[self.hub_chain_id]

    def get(self, chain_id: str) -> ChainContext:
        return self.chains[chain_id]

    @property
    def chain_ids(self) -> list[str]:
        return list(self.chains.keys())


def _create_in_memory_engine(chain_id: str, tmp_path: str) -> Any:
    """Create an in-memory SQLite engine for a chain."""
    # Import all models to ensure they are registered with SQLModel.metadata
    from aitbc_chain.models import Account, Block, Escrow, Receipt, Transaction  # noqa: F401

    db_path = os.path.join(tmp_path, f"{chain_id}.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_session_factory(engine: Any):
    """Create a session factory context manager for the given engine."""

    @contextmanager
    def _factory():
        with Session(engine) as session:
            yield session
            session.rollback()

    return _factory


@pytest.fixture
def multi_chain_setup(tmp_path) -> Generator[MultiChainSetup]:
    """Spin up 2 chains (ait-hub, ait-island1) with separate databases.

    Each chain gets its own in-memory SQLite database with all tables created.
    The hub chain is the default, and the island chain has a sync source
    pointing to the hub.

    Yields:
        MultiChainSetup with chains dict, hub chain accessible via .hub
    """
    setup = MultiChainSetup(hub_chain_id="ait-hub")

    # Create hub chain
    hub_engine = _create_in_memory_engine("ait-hub", str(tmp_path))
    hub_ctx = ChainContext(
        chain_id="ait-hub",
        engine=hub_engine,
        session_factory=_make_session_factory(hub_engine),
        db_path=str(tmp_path / "ait-hub.db"),
        is_hub=True,
    )
    setup.chains["ait-hub"] = hub_ctx

    # Create island chain
    island_engine = _create_in_memory_engine("ait-island1", str(tmp_path))
    island_ctx = ChainContext(
        chain_id="ait-island1",
        engine=island_engine,
        session_factory=_make_session_factory(island_engine),
        db_path=str(tmp_path / "ait-island1.db"),
        is_hub=False,
        sync_sources={"ait-hub": "http://localhost:8006"},
    )
    setup.chains["ait-island1"] = island_ctx

    try:
        yield setup
    finally:
        for ctx in setup.chains.values():
            ctx.engine.dispose()


@pytest.fixture
def three_chain_setup(tmp_path) -> Generator[MultiChainSetup]:
    """Spin up 3 chains (ait-hub, ait-island1, ait-island2) for more complex tests."""
    setup = MultiChainSetup(hub_chain_id="ait-hub")

    configs = [
        ("ait-hub", True, {}),
        ("ait-island1", False, {"ait-hub": "http://localhost:8006"}),
        ("ait-island2", False, {"ait-hub": "http://localhost:8006"}),
    ]

    for chain_id, is_hub, sync_sources in configs:
        engine = _create_in_memory_engine(chain_id, str(tmp_path))
        ctx = ChainContext(
            chain_id=chain_id,
            engine=engine,
            session_factory=_make_session_factory(engine),
            db_path=str(tmp_path / f"{chain_id}.db"),
            is_hub=is_hub,
            sync_sources=sync_sources,
        )
        setup.chains[chain_id] = ctx

    try:
        yield setup
    finally:
        for ctx in setup.chains.values():
            ctx.engine.dispose()


@pytest.fixture
def sync_source_map(multi_chain_setup) -> dict[str, str]:
    """Per-chain sync source mapping (chain_id → hub_url)."""
    sources = {}
    for _chain_id, ctx in multi_chain_setup.chains.items():
        sources.update(ctx.sync_sources)
    return sources


@pytest.fixture
def island_registry(multi_chain_setup) -> dict[str, dict[str, str]]:
    """Island-to-chain-to-hub registry.

    Returns:
        Dict mapping island_id → {chain_id, hub_url, hub_chain_id}
    """
    return {
        "island-hub": {
            "chain_id": "ait-hub",
            "hub_url": "http://localhost:8006",
            "hub_chain_id": "ait-hub",
        },
        "island-1": {
            "chain_id": "ait-island1",
            "hub_url": "http://localhost:8006",
            "hub_chain_id": "ait-hub",
        },
    }


@pytest.fixture
def multi_chain_mempool(multi_chain_setup):
    """Multi-chain mempool with per-chain namespaces.

    Returns an InMemoryMempool instance configured for multi-chain operation.
    """
    from aitbc_chain.mempool import InMemoryMempool

    pool = InMemoryMempool(max_size=10_000, min_fee=0, chain_id=multi_chain_setup.hub_chain_id)

    # Seed each chain with a test transaction
    for chain_id in multi_chain_setup.chain_ids:
        tx = {
            "chain_id": chain_id,
            "from": "0xtest_sender",
            "to": "0xtest_recipient",
            "amount": 100,
            "fee": 36,
            "nonce": 0,
            "type": "TRANSFER",
            "payload": {},
        }
        pool.add(tx, chain_id=chain_id)

    return pool


@pytest.fixture
def mock_settings(multi_chain_setup):
    """Mock blockchain settings configured for multi-chain test.

    Patches the settings module so that supported_chains includes all test chains
    and the default chain_id is the hub.
    """
    from aitbc_chain.config import settings

    chain_ids = ",".join(multi_chain_setup.chain_ids)

    with patch.object(settings, "chain_id", multi_chain_setup.hub_chain_id):
        with patch.object(settings, "supported_chains", chain_ids):
            yield settings


# --- Helper functions for tests ---


def make_test_account(chain_id: str, address: str, balance: int = 10000, nonce: int = 0) -> dict[str, Any]:
    """Create a test account dict for seeding databases."""
    return {
        "chain_id": chain_id,
        "address": address,
        "balance": balance,
        "nonce": nonce,
    }


def seed_account(chain_ctx: ChainContext, address: str, balance: int = 10000, nonce: int = 0) -> None:
    """Seed an account in a chain's database."""
    from aitbc_chain.models import Account

    with chain_ctx.session() as session:
        account = Account(
            chain_id=chain_ctx.chain_id,
            address=address,
            balance=balance,
            nonce=nonce,
        )
        session.add(account)
        session.commit()


def seed_accounts_multi_chain(setup: MultiChainSetup, address: str, balance: int = 10000) -> None:
    """Seed an account on all chains in the setup."""
    for ctx in setup.chains.values():
        seed_account(ctx, address, balance)
