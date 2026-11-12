"""Genesis seeding, attestation gating, seal republish, and block broadcast for ``PoAProposer`` (#1867 pure-move split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

from typing import Any

from . import poa as _poa
from .poa import _PoaBaseMixin

from ..config import settings
from ..lease_tracker import lease_tracker
from ..metrics import metrics_registry, poa_broadcast_skipped_total, poa_valid_subscribers
from ..models import Account, Block
from .block_hash import compute_block_hash
from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.signature_recovery import canonical_address
from datetime import datetime
from sqlmodel import Session, select
import asyncio
import json
import time


class _OpsMixin(_PoaBaseMixin):
    async def _broadcast_block(self, block: Block, processed_txs: list[Any]) -> bool:
        """Publish a committed block to the gossip broker.

        Returns False when the stop event fires mid-broadcast — the block is
        already committed, but the caller reports the proposal as aborted.
        Broadcast failures are logged and do not fail the proposal.
        """
        # Broadcast must carry the proposer's tx_hash: importers recompute a
        # hash only when one is absent, and the recompute runs over normalized
        # (enriched) content, so hashless txs landed under different tx_hash
        # values per node — breaking every cross-node reference (v4
        # lock_tx_hashes being the first consumer).
        tx_list = [{**(tx.content or {}), "tx_hash": tx.tx_hash} for tx in processed_txs] if processed_txs else []
        gossip_topic = f"blocks.{self._config.chain_id}"
        if self._stop_event.is_set():
            return False
        payload = {
            "chain_id": self._config.chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "timestamp": block.timestamp.isoformat(),
            "tx_count": block.tx_count,
            "state_root": block.state_root,
            "bridge_state_root": block.bridge_state_root,
            "aux_state_root": block.aux_state_root,
            "signature": block.signature,
            "block_metadata": block.block_metadata,
            "transactions": tx_list,
        }
        try:
            subscribers = await lease_tracker.get_valid_subscribers(self._config.chain_id)
            subscriber_count = len(subscribers)
            poa_valid_subscribers.labels(chain_id=self._config.chain_id).set(subscriber_count)
            self._logger.info(
                "[BROADCAST] block=%s, topic=%s, valid_subscribers=%s", block.height, gossip_topic, subscriber_count
            )
            if self._stop_event.is_set():
                return False
            # v0.7.6: always publish to _poa.gossip_broker; the backend (Redis on
            # hub, WSS on remote validators) is responsible for fan-out.
            # Leases are still logged as a metric but do not gate block
            # propagation now that multiple validators may produce.
            await _poa.gossip_broker.publish(gossip_topic, payload)
            self._logger.info(
                "[BROADCAST SUCCESS] block=%s, topic=%s, subscribers=%s", block.height, gossip_topic, subscriber_count
            )
        except Exception as e:
            poa_broadcast_skipped_total.labels(chain_id=self._config.chain_id).inc()
            self._logger.error("Failed to broadcast block %s: %s", block.height, e)
        if getattr(settings, "seal_republish_enabled", False):  # #1268: flag off never touches the new path
            self._schedule_seal_republish(gossip_topic, payload)
        return True

    def _schedule_seal_republish(self, topic: str, payload: dict[str, Any]) -> None:
        """#1268: keep re-announcing a just-sealed block until it is known elsewhere.

        A single failed (or lost) publish used to leave a seal visible only on
        its proposer while the attesters that signed it sat on a vote for a
        block nobody could fetch. Flag off: nothing is scheduled.
        """
        if not getattr(settings, "seal_republish_enabled", False):
            return
        task = create_task_with_logging(self._republish_seal(topic, payload), name=f"seal_republish_{payload['height']}")
        self._republish_tasks.add(task)
        task.add_done_callback(self._republish_tasks.discard)

    def _seal_settled(self, height: int, block_hash: str) -> bool:
        """True once a child of the sealed block exists locally, or the seal was replaced."""
        with self._session_factory() as session:
            row = session.exec(
                select(Block.hash).where(Block.chain_id == self._config.chain_id).where(Block.height == height)
            ).first()
            if row is None or str(row) != block_hash:
                return True  # reorged away: re-announcing a loser would be wrong
            child = session.exec(
                select(Block.height)
                .where(Block.chain_id == self._config.chain_id)
                .where(Block.height == height + 1)
                .where(Block.parent_hash == block_hash)
            ).first()
            return child is not None

    async def _republish_seal(self, topic: str, payload: dict[str, Any]) -> None:
        interval = max(1.0, float(getattr(settings, "seal_republish_interval_seconds", 10.0)))
        deadline = time.monotonic() + float(getattr(settings, "seal_republish_max_seconds", 120.0))
        height = int(payload["height"])
        block_hash = str(payload["hash"])
        while time.monotonic() < deadline:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            if self._seal_settled(height, block_hash):
                metrics_registry.increment("seal_republish_settled_total")
                return
            if await _poa.locate_voted_block(self._config.chain_id, height, {block_hash}) is not None:
                metrics_registry.increment("seal_republish_peer_serves_total")
                return
            try:
                await _poa.gossip_broker.publish(topic, payload)
                metrics_registry.increment("seal_republished_total")
                self._logger.info("[BROADCAST] re-published unconfirmed seal %s at height %s", block_hash[:18], height)
            except Exception as exc:  # noqa: BLE001 - a failed re-publish is retried on the next tick
                self._logger.warning("seal re-publish for height %s failed: %s", height, exc)
        metrics_registry.increment("seal_republish_gave_up_total")

    def _seed_chain_parameters(self, session: Session, parameters: dict[str, Any] | None) -> None:
        """Seed ``chain_parameter`` rows from a ``parameters`` map in genesis.

        Genesis content is identical on every node — block 0's hash covers the
        genesis.json (or RPC-bootstrap) payload — so parameters seeded here
        start fleet-identical. Later changes go through GOVERNANCE_EXECUTE
        parameter_change, which is the deterministic channel. This is what
        consensus-facing values like ``bond_slash_authority`` should use
        instead of per-node env (see the 1-2 Sep slash divergence).
        """
        from ..base_models import ChainParameter, record_chain_parameter_history

        for name, value in (parameters or {}).items():
            # ``null`` in genesis is a deliberate clear ("") — str(None)
            # would store the literal "None", same trap as parameter_change.
            stored_value = "" if value is None else str(value)
            session.add(
                ChainParameter(chain_id=self._config.chain_id, parameter=str(name), value=stored_value, applied_height=0)
            )
            # Genesis parameters take effect at height 0 — record the history
            # entry so height-scoped lookups resolve them from the first block.
            record_chain_parameter_history(session, self._config.chain_id, str(name), stored_value, None, 0)
        if parameters:
            session.commit()
            self._logger.info("Seeded %d chain parameters from genesis: %s", len(parameters), sorted(parameters))

    async def _ensure_genesis_block(self) -> None:
        with self._session_factory() as session:
            genesis = session.exec(
                select(Block).where(Block.chain_id == self._config.chain_id).where(Block.height == 0).limit(1)
            ).first()
            if genesis is not None:
                if genesis.bridge_state_root is None:
                    genesis.bridge_state_root = self._empty_bridge_root()
                    session.add(genesis)
                    session.commit()
                self._logger.info(
                    "Genesis block already exists: height=%s, hash=%s, proposer=%s",
                    genesis.height,
                    genesis.hash,
                    genesis.proposer,
                )
                return
            # No RPC bootstrap: a partial genesis payload (allocations + claimed
            # hash/state_root but no canonical timestamp, parameters or
            # bridge_validators) minted a node-local block-0 timestamp that skewed
            # the proposer round and diverged the aux root. The canonical
            # document is the genesis file — fetchable over the network at
            # /agent/genesis.json — and every node must file-load it.
            self._logger.info("Loading genesis block from local file for chain %s", self._config.chain_id)
            local_genesis_data = self._load_genesis_data_from_file()
            if not local_genesis_data:
                from aitbc.constants import DATA_DIR

                self._logger.error(
                    "Genesis file not found at %s. Cannot create genesis block without genesis.json file.",
                    DATA_DIR / "data" / self._config.chain_id / "genesis.json",
                )
                raise RuntimeError(
                    f"Genesis file required but not found for chain {self._config.chain_id}: "
                    f"supply {DATA_DIR / 'data' / self._config.chain_id / 'genesis.json'} — a peer serves "
                    "the canonical document at /agent/genesis.json."
                )
            block_data = local_genesis_data.get("block", {})
            genesis_hash = local_genesis_data.get("genesis_hash") or block_data.get("hash")
            genesis_timestamp = local_genesis_data.get("timestamp") or block_data.get("timestamp")
            genesis_state_root = local_genesis_data.get("state_root") or block_data.get("state_root")
            genesis_allocations = local_genesis_data.get("allocations", block_data.get("allocations", []))
            if not genesis_hash or not genesis_timestamp or (not genesis_state_root):
                from aitbc.constants import DATA_DIR

                genesis_file = DATA_DIR / "data" / self._config.chain_id / "genesis.json"
                self._logger.error("Genesis file missing required fields: genesis_hash, timestamp, or state_root")
                raise RuntimeError(
                    f"Genesis file at {genesis_file} is missing required fields (genesis_hash, timestamp, state_root)"
                )
            try:
                if isinstance(genesis_timestamp, str):
                    timestamp = datetime.fromisoformat(genesis_timestamp)
                else:
                    timestamp = genesis_timestamp
            except Exception as e:
                self._logger.error("Failed to parse genesis timestamp: %s", e)
                raise RuntimeError(f"Invalid timestamp format in genesis file: {e}") from e
            genesis = Block(
                chain_id=self._config.chain_id,
                height=0,
                hash=genesis_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=genesis_state_root,
                bridge_state_root=self._empty_bridge_root(),
                block_metadata=json.dumps({"allocations": genesis_allocations}) if genesis_allocations else None,
            )
            session.add(genesis)
            try:
                self._verify_genesis_claims(
                    source=f"genesis file (chain {self._config.chain_id})",
                    genesis_state_root=genesis_state_root,
                    allocations=genesis_allocations,
                    genesis_hash=genesis_hash,
                    timestamp=timestamp,
                )
                self._verify_bridge_validators_claim(local_genesis_data)
                session.commit()
                self._logger.info(
                    "Successfully created genesis block from genesis.json: hash=%s, state_root=%s, timestamp=%s",
                    genesis_hash,
                    genesis_state_root,
                    timestamp,
                )
                if genesis_allocations:
                    self._create_accounts_from_allocations(session, genesis_allocations)
                    self._logger.info("Initialized %s accounts from genesis.json", len(genesis_allocations))
                self._seed_chain_parameters(session, local_genesis_data.get("parameters"))
                self._seed_bridge_validators(session, local_genesis_data)
            except Exception as e:
                self._logger.error("Failed to create genesis block from genesis.json: %s", e)
                session.rollback()
                raise
            await _poa.gossip_broker.publish(
                f"blocks.{self._config.chain_id}",
                {
                    "chain_id": self._config.chain_id,
                    "height": genesis.height,
                    "hash": genesis.hash,
                    "parent_hash": genesis.parent_hash,
                    "proposer": genesis.proposer,
                    "timestamp": genesis.timestamp.isoformat(),
                    "tx_count": genesis.tx_count,
                    "state_root": genesis.state_root,
                    "bridge_state_root": genesis.bridge_state_root,
                    "aux_state_root": genesis.aux_state_root,
                },
            )

    def _verify_genesis_claims(
        self,
        *,
        source: str,
        genesis_state_root: str,
        allocations: list[Any],
        genesis_hash: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Refuse to bootstrap from genesis claims that do not recompute (V-5).

        ``_ensure_genesis_block`` historically wrote whatever hash and state_root a
        genesis file or the (now removed) RPC bootstrap claimed. The fleet's
        genesis.json files turned out to be abandoned pre-migration stubs
        carrying a placeholder ``0x00`` root, and nothing noticed until a fresh
        node's first synced block failed its parent_hash check. Recomputing the
        claims *before* anything is committed turns that silent fork into a
        clear refusal at the moment it happens — a RuntimeError here propagates
        out of ``_ensure_genesis_block`` and refuses startup instead of writing
        a genesis the chain will reject.

        The root is rebuilt with ``StateManager.update_account`` over the
        allocation set — the same code path ``compute_state_root_full`` uses —
        evaluated before seeding, not after: ``_create_accounts_from_allocations``
        commits internally, so a post-seed check could not roll back cleanly.
        Duplicated allocation addresses are refused outright because the seeder is
        first-wins while ``update_account`` is last-wins — a file carrying dupes
        would claim a root the seeded state can never match.

        The hash check runs only when ``timestamp`` is what the block row will
        carry — the genesis file transports one, so the file path always runs it.
        """
        seen: set[str] = set()
        for alloc in allocations or []:
            addr = str(alloc.get("address", "")).strip().lower()
            if addr in seen:
                raise RuntimeError(f"Genesis {source} carries duplicated allocation address(es); refusing to bootstrap")
            seen.add(addr)

        from ..state.merkle_patricia_trie import StateManager

        state = StateManager()
        for alloc in allocations or []:
            state.update_account(str(alloc["address"]), int(alloc["balance"]), int(alloc.get("nonce", 0)))
        computed_root = "0x" + state.get_root().hex()
        if computed_root.lower() != str(genesis_state_root).lower():
            raise RuntimeError(
                f"Genesis {source} state_root mismatch: claimed {str(genesis_state_root)[:10]}… recomputes to "
                f"{computed_root[:10]}… over {len(seen)} allocation(s); refusing to bootstrap"
            )

        if genesis_hash is not None and timestamp is not None:
            computed_hash = compute_block_hash(
                self._config.chain_id,
                0,
                "0x00",
                timestamp,
                [],
                "genesis",
                state_root=genesis_state_root,
                bridge_state_root=self._empty_bridge_root(),
            )
            if computed_hash.lower() != genesis_hash.lower():
                raise RuntimeError(
                    f"Genesis {source} hash mismatch: claimed {str(genesis_hash)[:10]}… recomputes to "
                    f"{computed_hash[:10]}… over the fields the block row would carry; refusing to bootstrap"
                )

    def _verify_bridge_validators_claim(self, genesis_data: dict[str, Any]) -> None:
        """Refuse a genesis whose ``bridge_validators`` rows don't match their digest.

        ``genesis_hash`` binds the allocation set but has no validator term, so
        without this check two nodes could start from files whose validator
        rows silently differ. The digest is verified *before* the genesis block
        commits; a file without the keys is a legacy document and is skipped.
        """
        from ..genesis_builder import GenesisBuildError, verify_bridge_validators_claim

        try:
            verify_bridge_validators_claim(genesis_data, chain_id=self._config.chain_id)
        except GenesisBuildError as e:
            raise RuntimeError(f"Genesis file (chain {self._config.chain_id}): {e}") from e

    def _seed_bridge_validators(self, session: Session, genesis_data: dict[str, Any]) -> None:
        """Insert ``bridge_validators`` rows carried by the genesis document.

        Runs after the block-0 commit — i.e. after ``init_db``'s schema
        creation and before the proposers start (block 1). ``bridge_validators``
        is not one of the aux-root-fingerprinted tables, so each node writing
        its own ``registered_at`` wall time cannot diverge consensus. Rows go
        through the same ``insert_bridge_validator`` the register route uses,
        so seeded and registered rows are identical by construction.
        """
        rows = genesis_data.get("bridge_validators") or []
        if not rows:
            return
        from ..cross_chain.bridge_validator import insert_bridge_validator

        for row in rows:
            insert_bridge_validator(
                session,
                chain_id=self._config.chain_id,
                address=str(row["address"]).lower(),
                public_key=str(row["public_key"]),
                epoch=int(row.get("epoch", 0)),
            )
        session.commit()
        self._logger.info("Seeded %d bridge validators from genesis", len(rows))

    def _load_genesis_data_from_file(self) -> dict[str, Any]:
        """Load complete genesis data from local file.

        The path is the per-chain candidate ``DATA_DIR/data/<chain_id>/genesis.json``
        (``aitbc.constants.DATA_DIR`` honours ``AITBC_DATA_DIR``). The chain-less
        ``data/genesis.json`` candidate ``ChainSettings.get_genesis_candidates``
        lists first is deliberately not used: a stray shared file would shadow the
        per-chain one. Byte-identical to the old hardcoded path when
        ``AITBC_DATA_DIR`` is unset. Resolved lazily so tests can patch the
        constant.
        """
        from aitbc.constants import DATA_DIR

        genesis_path = DATA_DIR / "data" / self._config.chain_id / "genesis.json"
        if not genesis_path.exists():
            return {}
        try:
            with open(genesis_path) as f:
                genesis_data = json.load(f)
            return genesis_data  # type: ignore[no-any-return]
        except Exception as e:
            self._logger.warning("Failed to load genesis file: %s", e)
            return {}

    def _create_accounts_from_allocations(self, session: Session, allocations: list[Any]) -> None:
        """Create Account entries from allocation data."""
        created = 0
        for alloc in allocations:
            addr = alloc["address"]
            balance = int(alloc["balance"])
            nonce = int(alloc.get("nonce", 0))
            existing = session.exec(
                select(Account).where(Account.chain_id == self._config.chain_id).where(Account.address == addr)
            ).first()
            if existing:
                continue
            account = Account(chain_id=self._config.chain_id, address=addr, balance=balance, nonce=nonce)
            session.add(account)
            created += 1
        session.commit()
        self._logger.info("Created %s accounts from genesis allocations", created)

    def _effective_min_attestations(self, block: Block, active_validators: list[str], configured_min: int) -> int:
        """Effective attestation floor — the #693 seal guard.

        Remote actives clamp the configured floor (unchanged). Remotes
        configured but none active: HOLD the floor — counted attestations
        below it stall the proposer instead of sealing a block every
        follower rejects. No remotes configured: floor 0 — a genuine
        single-validator island keeps sealing.
        """
        proposer_c = canonical_address(block.proposer)
        remote_active = sum(1 for a in active_validators if canonical_address(a) != proposer_c)
        if remote_active:
            effective_min = max(0, min(configured_min, remote_active))
            if configured_min > effective_min:
                self._logger.warning(
                    "Configured min_attestations %d reduced to %d because only %d non-proposer validators are active",
                    configured_min,
                    effective_min,
                    remote_active,
                )
            return effective_min
        if self._remote_validators_configured(proposer_c):
            if configured_min:
                self._logger.error(
                    "No non-proposer validators are active but remotes are configured; "
                    "holding min_attestations floor at %d instead of degrading to 0 (#693)",
                    configured_min,
                )
            return configured_min
        return 0

    async def _collect_and_gate_attestations(
        self,
        block: Block,
        block_hash: str,
        metadata_dict: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        round_number: int | None = None,
    ) -> bool:
        """Collect gossip attestations and apply the multi-validator gate.

        Populates ``metadata_dict`` with ``pbft_certificate`` and
        ``attestations`` when present. Returns False when the attestation
        minimum is unmet and the PBFT certificate cannot cover it — the caller
        owns the session rollback.

        The PBFT certificate is resolved *before* the attestation gate,
        because it can satisfy it. sync_validator._validate_attestations
        checks the certificate instead of the attestations list whenever one
        is present, so a block carrying a commit quorum is accepted by every
        follower no matter how many gossip attestations came back. Requiring
        a second, independent signature round here was therefore stricter
        than the network itself: PBFT would reach quorum and the block would
        still be dropped, stalling the chain on a check no verifier applies.
        """
        pbft_certificate: list[dict[str, Any]] = []
        if self._pbft_consensus:
            pbft_certificate = self._pbft_consensus.get_certificate(block_hash)
            if pbft_certificate:
                metadata_dict["pbft_certificate"] = pbft_certificate

        if self._multi_validator:
            attestations = await self._collect_attestations(block, transactions=transactions, round_number=round_number)
            configured_min = getattr(settings, "multi_validator_min_attestations", 0)
            # _collect_attestations already ran the #693 anomaly re-read, so the
            # participants here are the post-recovery view.
            effective_min = self._effective_min_attestations(
                block, self._multi_validator.get_consensus_participants(), configured_min
            )
            if attestations:
                metadata_dict["attestations"] = attestations
            if effective_min and len(attestations) < effective_min:
                commit_count = self._certificate_commit_count(
                    pbft_certificate, block_hash, self._multi_validator.get_consensus_participants()
                )
                if commit_count < effective_min:
                    self._logger.warning(
                        "Not enough attestations for multi-validator block %s: got %d attestation(s) "
                        "and %d PBFT commit(s), need %d",
                        block.height,
                        len(attestations),
                        commit_count,
                        effective_min,
                    )
                    await self._publish_abandon(block, block_hash)
                    return False
                self._logger.info(
                    "Block %s carries %d attestation(s), below the %d minimum, but its PBFT certificate "
                    "holds %d commits; proceeding on the certificate",
                    block.height,
                    len(attestations),
                    effective_min,
                    commit_count,
                )
        return True
