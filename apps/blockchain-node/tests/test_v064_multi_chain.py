"""Tests for v0.6.4 multi-chain per island: MultiChainManager with PortAllocator,
retry/backoff, threshold guards, config fields, and make_genesis multi-genesis.

B1: Config fields (island_chains, chain_configs, chain_port_offsets, retry/health/shutdown)
B4: MultiChainManager startup sequencing with PortAllocator + retry/backoff
B5: Threshold guards for MultiValidatorPoA + PBFT
B7: make_genesis multi-genesis support
B8: Integration tests — multi-chain, island leave cleanup, backward compat
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aitbc_chain.config import settings

# Ensure MULTI_VALIDATOR_CONSENSUS_ENABLED is set for threshold guard tests
os.environ.setdefault("MULTI_VALIDATOR_CONSENSUS_ENABLED", "true")


# ---------------------------------------------------------------------------
# B1 — Config fields
# ---------------------------------------------------------------------------


class TestMultiChainConfig:
    """Test multi-chain config fields added in v0.6.4."""

    def test_config_fields_exist(self):
        """All v0.6.4 config fields exist with correct defaults."""
        from aitbc_chain.config import settings

        assert hasattr(settings, "island_chains")
        assert hasattr(settings, "chain_configs")
        assert hasattr(settings, "chain_port_offsets")
        assert hasattr(settings, "multi_chain_start_max_retries")
        assert hasattr(settings, "multi_chain_start_base_delay")
        assert hasattr(settings, "multi_chain_start_max_delay")
        assert hasattr(settings, "multi_chain_start_backoff_multiplier")
        assert hasattr(settings, "multi_chain_health_interval")
        assert hasattr(settings, "chain_shutdown_timeout")

    def test_config_defaults(self):
        """Default values are correct."""
        from aitbc_chain.config import settings

        assert settings.island_chains == ""
        assert settings.chain_configs == {}
        assert settings.chain_port_offsets == ""
        assert settings.multi_chain_start_max_retries == 3
        assert settings.multi_chain_start_base_delay == 2.0
        assert settings.multi_chain_start_max_delay == 30.0
        assert settings.multi_chain_start_backoff_multiplier == 2.0
        assert settings.multi_chain_health_interval == 60
        assert settings.chain_shutdown_timeout == 10

    def test_chain_configs_validator_accepts_empty(self):
        """Empty chain_configs dict is valid."""
        from aitbc_chain.config import ChainSettings

        s = ChainSettings()
        assert s.chain_configs == {}

    def test_chain_configs_validator_parses_valid(self):
        """Valid chain_configs strings pass validation."""
        from aitbc_chain.config import ChainSettings

        s = ChainSettings(chain_configs={"chain-a": "block_time_seconds:2,max_txs_per_block:500"})
        assert s.chain_configs == {"chain-a": "block_time_seconds:2,max_txs_per_block:500"}

    def test_chain_configs_validator_rejects_invalid(self):
        """Invalid config string raises ValueError."""
        from aitbc_chain.config import ChainSettings

        with pytest.raises(ValueError, match="chain_configs"):
            ChainSettings(chain_configs={"chain-a": "not_a_real_setting:abc"})


# ---------------------------------------------------------------------------
# B4 — MultiChainManager with PortAllocator + retry/backoff
# ---------------------------------------------------------------------------


class TestMultiChainManagerPortAllocator:
    """Test MultiChainManager integration with PortAllocator."""

    def test_port_allocator_integration(self):
        """MultiChainManager uses PortAllocator when offsets configured."""
        from aitbc.network.port_allocator import PortAllocator

        from aitbc_chain.network.multi_chain_manager import MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            allocator = PortAllocator(
                base_rpc_port=8006,
                base_p2p_port=8007,
                port_offsets="chain-a:10,chain-b:20",
            )
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
                port_allocator=allocator,
            )
            # Default chain should have base ports
            default_chain = mgr.get_chain_status("default-chain")
            assert default_chain is not None
            assert default_chain.rpc_port == 8006
            assert default_chain.p2p_port == 8007

    def test_port_allocator_no_offsets_fallback(self):
        """Without per-chain offsets, falls back to naive incrementing."""
        from aitbc.network.port_allocator import PortAllocator

        from aitbc_chain.network.multi_chain_manager import MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            allocator = PortAllocator(base_rpc_port=8006, base_p2p_port=8007, port_offsets="")
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
                port_allocator=allocator,
            )
            # Without offsets, _allocate_ports uses naive incrementing
            rpc, p2p = mgr._allocate_ports("chain-x")
            assert rpc == 8007  # base + 1
            assert p2p == 8008  # base + 1


class TestMultiChainManagerRetry:
    """Test retry/backoff in start_chain."""

    def test_start_chain_retries_on_failure(self):
        """start_chain retries on failure with backoff."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import ChainStatus, ChainType, MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
            )

            # Mock init_db to always fail
            with patch("aitbc_chain.network.multi_chain_manager.init_db", side_effect=Exception("DB error")):
                with patch("aitbc_chain.network.multi_chain_manager.shutdown_db"):
                    # Patch asyncio.sleep to avoid real delays
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        result = asyncio.run(mgr.start_chain("failing-chain", ChainType.MICRO))

            assert result is False
            chain = mgr.get_chain_status("failing-chain")
            assert chain is not None
            assert chain.status == ChainStatus.ERROR
            assert "DB error" in chain.error_message

    def test_start_chain_succeeds_after_retry(self):
        """start_chain succeeds on retry after initial failure."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import ChainStatus, ChainType, MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
            )

            # Mock init_db to fail first, then succeed
            call_count = [0]

            def mock_init_db(chain_id):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise Exception("Transient error")

            mock_consensus = AsyncMock()
            mock_consensus.start = AsyncMock()

            with (
                patch("aitbc_chain.network.multi_chain_manager.init_db", side_effect=mock_init_db),
                patch("aitbc_chain.network.multi_chain_manager.shutdown_db"),
                patch("aitbc_chain.network.multi_chain_manager.PoAProposer", return_value=mock_consensus),
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                result = asyncio.run(mgr.start_chain("retry-chain", ChainType.MICRO))

            assert result is True
            chain = mgr.get_chain_status("retry-chain")
            assert chain is not None
            assert chain.status == ChainStatus.RUNNING
            assert call_count[0] == 2  # Failed once, succeeded on retry


class TestMultiChainManagerStartSecondary:
    """Test start_secondary_chains from config."""

    def test_start_secondary_chains_empty_config(self):
        """No secondary chains when island_chains is empty."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
            )
            with patch.object(settings, "island_chains", ""):
                asyncio.run(mgr.start_secondary_chains())
            # Only default chain should exist
            assert len(mgr.get_all_chains()) == 1

    def test_start_secondary_chains_from_config(self):
        """Secondary chains are started from island_chains config."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
            )

            mock_consensus = AsyncMock()
            mock_consensus.start = AsyncMock()

            with (
                patch("aitbc_chain.network.multi_chain_manager.init_db"),
                patch("aitbc_chain.network.multi_chain_manager.shutdown_db"),
                patch("aitbc_chain.network.multi_chain_manager.PoAProposer", return_value=mock_consensus),
                patch.object(settings, "island_chains", "default-chain,chain-a,chain-b"),
            ):
                asyncio.run(mgr.start_secondary_chains())

            # Default + 2 secondary chains
            all_chains = mgr.get_all_chains()
            chain_ids = [c.chain_id for c in all_chains]
            assert "default-chain" in chain_ids
            assert "chain-a" in chain_ids
            assert "chain-b" in chain_ids
            assert len(all_chains) == 3


class TestMultiChainManagerStop:
    """Test graceful stop with timeout."""

    def test_stop_stops_secondary_chains(self):
        """stop() stops all secondary chains."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import ChainInstance, ChainStatus, ChainType, MultiChainManager

        with tempfile.TemporaryDirectory() as tmpdir:
            base_db = Path(tmpdir) / "chain.db"
            mgr = MultiChainManager(
                default_chain_id="default-chain",
                base_db_path=base_db,
                base_rpc_port=8006,
                base_p2p_port=8007,
            )

            # Manually add a secondary chain in RUNNING state
            chain = ChainInstance(
                chain_id="secondary",
                chain_type=ChainType.MICRO,
                status=ChainStatus.RUNNING,
                db_path=base_db.parent / "secondary" / "chain.db",
                rpc_port=8007,
                p2p_port=8008,
                started_at=1.0,
            )
            chain._consensus = AsyncMock()
            chain._consensus.stop = AsyncMock()
            mgr.chains["secondary"] = chain

            with patch("aitbc_chain.network.multi_chain_manager.shutdown_db"):
                asyncio.run(mgr.stop())

            assert mgr.chains["secondary"].status == ChainStatus.STOPPED


# ---------------------------------------------------------------------------
# B5 — Threshold guards
# ---------------------------------------------------------------------------


class TestThresholdGuards:
    """Test threshold guards on MultiValidatorPoA and PBFT."""

    def test_multi_validator_poa_blocked_without_env(self):
        """MultiValidatorPoA raises RuntimeError when consensus disabled in config."""
        from aitbc_chain.config import settings
        from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

        original = settings.multi_validator_consensus_enabled
        settings.multi_validator_consensus_enabled = False
        try:
            with pytest.raises(RuntimeError, match="not yet activated"):
                MultiValidatorPoA("test-chain")
        finally:
            settings.multi_validator_consensus_enabled = original

    def test_multi_validator_poa_allowed_with_env(self):
        """MultiValidatorPoA works when consensus enabled in config."""
        from aitbc_chain.config import settings
        from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

        original = settings.multi_validator_consensus_enabled
        settings.multi_validator_consensus_enabled = True
        try:
            consensus = MultiValidatorPoA("test-chain")
            assert consensus.chain_id == "test-chain"
        finally:
            settings.multi_validator_consensus_enabled = original

    def test_pbft_blocked_without_env(self):
        """PBFTConsensus raises RuntimeError when consensus disabled in config."""
        from aitbc_chain.config import settings
        from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
        from aitbc_chain.consensus.pbft import PBFTConsensus

        original = settings.multi_validator_consensus_enabled
        settings.multi_validator_consensus_enabled = True
        try:
            poa = MultiValidatorPoA("test-chain")
        finally:
            settings.multi_validator_consensus_enabled = original

        settings.multi_validator_consensus_enabled = False
        try:
            with pytest.raises(RuntimeError, match="not yet activated"):
                PBFTConsensus(poa)
        finally:
            settings.multi_validator_consensus_enabled = original


# ---------------------------------------------------------------------------
# B7 — make_genesis multi-genesis
# ---------------------------------------------------------------------------


class TestMakeGenesisMultiGenesis:
    """Test make_genesis.py multi-genesis support."""

    def test_single_genesis_backward_compat(self):
        """Single genesis mode works as before."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            alloc_file = Path(tmpdir) / "alloc.json"
            alloc_file.write_text(json.dumps([{"address": "0xabc", "balance": 1000}]))

            output_file = Path(tmpdir) / "genesis.json"
            script = Path(__file__).parent.parent / "scripts" / "make_genesis.py"

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--allocations",
                    str(alloc_file),
                    "--authorities",
                    "0xabc",
                    "--chain-id",
                    "ait-test",
                    "--output",
                    str(output_file),
                    "--force",
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"make_genesis failed: {result.stderr}"
            assert output_file.exists()
            data = json.loads(output_file.read_text())
            assert data["chain_id"] == "ait-test"
            assert "island_id" not in data  # No island_id without flag

    def test_multi_genesis_with_chains(self):
        """Multi-genesis mode generates one file per chain."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            alloc_file = Path(tmpdir) / "alloc.json"
            alloc_file.write_text(json.dumps([{"address": "0xabc", "balance": 1000}]))

            output_dir = Path(tmpdir) / "genesis_out"
            script = Path(__file__).parent.parent / "scripts" / "make_genesis.py"

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--allocations",
                    str(alloc_file),
                    "--authorities",
                    "0xabc",
                    "--chains",
                    "chain-a,chain-b",
                    "--island-id",
                    "island-1",
                    "--output",
                    str(output_dir),
                    "--force",
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"make_genesis failed: {result.stderr}"

            # Check both genesis files exist
            genesis_a = output_dir / "chain-a" / "genesis.json"
            genesis_b = output_dir / "chain-b" / "genesis.json"
            assert genesis_a.exists()
            assert genesis_b.exists()

            data_a = json.loads(genesis_a.read_text())
            assert data_a["chain_id"] == "chain-a"
            assert data_a["island_id"] == "island-1"

            data_b = json.loads(genesis_b.read_text())
            assert data_b["chain_id"] == "chain-b"
            assert data_b["island_id"] == "island-1"

    def test_multi_genesis_island_id_optional(self):
        """Multi-genesis works without --island-id."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            alloc_file = Path(tmpdir) / "alloc.json"
            alloc_file.write_text(json.dumps([{"address": "0xabc", "balance": 1000}]))

            output_dir = Path(tmpdir) / "genesis_out"
            script = Path(__file__).parent.parent / "scripts" / "make_genesis.py"

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--allocations",
                    str(alloc_file),
                    "--authorities",
                    "0xabc",
                    "--chains",
                    "chain-x",
                    "--output",
                    str(output_dir),
                    "--force",
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"make_genesis failed: {result.stderr}"

            genesis = output_dir / "chain-x" / "genesis.json"
            assert genesis.exists()
            data = json.loads(genesis.read_text())
            assert "island_id" not in data


# ---------------------------------------------------------------------------
# B8 — Island leave cleanup (backward compat with chain_ids)
# ---------------------------------------------------------------------------


class TestIslandLeaveCleanup:
    """Test that leaving an island cleans up all chain databases."""

    def test_leave_island_cleans_up_chain_dbs(self):
        """leave_island shuts down all chain databases for the island."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "default-chain")
        mgr.join_island("island-uuid-1", "island1", ["chain-a", "chain-b"])

        # shutdown_db is imported inside leave_island from ..database
        with patch("aitbc_chain.database.shutdown_db") as mock_shutdown:
            result = mgr.leave_island("island-uuid-1")

        assert result is True
        # shutdown_db should be called for each chain
        called_chain_ids = [call.args[0] for call in mock_shutdown.call_args_list]
        assert "chain-a" in called_chain_ids
        assert "chain-b" in called_chain_ids

    def test_join_island_with_list_backward_compat(self):
        """join_island accepts both str and list for chain_id."""
        from aitbc_chain.network.island_manager import IslandManager

        mgr = IslandManager("node-1", "default-island", "default-chain")

        # Single string (backward compat)
        result = mgr.join_island("island-1", "island1", "chain-a")
        assert result is True
        membership = mgr.get_island_info("island-1")
        assert membership is not None
        assert membership.chain_ids == ["chain-a"]
        assert membership.chain_id == "chain-a"  # backward compat property

        # List of strings
        result = mgr.join_island("island-2", "island2", ["chain-b", "chain-c"])
        assert result is True
        membership = mgr.get_island_info("island-2")
        assert membership is not None
        assert membership.chain_ids == ["chain-b", "chain-c"]
        assert membership.chain_id == "chain-b"  # first element


# ---------------------------------------------------------------------------
# B6 — RPC chain endpoints
# ---------------------------------------------------------------------------


class TestChainRPCEndpoints:
    """Test chain RPC endpoint handlers."""

    def test_list_chains_no_manager(self):
        """list_chains raises 503 when MultiChainManager not available."""
        import asyncio

        from aitbc_chain.rpc.chains import list_chains

        with patch("aitbc_chain.rpc.chains.get_multi_chain_manager", return_value=None):
            with pytest.raises(Exception) as exc_info:
                asyncio.run(list_chains())
            assert "503" in str(exc_info.value) or "Not Available" in str(exc_info.value)

    def test_start_chain_no_manager(self):
        """start_chain raises 503 when MultiChainManager not available."""
        import asyncio

        from aitbc_chain.rpc.chains import ChainActionRequest, start_chain

        with patch("aitbc_chain.rpc.chains.get_multi_chain_manager", return_value=None):
            with pytest.raises(Exception) as exc_info:
                asyncio.run(start_chain(ChainActionRequest(chain_id="test")))
            assert "503" in str(exc_info.value) or "Not Available" in str(exc_info.value)

    def test_list_chains_with_manager(self):
        """list_chains returns chain data when manager is available."""
        import asyncio

        from aitbc_chain.network.multi_chain_manager import ChainInstance, ChainStatus, ChainType
        from aitbc_chain.rpc.chains import list_chains

        mock_mgr = MagicMock()
        mock_mgr.get_all_chains.return_value = [
            ChainInstance(
                chain_id="chain-a",
                chain_type=ChainType.DEFAULT,
                status=ChainStatus.RUNNING,
                db_path=Path("/tmp/chain.db"),
                rpc_port=8006,
                p2p_port=8007,
                started_at=1234567890.0,
            )
        ]

        with patch("aitbc_chain.rpc.chains.get_multi_chain_manager", return_value=mock_mgr):
            result = asyncio.run(list_chains())

        assert result["total"] == 1
        assert result["chains"][0]["chain_id"] == "chain-a"
        assert result["chains"][0]["status"] == "running"


# ---------------------------------------------------------------------------
# AsyncMock helper (for Python < 3.8 compat, though we require 3.13)
# ---------------------------------------------------------------------------

try:
    from unittest.mock import AsyncMock
except ImportError:
    # Fallback for very old Python — should not be needed on 3.13
    AsyncMock = MagicMock  # type: ignore[assignment,misc]
