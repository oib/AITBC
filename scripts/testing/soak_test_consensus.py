#!/usr/bin/env python3
"""
Testnet soak test for v0.7.5 MultiValidatorPoA + PBFT consensus.

Runs a simulated multi-node network for a configurable duration (default 48h)
with ≥3 validator nodes and 1 Byzantine validator. Continuously produces blocks,
monitors consensus health, and reports failures.

Usage:
    ./venv/bin/python scripts/testing/soak_test_consensus.py
    ./venv/bin/python scripts/testing/soak_test_consensus.py --duration 48 --nodes 4 --byzantine 1
    ./venv/bin/python scripts/testing/soak_test_consensus.py --duration 1 --dry-run  # quick smoke test

Requirements:
    - blockchain-node src on PYTHONPATH (handled automatically)
    - multi_validator_consensus_enabled=true in config (set automatically)

Exit codes:
    0 — soak test passed (no chain splits, no consensus failures)
    1 — soak test failed (chain split, consensus stall, or slashing failure)
    2 — configuration error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure blockchain-node src is on path
_BLOCKCHAIN_SRC = Path(__file__).resolve().parents[2] / "apps" / "blockchain-node" / "src"
if str(_BLOCKCHAIN_SRC) not in sys.path:
    sys.path.insert(0, str(_BLOCKCHAIN_SRC))

# Ensure aitbc shared core is on path
_AITBC_ROOT = Path(__file__).resolve().parents[2]
if str(_AITBC_ROOT) not in sys.path:
    sys.path.insert(0, str(_AITBC_ROOT))

from eth_keys import keys  # noqa: E402

from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.consensus.multi_validator_poa import (  # noqa: E402
    MultiValidatorPoA,
    ValidatorRole,
)
from aitbc_chain.consensus.pbft import PBFTConsensus  # noqa: E402


class _SoakBus:
    """Synchronous in-process PBFT transport for the soak.

    Each published message is delivered straight into the other nodes'
    ``handle_incoming_message``, so a round actually exercises the
    signature check, the scheduled-proposer check, the membership gate
    and the prepare/commit quorums (the InMemoryGossipBackend only
    queued messages nobody subscribed to).  ``offline`` holds validator
    addresses that must not receive anything — the Byzantine crash model.
    """

    def __init__(self) -> None:
        self.nodes: list[PBFTConsensus] = []
        self.offline: set[str] = set()

    async def publish(self, topic: str, msg_data: dict[str, Any]) -> None:
        for node in self.nodes:
            if node._local_validator == msg_data.get("sender"):
                continue
            if node._local_validator in self.offline:
                continue
            await node.handle_incoming_message(msg_data)


@dataclass
class SoakTestConfig:
    """Configuration for the soak test."""

    duration_hours: float = 48.0
    num_nodes: int = 4
    num_byzantine: int = 1
    round_timeout_seconds: float = 5.0
    block_interval_seconds: float = 2.0
    report_interval_minutes: float = 15.0
    chain_id: str = "soak-test-chain"
    dry_run: bool = False
    output_file: str = ""


@dataclass
class NodeState:
    """State tracker for a single node in the soak test."""

    node_id: str
    address: str
    consensus: MultiValidatorPoA
    pbft: PBFTConsensus
    is_byzantine: bool = False
    blocks_produced: int = 0
    blocks_validated: int = 0
    consensus_failures: int = 0
    view_changes: int = 0
    slashing_events: int = 0
    last_block_hash: str = ""
    last_block_height: int = 0
    start_time: float = 0.0


@dataclass
class SoakTestReport:
    """Final report from the soak test."""

    config: SoakTestConfig
    start_time: float = 0.0
    end_time: float = 0.0
    total_blocks: int = 0
    total_consensus_rounds: int = 0
    total_view_changes: int = 0
    total_slashing_events: int = 0
    total_consensus_failures: int = 0
    chain_splits: int = 0
    consensus_stalls: int = 0
    max_sync_lag: int = 0
    node_reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def passed(self) -> bool:
        return self.chain_splits == 0 and self.consensus_stalls == 0 and self.total_consensus_failures == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "duration_hours": self.config.duration_hours,
                "num_nodes": self.config.num_nodes,
                "num_byzantine": self.config.num_byzantine,
                "block_interval_seconds": self.config.block_interval_seconds,
                "chain_id": self.config.chain_id,
                "dry_run": self.config.dry_run,
            },
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round(self.duration_seconds, 2),
            "total_blocks": self.total_blocks,
            "total_consensus_rounds": self.total_consensus_rounds,
            "total_view_changes": self.total_view_changes,
            "total_slashing_events": self.total_slashing_events,
            "total_consensus_failures": self.total_consensus_failures,
            "chain_splits": self.chain_splits,
            "consensus_stalls": self.consensus_stalls,
            "max_sync_lag": self.max_sync_lag,
            "passed": self.passed,
            "node_reports": self.node_reports,
            "timeline": self.timeline,
        }


class ConsensusSoakTest:
    """Multi-node consensus soak test runner."""

    def __init__(self, config: SoakTestConfig) -> None:
        self.config = config
        self.nodes: dict[str, NodeState] = {}
        self.gossip_backend = _SoakBus()
        self.report = SoakTestReport(config=config)
        self._stop_event = asyncio.Event()
        self._block_height = 0
        self._parent_hash = "0x" + "0" * 64

    def _setup_nodes(self) -> None:
        """Create validator nodes with PBFT consensus instances."""
        n_validators = self.config.num_nodes
        n_byzantine = self.config.num_byzantine

        assert n_validators >= 3, "Soak test requires at least 3 nodes"
        assert n_byzantine >= 0, "Byzantine count cannot be negative"
        assert n_byzantine <= (n_validators - 1) // 3, (
            f"Too many Byzantine nodes ({n_byzantine}) for {n_validators} validators. "
            f"PBFT tolerates at most (n-1)/3 = {(n_validators - 1) // 3} Byzantine validators."
        )

        # Real validator keys — the intake path verifies signatures and a
        # scheduled proposer that cannot sign is simply dropped.
        keyspec: list[tuple[str, str]] = []
        for _ in range(n_validators):
            pk = keys.PrivateKey(secrets.token_bytes(32))
            keyspec.append((pk.public_key.to_checksum_address(), pk.to_hex()))

        # Create per-node PBFT instances sharing the dispatch bus
        for i, (addr, pk_hex) in enumerate(keyspec):
            node_id = f"node-{i}"
            is_byzantine = i < n_byzantine

            # Each node gets its own consensus view (they share validator set).
            # load_state=False keeps the soak hermetic: the ambient
            # VALIDATOR_SET / DB state of the host must not leak fleet
            # validators into the proposer rotation.
            node_consensus = MultiValidatorPoA(self.config.chain_id, load_state=False)
            for a, _ in keyspec:
                node_consensus.add_validator(a, 1000.0)
                node_consensus.validators[a].role = ValidatorRole.PROPOSER

            pbft = PBFTConsensus(
                node_consensus,
                private_key=pk_hex,
                chain_id=self.config.chain_id,
                local_validator=addr,
            )
            pbft.set_gossip_backend(self.gossip_backend)
            self.gossip_backend.nodes.append(pbft)

            self.nodes[node_id] = NodeState(
                node_id=node_id,
                address=addr,
                consensus=node_consensus,
                pbft=pbft,
                is_byzantine=is_byzantine,
                start_time=time.time(),
            )

    async def _produce_block(self) -> None:
        """Produce a single block across all nodes."""
        self._block_height += 1
        height = self._block_height
        block_hash = f"0xblock_{height:08d}"

        self.report.total_consensus_rounds += 1

        # The scheduled proposer for this height drives ONE real PBFT round:
        # pre-prepare -> prepare quorum -> commit quorum over the bus.
        any_consensus = next(iter(self.nodes.values())).consensus
        proposer_addr = any_consensus.select_proposer(height, 0)
        proposer_node = next(
            (n for n in self.nodes.values() if n.address == proposer_addr),
            None,
        )
        if proposer_node is None:
            self.report.total_consensus_failures += 1
            self._log_event("consensus_failure", f"no scheduled proposer at height {height}", height)
            self.report.total_blocks += 1
            self._parent_hash = block_hash
            return

        # Byzantine crash model: every 10th block the Byzantine nodes go
        # deaf — the bus withholds all delivery to them. While f <=
        # (n-1)/3 the honest remainder still forms both quorums.
        self.gossip_backend.offline = (
            {n.address for n in self.nodes.values() if n.is_byzantine}
            if self.config.num_byzantine and height % 10 == 0
            else set()
        )
        if self.gossip_backend.offline:
            self._log_event("byzantine_fault", f"Byzantine nodes offline for height {height}", height)

        try:
            await proposer_node.pbft.propose_and_wait(
                proposer_addr,
                block_hash,
                timeout=self.config.round_timeout_seconds,
                sequence=height,
                view=0,
            )
        except Exception as e:
            proposer_node.consensus_failures += 1
            self.report.total_consensus_failures += 1
            self._log_event(
                "consensus_error",
                f"Proposer {proposer_node.node_id} error at height {height}: {e}",
                height,
            )

        # The round verdict is read from honest nodes' commit quorums — a
        # deaf Byzantine proposer times out on its own side even when the
        # honest remainder committed fine.
        key = f"{height}:0"
        for node in self.nodes.values():
            if node.is_byzantine:
                continue
            if len(node.pbft.state.committed_messages.get(key, [])) >= node.pbft.required_messages:
                node.blocks_produced += 1
                node.blocks_validated += 1
                node.last_block_hash = block_hash
                node.last_block_height = height
            else:
                node.consensus_failures += 1
                self.report.total_consensus_failures += 1
                self._log_event(
                    "consensus_failure",
                    f"Node {node.node_id} reached no commit quorum at height {height}",
                    height,
                )

        self.report.total_blocks += 1
        self._parent_hash = block_hash

    def _check_chain_consistency(self) -> None:
        """Check that all honest nodes agree on the latest block."""
        honest_heights: dict[str, int] = {}
        for node in self.nodes.values():
            if not node.is_byzantine:
                honest_heights[node.node_id] = node.last_block_height

        if not honest_heights:
            return

        heights = list(honest_heights.values())
        max_h = max(heights)
        min_h = min(heights)
        lag = max_h - min_h

        if lag > self.report.max_sync_lag:
            self.report.max_sync_lag = lag

        # Chain split: honest nodes disagree by more than 2 blocks
        if lag > 2:
            self.report.chain_splits += 1
            self._log_event(
                "chain_split",
                f"Chain split detected: max_height={max_h}, min_height={min_h}, lag={lag}",
                self._block_height,
            )

    def _check_consensus_liveness(self) -> None:
        """Check that consensus is making progress (not stalled)."""
        if self._block_height == 0:
            return

        current_time = time.time()
        for node in self.nodes.values():
            if node.is_byzantine:
                continue
            # If no block produced in last 60 seconds, consider it stalled
            time_since_last = current_time - node.start_time
            if node.blocks_produced == 0 and time_since_last > 60:
                self.report.consensus_stalls += 1
                self._log_event(
                    "consensus_stall",
                    f"Node {node.node_id} has produced 0 blocks in {time_since_last:.0f}s",
                    self._block_height,
                )

    def _log_event(self, event_type: str, message: str, height: int) -> None:
        """Log an event to the timeline."""
        event = {
            "timestamp": time.time(),
            "elapsed_seconds": time.time() - self.report.start_time,
            "type": event_type,
            "message": message,
            "block_height": height,
        }
        self.report.timeline.append(event)
        print(f"  [{event_type.upper()}] {message}")

    def _periodic_report(self) -> str:
        """Generate a periodic status report."""
        elapsed = time.time() - self.report.start_time
        elapsed_h = elapsed / 3600.0
        remaining_h = self.config.duration_hours - elapsed_h

        honest_blocks = sum(n.blocks_produced for n in self.nodes.values() if not n.is_byzantine)
        byzantine_slashed = sum(n.slashing_events for n in self.nodes.values())

        status = (
            f"  [REPORT] Elapsed: {elapsed_h:.1f}h / {self.config.duration_hours:.1f}h "
            f"| Remaining: {remaining_h:.1f}h "
            f"| Blocks: {self.report.total_blocks} "
            f"| Honest blocks: {honest_blocks} "
            f"| Failures: {self.report.total_consensus_failures} "
            f"| Splits: {self.report.chain_splits} "
            f"| Stalls: {self.report.consensus_stalls} "
            f"| Slashing: {byzantine_slashed} "
            f"| Max lag: {self.report.max_sync_lag}"
        )
        print(status)
        return status

    async def run(self) -> SoakTestReport:
        """Run the soak test for the configured duration."""
        print("=" * 80)
        print("AITBC v0.7.5 Consensus Soak Test")
        print("=" * 80)
        print(f"  Duration: {self.config.duration_hours}h")
        print(f"  Nodes: {self.config.num_nodes} ({self.config.num_byzantine} Byzantine)")
        print(f"  Chain ID: {self.config.chain_id}")
        print(f"  Block interval: {self.config.block_interval_seconds}s")
        print(f"  Dry run: {self.config.dry_run}")
        print("-" * 80)

        # Enable multi-validator consensus
        original_setting = settings.multi_validator_consensus_enabled
        settings.multi_validator_consensus_enabled = True

        try:
            self._setup_nodes()
            print(f"  Setup complete: {len(self.nodes)} nodes created")
            for nid, node in self.nodes.items():
                tag = "BYZANTINE" if node.is_byzantine else "HONEST"
                print(f"    {nid}: {tag}")
            print("-" * 80)

            self.report.start_time = time.time()
            duration_seconds = self.config.duration_hours * 3600
            report_interval = self.config.report_interval_minutes * 60
            last_report = time.time()

            # Set up signal handler for graceful shutdown
            def _signal_handler(sig, frame):
                print("\n  [SIGNAL] Received shutdown signal, stopping gracefully...")
                self._stop_event.set()

            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)

            while not self._stop_event.is_set():
                elapsed = time.time() - self.report.start_time
                if elapsed >= duration_seconds:
                    print(f"\n  [DONE] Duration reached ({elapsed / 3600:.1f}h)")
                    break

                # Produce a block
                await self._produce_block()

                # Health checks
                self._check_chain_consistency()
                self._check_consensus_liveness()

                # Periodic report
                if time.time() - last_report >= report_interval:
                    self._periodic_report()
                    last_report = time.time()

                # Wait for next block interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.block_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass  # normal — continue to next block

        finally:
            settings.multi_validator_consensus_enabled = original_setting

        self.report.end_time = time.time()

        # Collect per-node reports
        for nid, node in self.nodes.items():
            self.report.node_reports[nid] = {
                "is_byzantine": node.is_byzantine,
                "blocks_produced": node.blocks_produced,
                "blocks_validated": node.blocks_validated,
                "consensus_failures": node.consensus_failures,
                "view_changes": node.pbft._view_change_count,
                "slashing_events": node.slashing_events,
                "last_block_hash": node.last_block_hash,
                "last_block_height": node.last_block_height,
                "uptime_seconds": time.time() - node.start_time,
            }
            self.report.total_view_changes += node.pbft._view_change_count

        return self.report

    def print_final_report(self, report: SoakTestReport) -> None:
        """Print the final soak test report."""
        print("\n" + "=" * 80)
        print("SOAK TEST FINAL REPORT")
        print("=" * 80)
        print(f"  Duration: {report.duration_seconds / 3600:.2f}h")
        print(f"  Total blocks: {report.total_blocks}")
        print(f"  Total consensus rounds: {report.total_consensus_rounds}")
        print(f"  Total view changes: {report.total_view_changes}")
        print(f"  Total slashing events: {report.total_slashing_events}")
        print(f"  Total consensus failures: {report.total_consensus_failures}")
        print(f"  Chain splits: {report.chain_splits}")
        print(f"  Consensus stalls: {report.consensus_stalls}")
        print(f"  Max sync lag: {report.max_sync_lag}")
        print()
        print("  Per-Node Summary:")
        for nid, nr in report.node_reports.items():
            tag = "BYZANTINE" if nr["is_byzantine"] else "HONEST"
            print(f"    {nid} ({tag}):")
            print(f"      blocks_produced: {nr['blocks_produced']}")
            print(f"      consensus_failures: {nr['consensus_failures']}")
            print(f"      view_changes: {nr['view_changes']}")
            print(f"      slashing_events: {nr['slashing_events']}")
            print(f"      last_block_height: {nr['last_block_height']}")

        print()
        if report.passed:
            print("  ✅ SOAK TEST PASSED — No chain splits, no stalls, no failures")
        else:
            print("  ❌ SOAK TEST FAILED")
            if report.chain_splits:
                print(f"     - {report.chain_splits} chain split(s) detected")
            if report.consensus_stalls:
                print(f"     - {report.consensus_stalls} consensus stall(s) detected")
            if report.total_consensus_failures:
                print(f"     - {report.total_consensus_failures} consensus failure(s)")

        print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="AITBC v0.7.5 Consensus Soak Test (48h, ≥3 nodes, 1 Byzantine)")
    parser.add_argument(
        "--duration",
        type=float,
        default=48.0,
        help="Soak test duration in hours (default: 48)",
    )
    parser.add_argument(
        "--nodes",
        type=int,
        default=4,
        help="Number of validator nodes (default: 4, minimum: 3; 4 needed to tolerate 1 Byzantine)",
    )
    parser.add_argument(
        "--byzantine",
        type=int,
        default=1,
        help="Number of Byzantine nodes (default: 1)",
    )
    parser.add_argument(
        "--block-interval",
        type=float,
        default=2.0,
        help="Block production interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--report-interval",
        type=float,
        default=15.0,
        help="Report interval in minutes (default: 15.0)",
    )
    parser.add_argument(
        "--chain-id",
        type=str,
        default="soak-test-chain",
        help="Chain ID for the test (default: soak-test-chain)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output file for JSON report (default: stdout only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Quick 1-minute smoke test (overrides --duration to 0.0167h = 1min)",
    )
    args = parser.parse_args()

    config = SoakTestConfig(
        duration_hours=0.0167 if args.dry_run else args.duration,
        num_nodes=args.nodes,
        num_byzantine=args.byzantine,
        block_interval_seconds=args.block_interval,
        report_interval_minutes=args.report_interval,
        chain_id=args.chain_id,
        dry_run=args.dry_run,
        output_file=args.output,
    )

    if config.num_nodes < 3:
        print("ERROR: Soak test requires at least 3 nodes", file=sys.stderr)
        return 2

    if config.num_byzantine >= config.num_nodes // 3 + 1:
        print(
            f"ERROR: Too many Byzantine nodes ({config.num_byzantine}) "
            f"for {config.num_nodes} validators. PBFT tolerates at most "
            f"{(config.num_nodes - 1) // 3} Byzantine validators.",
            file=sys.stderr,
        )
        return 2

    soak_test = ConsensusSoakTest(config)
    report = asyncio.run(soak_test.run())
    soak_test.print_final_report(report)

    # Save JSON report
    report_json = json.dumps(report.to_dict(), indent=2)
    if config.output_file:
        Path(config.output_file).write_text(report_json)
        print(f"\n  Report saved to: {config.output_file}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
