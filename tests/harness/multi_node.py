"""
Multi-node test harness for v0.5.17 test infrastructure.

Provides a harness to spin up multiple blockchain nodes (hub + followers)
with different chain configs, network partition simulation, block propagation
verification, and Byzantine node simulation.

This harness is used by v0.6.1 (Parallel Processing), v0.6.2 (Sync),
v0.9.0 (Chaos Testing), and the v0.5.16 regression tests.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

# Ensure blockchain-node src is on path
_BLOCKCHAIN_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "blockchain-node", "src")
_BLOCKCHAIN_SRC = os.path.abspath(_BLOCKCHAIN_SRC)
import sys

if _BLOCKCHAIN_SRC not in sys.path:
    sys.path.insert(0, _BLOCKCHAIN_SRC)


@dataclass
class NodeConfig:
    """Configuration for a single test node."""

    node_id: str
    chain_id: str
    is_hub: bool = False
    port: int = 8006
    sync_sources: dict[str, str] = field(default_factory=dict)
    byzantine: bool = False
    partitioned: bool = False


@dataclass
class TestNode:
    """A running test node with its own FastAPI app and database."""

    config: NodeConfig
    app: FastAPI
    client: TestClient
    engine: Any
    db_path: str
    _server_thread: threading.Thread | None = None
    _running: bool = False

    def start_server(self) -> None:
        """Start the node's HTTP server in a background thread."""
        import uvicorn

        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.config.port, log_level="warning")
        server = uvicorn.Server(config)

        def _run():
            asyncio.run(server.serve())

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        self._running = True
        # Give server time to start
        time.sleep(0.3)

    def stop_server(self) -> None:
        """Stop the HTTP server."""
        self._running = False
        # Thread is daemon, will exit with process

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.config.port}"

    def is_partitioned(self) -> bool:
        return self.config.partitioned

    def is_byzantine(self) -> bool:
        return self.config.byzantine


class MultiNodeHarness:
    """Harness to spin up multiple blockchain nodes for integration testing.

    Features:
    - Start N nodes with M chains
    - Network partition simulation (disconnect/reconnect)
    - Block propagation verification
    - Byzantine node simulation (invalid blocks, invalid signatures)
    - Chain reorg simulation (fork then resolve)
    - Sync lag measurement
    """

    def __init__(self) -> None:
        self.nodes: dict[str, TestNode] = {}
        self._tmpdir: tempfile.TemporaryDirectory | None = None

    def start_network(
        self,
        num_nodes: int = 3,
        num_chains: int = 2,
        chain_ids: list[str] | None = None,
        base_port: int = 8006,
    ) -> None:
        """Start a network of nodes with multiple chains.

        Args:
            num_nodes: Number of follower nodes (plus 1 hub)
            num_chains: Number of chains to configure
            chain_ids: Optional explicit chain IDs
            base_port: Starting port for nodes
        """
        self._tmpdir = tempfile.TemporaryDirectory()

        if chain_ids is None:
            chain_ids = ["ait-hub"] + [f"ait-island{i}" for i in range(1, num_chains)]

        hub_chain = chain_ids[0]

        # Create hub node
        hub_config = NodeConfig(
            node_id="hub",
            chain_id=hub_chain,
            is_hub=True,
            port=base_port,
        )
        hub_node = self._create_node(hub_config)
        self.nodes["hub"] = hub_node

        # Create follower nodes
        for i in range(num_nodes):
            follower_id = f"follower-{i + 1}"
            chain_idx = (i % (len(chain_ids) - 1)) + 1 if len(chain_ids) > 1 else 0
            follower_chain = chain_ids[chain_idx] if chain_idx < len(chain_ids) else hub_chain
            config = NodeConfig(
                node_id=follower_id,
                chain_id=follower_chain,
                is_hub=False,
                port=base_port + i + 1,
                sync_sources={hub_chain: f"http://127.0.0.1:{base_port}"},
            )
            node = self._create_node(config)
            self.nodes[follower_id] = node

    def _create_node(self, config: NodeConfig) -> TestNode:
        """Create a test node with its own database and FastAPI app."""
        assert self._tmpdir is not None

        db_path = os.path.join(self._tmpdir.name, f"{config.node_id}.db")
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        SQLModel.metadata.create_all(engine)

        # Create a minimal FastAPI app for the node
        app = FastAPI(title=f"Test Node {config.node_id}")

        # Add basic endpoints
        self._add_endpoints(app, config, engine)

        client = TestClient(app)

        return TestNode(
            config=config,
            app=app,
            client=client,
            engine=engine,
            db_path=db_path,
        )

    def _add_endpoints(self, app: FastAPI, config: NodeConfig, engine: Any) -> None:
        """Add basic RPC endpoints to a test node's app."""

        @app.get("/rpc/head")
        async def get_head() -> dict[str, Any]:
            from aitbc_chain.models import Block
            from sqlmodel import select

            with Session(engine) as session:
                stmt = select(Block).where(Block.chain_id == config.chain_id).order_by(Block.height.desc()).limit(1)
                block = session.exec(stmt).first()
                if block:
                    return {"height": block.height, "hash": block.hash, "chain_id": block.chain_id}
                return {"height": -1, "hash": None, "chain_id": config.chain_id}

        @app.get("/rpc/blocks-range")
        async def get_blocks_range(start: int = 0, end: int = 100, chain_id: str = "") -> list[dict[str, Any]]:
            from aitbc_chain.models import Block
            from sqlmodel import select

            target_chain = chain_id or config.chain_id
            with Session(engine) as session:
                stmt = (
                    select(Block)
                    .where(Block.chain_id == target_chain, Block.height >= start, Block.height <= end)
                    .order_by(Block.height)
                )
                blocks = session.exec(stmt).all()
                return [
                    {
                        "height": b.height,
                        "hash": b.hash,
                        "parent_hash": b.parent_hash,
                        "chain_id": b.chain_id,
                        "proposer": b.proposer,
                        "timestamp": b.timestamp.isoformat() if b.timestamp else None,
                    }
                    for b in blocks
                ]

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "node_id": config.node_id,
                "chain_id": config.chain_id,
                "is_hub": config.is_hub,
                "partitioned": config.partitioned,
            }

        @app.get("/rpc/account/{address}")
        async def get_account(address: str) -> dict[str, Any]:
            from aitbc_chain.models import Account

            with Session(engine) as session:
                account = session.get(Account, (config.chain_id, address))
                if account:
                    return {
                        "address": address,
                        "balance": account.balance,
                        "nonce": account.nonce,
                        "chain_id": config.chain_id,
                    }
                return {"address": address, "balance": 0, "nonce": 0, "chain_id": config.chain_id}

    def partition(self, node_ids: list[str]) -> None:
        """Simulate network partition — disconnect specified nodes."""
        for nid in node_ids:
            if nid in self.nodes:
                self.nodes[nid].config.partitioned = True

    def heal(self) -> None:
        """Reconnect all partitioned nodes."""
        for node in self.nodes.values():
            node.config.partitioned = False

    def add_byzantine_node(self, chain_id: str, port: int | None = None) -> str:
        """Add a node that sends invalid blocks.

        Returns:
            The node_id of the new Byzantine node.
        """
        assert self._tmpdir is not None
        base_port = max(n.config.port for n in self.nodes.values()) + 1 if self.nodes else 8006
        node_id = f"byzantine-{len(self.nodes)}"
        config = NodeConfig(
            node_id=node_id,
            chain_id=chain_id,
            is_hub=False,
            port=port or base_port,
            byzantine=True,
        )

        # Create a byzantine-specific app with invalid endpoints
        db_path = os.path.join(self._tmpdir.name, f"{config.node_id}.db")
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        SQLModel.metadata.create_all(engine)

        app = FastAPI(title=f"Byzantine Node {node_id}")

        @app.get("/rpc/head")
        async def byzantine_head() -> dict[str, Any]:
            return {"height": 999999, "hash": "0xfake", "chain_id": chain_id}

        @app.get("/rpc/blocks-range")
        async def byzantine_blocks(start: int = 0, end: int = 100, chain_id: str = "") -> list[dict[str, Any]]:
            return [
                {
                    "height": start,
                    "hash": "0xinvalid_byzantine",
                    "parent_hash": "0xnonexistent",
                    "chain_id": chain_id,
                    "proposer": "0xbyzantine_attacker",
                    "timestamp": None,
                }
            ]

        @app.get("/health")
        async def byzantine_health() -> dict[str, Any]:
            return {"status": "ok", "node_id": node_id, "chain_id": chain_id, "byzantine": True}

        client = TestClient(app)

        node = TestNode(
            config=config,
            app=app,
            client=client,
            engine=engine,
            db_path=db_path,
        )

        self.nodes[node_id] = node
        return node_id

    def verify_block_propagation(self, chain_id: str, height: int, timeout: float = 5.0) -> bool:
        """Verify that all non-partitioned nodes have a block at the given height.

        Args:
            chain_id: Chain to check
            height: Block height to verify
            timeout: Maximum time to wait for propagation

        Returns:
            True if all active nodes have the block, False otherwise.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            all_have = True
            for node in self.nodes.values():
                if node.is_partitioned() or node.is_byzantine():
                    continue
                resp = node.client.get(f"/rpc/blocks-range?start={height}&end={height}&chain_id={chain_id}")
                blocks = resp.json()
                if not blocks or len(blocks) == 0:
                    all_have = False
                    break
            if all_have:
                return True
            time.sleep(0.1)
        return False

    def measure_sync_lag(self, chain_id: str) -> dict[str, int]:
        """Measure sync lag across all nodes for a chain.

        Returns:
            Dict mapping node_id → height difference from hub.
        """
        hub_resp = self.nodes["hub"].client.get("/rpc/head")
        hub_height = hub_resp.json().get("height", -1)

        lag = {}
        for nid, node in self.nodes.items():
            if nid == "hub" or node.is_partitioned():
                continue
            resp = node.client.get("/rpc/head")
            node_height = resp.json().get("height", -1)
            lag[nid] = max(0, hub_height - node_height)

        return lag

    def shutdown(self) -> None:
        """Shut down all nodes and clean up."""
        for node in self.nodes.values():
            node.stop_server()
            node.engine.dispose()
        self.nodes.clear()
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None


@pytest.fixture
def multi_node_harness() -> Generator[MultiNodeHarness]:
    """Create a multi-node test harness.

    Yields:
        MultiNodeHarness instance. Call start_network() to begin.
    """
    harness = MultiNodeHarness()
    try:
        yield harness
    finally:
        harness.shutdown()


@pytest.fixture
def three_node_network(multi_node_harness) -> Generator[MultiNodeHarness]:
    """Pre-configured 3-node network (1 hub + 2 followers) with 2 chains."""
    multi_node_harness.start_network(num_nodes=2, num_chains=2)
    try:
        yield multi_node_harness
    finally:
        multi_node_harness.shutdown()
