from __future__ import annotations
import asyncio
import time
import traceback
import json
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .multi_validator_poa import MultiValidatorPoA

from . import abandon, unavail
from .block_hash import compute_block_hash
from .pbft import PBFTConsensus
from .remote_attestation import RemoteAttestationService, attestation_lock_window_seconds as attestation_lock_window_seconds
from .vote_fetch import contention_hold, kick_pull, locate_voted_block
from .vote_journal import (
    get_vote_journal,
    valve_open,
    vote_journal_enabled,
)

from sqlalchemy import text
from sqlmodel import Session, select

from aitbc.async_tasks import create_task_with_logging
from aitbc.network import SharedHttpClient as SharedHttpClient
from aitbc.parallel import DependencyGraph, ParallelExecutor as ParallelExecutor

from ..config import ProposerConfig, settings
from ..gossip import gossip_broker
from ..lease_tracker import lease_tracker as lease_tracker
from ..logger import get_logger
from ..metrics import (
    block_height,
    metrics_registry,
)
from ..models import Account, Block, CrossChainTransfer
from ..models import Transaction
from ..base_models import _to_ait_address
from aitbc.crypto.signature_recovery import canonical_address
from ..state.pure_state_transition import (
    SEQUENTIAL_ONLY_TX_TYPES,
    _determine_tx_type,
    _escrow_address,
    apply_delta_to_map as apply_delta_to_map,
    apply_deltas_to_db as apply_deltas_to_db,
    compute_state_delta as compute_state_delta,
    extract_read_write_sets,
)
from ..state.state_root_utils import compute_state_root_full as _compute_state_root
from ..cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from ..state.block_deltas import BlockDeltaJournal
from ..state import side_root_shadow
from ..state.bridge_credit import (
    BRIDGE_AUTHORITY_TX_TYPES,
)
from ..state.state_transition import (
    _bridge_release_authority,
    _ensure_account,
    get_block_version,
    get_block_version_for_height,
    get_state_transition,
    use_account_nonce_override,
)

logger = get_logger(__name__)

# Transaction types whose side effects (pools, stakes, GPU tables, etc.) are not
# modeled by the pure/parallel delta map. They must be applied through the
# full StateTransition.apply_transaction sequential path to keep state roots
# and side-effect tables consistent across proposer and follower nodes.
# Transaction types whose side effects the pure/parallel delta map cannot
# model — the canonical list lives in
# pure_state_transition.SEQUENTIAL_ONLY_TX_TYPES (the pure path returns
# requires_sequential=True for exactly these types). A block containing any
# of them stays on the sequential path.
_SEQUENTIAL_ONLY_TX_TYPES = SEQUENTIAL_ONLY_TX_TYPES

_METRIC_KEY_SANITIZE = re.compile("[^a-zA-Z0-9_]")

# #1741: minimum monotonic interval between wall-clock-skew error logs —
# the proposer loop calls the detector every iteration, so the journal must
# not get one CRITICAL per tick while the skew persists.
_CLOCK_SKEW_WARN_INTERVAL_SECONDS = 60.0


def _escrow_addresses_from_txs(tx_datas: list[dict[str, Any]]) -> set[str]:
    """Return the per-escrow addresses for any ESCROW_RELEASE/REFUND txs."""
    escrow_addrs: set[str] = set()
    for tx_data in tx_datas:
        tx_type = _determine_tx_type(tx_data)
        if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            payload = tx_data.get("payload", {}) or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            job_id = payload.get("job_id", "")
            if job_id:
                escrow_addrs.add(_escrow_address(job_id))
    return escrow_addrs


# v0.7.3: Governance transaction payload validation
_GOV_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "GOVERNANCE_PROPOSE": ("proposal_id", "title", "proposer"),
    "GOVERNANCE_VOTE": ("proposal_id", "voter", "vote_type"),
    "GOVERNANCE_EXECUTE": ("proposal_id", "executor"),
}


def _validate_governance_payload(tx_type: str, payload: dict[str, Any]) -> list[str]:
    """Validate a governance transaction payload. Returns list of error messages (empty if valid).

    Checks that the payload contains all required fields for the given governance tx type.
    Uses ``aitbc.governance.onchain.validate_governance_payload`` when available (Agent A's
    shared SDK), falling back to inline validation for resilience.
    """
    # Try to use the shared SDK validation (Agent A's A3) when available
    errors: list[str] | None = None
    try:
        from aitbc.governance.onchain import validate_governance_payload as sdk_validate
        from aitbc.governance.types import GovernanceTxType

        gov_type = GovernanceTxType(tx_type)
        errors = list(sdk_validate(gov_type, payload))
    except Exception:
        pass  # SDK not available — use inline validation

    if errors is None:
        if _GOV_REQUIRED_FIELDS.get(tx_type) is None:
            return [f"Unknown governance tx type: {tx_type}"]
        errors = _inline_governance_errors(tx_type, payload)

    # A parameter_change must carry its value key explicitly — ``value: null``
    # records a deliberate clear (""), but a missing ``value`` key would be
    # stored as the literal string "None" and reach resolvers as a nonsense
    # address. Runs for both the SDK and inline paths.
    if tx_type == "GOVERNANCE_EXECUTE":
        execution_payload = payload.get("execution_payload")
        if (
            isinstance(execution_payload, dict)
            and execution_payload.get("action", "parameter_change") == "parameter_change"
            and "value" not in execution_payload
        ):
            errors.append("parameter_change missing 'value' key")

    return errors


def _inline_governance_errors(tx_type: str, payload: dict[str, Any]) -> list[str]:
    """Inline fallback validation used when the shared SDK is unavailable."""
    errors: list[str] = []
    for field_name in _GOV_REQUIRED_FIELDS[tx_type]:
        if field_name not in payload:
            errors.append(f"missing required field: {field_name}")
        elif not payload[field_name]:
            errors.append(f"empty required field: {field_name}")

    # Validate vote_type values for GOVERNANCE_VOTE
    if tx_type == "GOVERNANCE_VOTE" and "vote_type" in payload:
        vote_type = str(payload["vote_type"]).lower()
        if vote_type not in ("for", "against", "abstain"):
            errors.append(f"invalid vote_type: {vote_type} (must be 'for', 'against', or 'abstain')")
    return errors


def _sanitize_metric_suffix(value: str) -> str:
    sanitized = _METRIC_KEY_SANITIZE.sub("_", value).strip("_")
    return sanitized or "unknown"


def _rejection_metadata(reason: str, height: int, timestamp: datetime) -> str:
    """Serialise why a drained mempool tx was rejected at apply time (#669)."""
    return json.dumps(
        {
            "rejected_reason": reason,
            "rejected_at_height": height,
            "rejected_at": timestamp.isoformat(),
        }
    )


def _attestation_lock_peer_bases(peer_urls) -> list[str]:
    from .proposal_freshness import peer_base_url

    bases: list[str] = []
    for u in peer_urls:
        if u.startswith(("http://", "https://")):
            bases.append(u)
        else:
            base = peer_base_url(u)
            if base:
                bases.append(base)
    return bases


class _SeqTxContext:
    """Per-block shared state threaded through the sequential tx helpers.

    ``processed_txs``/``changed_addresses``/``pending_records`` are the same
    accumulators the monolithic loop used; ``pending_records`` stays deferred
    — Transaction rows are added to the session only after ALL state
    transitions succeed, because adding them inside per-tx savepoints let
    new rows leak when the outer transaction rolled back (e.g. PBFT fail)."""

    def __init__(
        self,
        session: Session,
        account_map: dict[str, Account],
        existing_tx_map: dict[str, int],
        next_height: int,
        timestamp: datetime,
        block_version: int,
        rejected: list[tuple[Any, str]] | None,
    ) -> None:
        self.session = session
        self.account_map = account_map
        self.existing_tx_map = existing_tx_map
        self.next_height = next_height
        self.timestamp = timestamp
        self.block_version = block_version
        self.rejected = rejected
        self.processed_txs: list[Any] = []
        self.changed_addresses: set[str] = set()
        self.pending_records: list[Transaction] = []


def _seq_reject(ctx: _SeqTxContext, tx: Any, reason: str) -> None:
    if ctx.rejected is not None:
        ctx.rejected.append((tx, reason))


def _parallel_build_graph(pending_txs: list[Any]):
    """Build the tx dependency graph and the tx_hash -> tx index."""
    graph = DependencyGraph()
    tx_by_hash: dict[str, Any] = {}
    for idx, tx in enumerate(pending_txs):
        read_set, write_set = extract_read_write_sets(tx.content)
        graph.add_transaction(tx.tx_hash, read_set, write_set, index=idx)
        tx_by_hash[tx.tx_hash] = tx
    return graph, tx_by_hash


def _parallel_bridge_authority(
    session: Session, chain_id: str, next_height: int, block_version: int, pending_txs
) -> str | None:
    """Resolve the bridge release authority once per block, only when a
    v5+ block actually contains a bridge-signed tx."""
    if block_version >= 5 and any(_determine_tx_type(tx.content) in BRIDGE_AUTHORITY_TX_TYPES for tx in pending_txs):
        return _bridge_release_authority(session, chain_id, next_height)
    return None


def _parallel_tx_data_map(
    pending_txs: list[Any], account_map: dict[str, Account], block_version: int
) -> dict[str, dict[str, Any]]:
    """Prepare tx_data for each tx (with nonce set from account_map)."""
    tx_data_map: dict[str, dict[str, Any]] = {}
    for tx in pending_txs:
        tx_data = tx.content.copy()
        sender = _to_ait_address(tx_data.get("from", ""))
        sender_account = account_map.get(sender)
        # Bridge credits sign their semantic fields at issuance (v5) —
        # overwriting the nonce with the pseudo-sender account's would
        # invalidate the authority signature.
        if _determine_tx_type(tx_data) not in ("BRIDGE_RELEASE", "BRIDGE_REFUND") and use_account_nonce_override(
            tx_data, block_version
        ):
            tx_data["nonce"] = sender_account.nonce if sender_account else 0
        tx_data["value"] = tx_data.get("amount", 0)
        tx_data_map[tx.tx_hash] = tx_data
    return tx_data_map


def _parallel_refresh_group_nonces(
    group, tx_data_map: dict[str, dict[str, Any]], account_map: dict[str, Account], block_version: int
) -> None:
    """Update nonces from account_map before processing each group
    (conflicting txs in later groups need updated nonces from earlier groups)."""
    for tx_hash in group:
        tx_data = tx_data_map[tx_hash]
        sender = _to_ait_address(tx_data.get("from", ""))
        sender_account = account_map.get(sender)
        if (
            sender_account
            and _determine_tx_type(tx_data) not in ("BRIDGE_RELEASE", "BRIDGE_REFUND")
            and use_account_nonce_override(tx_data, block_version)
        ):
            tx_data["nonce"] = sender_account.nonce


class _ProposalReleaseLedger:
    """#1300 §3 release-map bookkeeping for one proposal attempt.

    Tracks which of this attempt's reserved hashes have been accounted for and
    emits ``release_reservations`` calls with the exit-appropriate reason.
    Hashes whose ``existing_tx_map`` entry has a real block height are
    reclassified ``already_sealed`` (dup-skip, F1). Kept at module level so
    ``_propose_block`` stays under the C901 ratchet.
    """

    def __init__(
        self,
        mempool: Any,
        chain_id: str,
        reserved_hashes: Iterable[str],
        existing_tx_map: dict[str, int],
        owner_id: str,
    ) -> None:
        self._mempool = mempool
        self._chain_id = chain_id
        self._reserved = set(reserved_hashes)
        self._released: set[str] = set()
        self._existing_tx_map = existing_tx_map
        self._owner_id = owner_id
        self._release = getattr(mempool, "release_reservations", None)

    def release_hashes(self, hashes: Iterable[str], reason: str) -> None:
        todo = [h for h in hashes if h in self._reserved and h not in self._released]
        if not todo:
            return
        self._released.update(todo)
        if self._release is None:
            return
        sealed_like = {h for h in todo if self._existing_tx_map.get(h) is not None}
        normal = [h for h in todo if h not in sealed_like]
        if normal:
            self._release(self._chain_id, normal, reason, owner_id=self._owner_id)
        if sealed_like:
            self._release(self._chain_id, sorted(sealed_like), "already_sealed", owner_id=self._owner_id)

    def release_leftovers(self, reason: str = "cancelled") -> None:
        self.release_hashes(self._reserved - self._released, reason)


def _active_consensus_domain(height: int | None, domain: str) -> str | None:
    """#1298: return ``domain`` when the block height is at/above the armed
    domain-separation activation height, else None (legacy preimage)."""
    activation = getattr(settings, "consensus_domain_separation_height", None)
    if activation is None or height is None or height < activation:
        return None
    return domain


def _sign_consensus(message: dict[str, Any], private_key: str, domain: str | None) -> str:
    """Sign ``message`` under ``domain`` when armed, else the legacy preimage."""
    from aitbc.crypto.consensus_signing import sign_consensus_message, sign_consensus_message_domain

    if domain is None:
        return sign_consensus_message(message, private_key)
    return sign_consensus_message_domain(message, private_key, domain)


class _PoaBaseMixin:
    """Core lifecycle, attestation, journal, hashing, and PBFT plumbing for ``PoAProposer`` (#1867 pure-move split)."""

    if TYPE_CHECKING:

        def _assemble_proposal_block(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _broadcast_block(self, block: Block, processed_txs: list[Any]) -> bool: ...
        def _collect_proposal_txs(self, *args: Any, **kwargs: Any) -> Any: ...
        def _ensure_genesis_block(self, *args: Any, **kwargs: Any) -> Any: ...
        def _evict_mempool_txs(self, *args: Any, **kwargs: Any) -> Any: ...
        def _honor_prior_votes(self, *args: Any, **kwargs: Any) -> Any: ...
        def _note_same_hash_retry(self, *args: Any, **kwargs: Any) -> Any: ...
        def _passes_early_gates(self, *args: Any, **kwargs: Any) -> Any: ...
        def _peek_same_hash_retry(self, *args: Any, **kwargs: Any) -> Any: ...
        def _persist_rejected_txs(self, *args: Any, **kwargs: Any) -> Any: ...
        def _process_proposal_txs(self, *args: Any, **kwargs: Any) -> Any: ...
        def _reject_if_all_invalid(self, *args: Any, **kwargs: Any) -> Any: ...
        def _resolve_post_collect_proposal(self, *args: Any, **kwargs: Any) -> Any: ...
        def _resolve_proposal_head(self, *args: Any, **kwargs: Any) -> Any: ...
        def _run_journaled_gates(self, *args: Any, **kwargs: Any) -> Any: ...
        def _same_hash_retry_horizon_seconds(self, *args: Any, **kwargs: Any) -> Any: ...
        def _select_round_proposer(self, *args: Any, **kwargs: Any) -> Any: ...
        def _stamp_rejected_tx_metadata(self, *args: Any, **kwargs: Any) -> Any: ...
        def _tx_snapshot_key(self, *args: Any, **kwargs: Any) -> Any: ...

    def __init__(
        self,
        *,
        config: ProposerConfig,
        session_factory: Callable[[], AbstractContextManager[Session]],
        consensus: MultiValidatorPoA | None = None,
        sync_manager: Any | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._logger = get_logger(__name__)
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._propose_phase: str | None = None
        self._last_proposer_id: str | None = None
        self._last_block_timestamp: datetime | None = None
        self._multi_validator: MultiValidatorPoA | None = consensus
        self._sync_manager: Any | None = sync_manager
        self._validator_keys: dict[str, str] = {}
        self._remote_attestation: RemoteAttestationService | None = None
        self._republish_tasks: set[asyncio.Task[None]] = set()  # #1268 seal re-announcers
        # #1281: unlock justification produced by the armed evidence valve,
        # keyed by proposal height — consumed by _record_proposal_vote,
        # the attest_request, and block_metadata.unlock_justification.
        self._unlock_justifications: dict[int, dict[str, Any]] = {}
        # #1298: (height, parent_hash, timestamp, not_after_epoch, tx_key)
        # of the last assembled proposal, reused for same-hash retries while
        # inside the attestation-lock/header-age horizon. Parent and tx-set
        # binding: a reorg at the same height or a drifted mempool drain
        # would assemble a different hash under the pinned timestamp — a
        # rival inside attesters' lock window — so both invalidate the pin.
        self._same_hash_retry: tuple[int, Any, datetime, float, tuple[Any, ...]] | None = None
        # Warn-once latch for a computed same-hash retry horizon <= 0 — the
        # feature is silently inert in that configuration, so it must be
        # visible in the journal instead of looking like ordinary churn.
        self._same_hash_retry_horizon_warned = False
        # Pre-proposal freshness gate (2026-09-27 stale-head fork fix). The
        # verdict is cached per local head for a few seconds — never carried
        # into a later round. _freshness_fetch/_monotonic exist so tests can
        # inject a stub instead of hitting HTTP or real time.
        self._freshness_fetch: Any = None
        self._monotonic: Callable[[], float] = time.monotonic
        self._freshness_cache_key: tuple[int, str] | None = None
        self._freshness_cache_ok: bool = True
        self._freshness_cache_expires: float = 0.0
        # peer base -> local height when we kicked a pull from it
        self._freshness_pulls: dict[str, int] = {}
        # peer base -> monotonic deadline it is quarantined from the ahead check
        self._freshness_quarantined: dict[str, float] = {}
        # gate name -> last head key / height we warned about having no peers (#1260)
        self._no_peers_warned: dict[str, Any] = {}
        # #1741: monotonic timestamp of the last wall-clock-skew error log.
        self._clock_skew_warned_at = 0.0
        if self._multi_validator is not None:
            self._load_validator_set()
            self._load_validator_keys()
        elif self._multi_validator is None and getattr(settings, "multi_validator_consensus_enabled", False):
            if getattr(settings, "validator_set", ""):
                from .multi_validator_poa import get_consensus

                self._multi_validator = get_consensus(self._config.chain_id)
                self._load_validator_set()
                self._load_validator_keys()
            else:
                self._logger.warning(
                    "multi_validator_consensus_enabled is True but validator_set is empty; "
                    "falling back to single proposer for chain %s",
                    self._config.chain_id,
                )
        self._pbft_consensus: PBFTConsensus | None = None
        if settings.pbft_consensus_enabled and self._multi_validator is not None and self._validator_keys:
            self._pbft_consensus = PBFTConsensus(
                self._multi_validator,
                private_key=settings.proposer_key or "",
                chain_id=self._config.chain_id,
                local_validator=self._config.proposer_id,
                sync_manager=self._sync_manager,
            )
            from ..gossip import gossip_broker

            self._pbft_consensus.set_gossip_backend(gossip_broker)
            self._logger.info(
                "PBFT consensus initialized for chain %s with local validator %s",
                self._config.chain_id,
                self._config.proposer_id,
            )

        if self._multi_validator is not None and self._validator_keys:
            self._remote_attestation = RemoteAttestationService(
                self._config.chain_id, self._validator_keys, session_factory=self._session_factory
            )
            if self._sync_manager is not None:
                # #1268: lets the attester's fetch-before-unlock pull a voted block.
                self._remote_attestation.pull_hook = self._sync_manager.pull_from_peer
            self._logger.info(
                "Remote attestation service initialized for chain %s with %s local key(s)",
                self._config.chain_id,
                len(self._validator_keys),
            )

    def _fetch_chain_head(self) -> Block | None:
        """Fetch the current chain head block from the database."""
        with self._session_factory() as session:
            return session.exec(
                select(Block).where(Block.chain_id == self._config.chain_id).order_by(text("height DESC")).limit(1)
            ).first()

    def _load_validator_set(self) -> None:
        """Load the validator set from settings into MultiValidatorPoA."""
        if not self._multi_validator or not settings.validator_set:
            return
        try:
            import json
            from decimal import Decimal

            from .multi_validator_poa import ValidatorRole

            validators = json.loads(settings.validator_set)
            env_addresses = set()
            for v in validators:
                address = v.get("address")
                stake = v.get("stake", "1000")
                if address:
                    self._multi_validator.add_validator(address, Decimal(str(stake)))
                    # Promote to active validator so it is eligible for proposer selection
                    self._multi_validator.validators[address].role = ValidatorRole.VALIDATOR
                    env_addresses.add(address)
            # Row-persisted validators dropped from VALIDATOR_SET must leave the
            # rotation — env is the membership source of truth.
            for addr in self._multi_validator.deactivate_absent_from(env_addresses):
                self._logger.info("Validator %s absent from VALIDATOR_SET — marked inactive", addr)
            self._multi_validator.save_state()
            self._logger.info(
                "Loaded %s validators into MultiValidatorPoA for chain %s",
                len(validators),
                self._config.chain_id,
            )
        except Exception as e:
            self._logger.warning("Failed to load validator set: %s", e)

    def _load_validator_keys(self) -> None:
        """Load the local validator keys from settings."""
        if not settings.validator_keys:
            return
        try:
            import json

            self._validator_keys = json.loads(settings.validator_keys)
            self._logger.info(
                "Loaded %s local validator keys for chain %s",
                len(self._validator_keys),
                self._config.chain_id,
            )
        except Exception as e:
            self._logger.warning("Failed to load validator keys: %s", e)

    def _select_proposer(self, block_height: int, round_number: int = 0) -> str | None:
        """Select the proposer for a block height and round.

        When multi-validator consensus is enabled, use MultiValidatorPoA
        round-robin selection from the active validator set. Otherwise fall
        back to the single proposer_id from ProposerConfig.
        """
        if self._multi_validator:
            proposer = self._multi_validator.select_proposer(block_height, round_number)
            if proposer:
                return proposer
            self._logger.warning("MultiValidatorPoA returned no proposer for height %s", block_height)
        return self._config.proposer_id

    def _proposer_round(self, parent_timestamp: datetime | None, block_timestamp: datetime) -> int:
        """Rounds this height has gone without a block; 0 is the scheduled slot.

        Derived from block timestamps rather than from local state, so the
        proposer and every validator that later checks the block agree on the
        round without exchanging view-change messages.
        """
        if not self._multi_validator:
            return 0
        from ..config import settings as _settings
        from .multi_validator_poa import proposer_round

        return proposer_round(parent_timestamp, block_timestamp, getattr(_settings, "consensus_proposer_round_seconds", 120))

    def _empty_bridge_root(self) -> str:
        """Return the bridge event trie root for a block with no lock events."""
        from ..state.merkle_patricia_trie import MerklePatriciaTrie

        return "0x" + MerklePatriciaTrie().get_root().hex()

    def _sign_block_hash_for(self, proposer: str, block: Block) -> str:
        """Sign the canonical block header with the private key of the given proposer."""
        private_key = self._validator_keys.get(proposer) or getattr(settings, "proposer_key", None)
        if not private_key:
            self._logger.debug("No private key for proposer %s; block signature omitted", proposer)
            return ""
        try:
            from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_PROPOSAL

            domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_PROPOSAL)
            return _sign_consensus(self._block_header_message(block), private_key, domain)
        except Exception as e:
            self._logger.warning("Failed to sign block header for %s: %s", proposer, e)
            return ""

    @staticmethod
    def _certificate_commit_count(
        certificate: list[dict[str, Any]], block_hash: str, members: set[str] | frozenset[str] | list[str]
    ) -> int:
        """Count distinct set members that committed to ``block_hash`` in a PBFT certificate.

        Counted the same way ``sync_validator._validate_pbft_certificate`` counts
        them -- distinct senders of commit messages bound to this block hash,
        proposer included -- so the proposer never rejects a block that every
        follower would accept. Only senders in ``members`` (the active consensus
        participant set, any address spelling) count: a commit from an address
        outside the set is not a vote no matter how valid its signature.
        Signatures are not re-verified here: these commits were verified by the
        local PBFT engine before it accepted them.
        """
        member_set = {canonical_address(a) for a in members}
        seen: set[str] = set()
        for commit in certificate:
            if not isinstance(commit, dict) or commit.get("message_type") != "commit":
                continue
            sender = commit.get("sender", "")
            if not sender:
                continue
            commit_block_hash = commit.get("block_hash", "")
            if commit_block_hash and commit_block_hash != block_hash:
                continue
            sender_c = canonical_address(sender)
            if sender_c not in member_set:
                continue
            seen.add(sender_c)
        return len(seen)

    def _consensus_participants_anomaly_checked(self) -> list[str]:
        """Consensus participants after the #693 anomaly re-read.

        Never sizes an attestation round off a poisoned empty view.
        """
        if self._multi_validator is None:
            return list(self._validator_keys.keys())
        self._multi_validator.reload_state_if_anomalous()
        return self._multi_validator.get_consensus_participants()

    def _remote_validators_configured(self, proposer_c: str) -> bool:
        """True when consensus members other than ``proposer_c`` are configured.

        ``proposer_c`` must already be canonicalised. ``VALIDATOR_SET`` is the
        membership source of truth, so it is consulted first; the registered
        (persisted) validator set is the fallback when env is unset or
        unparseable. Distinguishes "single-validator island" from "remotes
        configured but missing from the active view" for the #693 floor guard.
        """
        raw = getattr(settings, "validator_set", "") or ""
        if raw.strip():
            try:
                env = json.loads(raw)
            except Exception:
                env = None
            if isinstance(env, list):
                return any(
                    isinstance(v, dict) and bool(v.get("address")) and canonical_address(v["address"]) != proposer_c
                    for v in env
                )
        if self._multi_validator is not None:
            return any(canonical_address(addr) != proposer_c for addr in self._multi_validator.validators)
        return False

    async def _collect_attestations(
        self,
        block: Block,
        transactions: list[dict[str, Any]] | None = None,
        round_number: int | None = None,
    ) -> list[dict[str, str]]:
        """Collect canonical header signatures from local and remote validators.

        Local attestations are produced immediately. Remote attestations are
        requested over the gossip broker and collected up to the configured
        timeout. Duplicates are de-duplicated by validator address.

        ``round_number`` is the proposer round this node selected for the
        block — the same deterministic derivation attesters apply to the
        attest_request header. #1298 T7a: at/above the armed
        domain-separation height the round is inside the signed attestation
        payload unconditionally (round_lock does not gate it), so local
        attestations must bind it exactly like remote ones or every importer
        rejects them.
        """
        attestations: list[dict[str, str]] = []
        seen: set[str] = set()

        active_validators = self._consensus_participants_anomaly_checked()
        configured_min = getattr(settings, "multi_validator_min_attestations", 0)
        # The configured minimum cannot exceed the number of validators that are
        # allowed to attest (everyone except the proposer).  This prevents an
        # impossible quorum from stalling block production when the validator
        # set is small or a member is offline.
        effective_min = max(0, min(configured_min, max(0, len(active_validators) - 1)))

        attestations = self._local_attestations(block, round_number)
        seen.update(canonical_address(att["validator"]) for att in attestations)

        if self._remote_attestation is not None:
            min_remote = max(0, effective_min - len(attestations))
            if min_remote > 0 or effective_min > 0:
                # Give slow validators more time when more responses are needed.
                base_timeout = getattr(settings, "multi_validator_attestation_timeout_seconds", 1.0)
                timeout = max(float(base_timeout), 0.5 * min_remote + float(base_timeout))
                try:
                    remote = await self._remote_attestation.collect_attestations(
                        block,
                        min_remote,
                        timeout=timeout,
                        transactions=transactions,
                        unlock_justification=self._unlock_justifications.get(block.height),
                    )
                    for att in remote:
                        addr = canonical_address(att["validator"])
                        if addr not in seen:
                            attestations.append(att)
                            seen.add(addr)
                        else:
                            self._logger.debug("Dropping duplicate remote attestation from %s", att["validator"])
                except Exception as e:
                    self._logger.warning("Failed to collect remote attestations: %s", e)

        return attestations

    def _local_attestations(self, block: Block, round_number: int | None) -> list[dict[str, str]]:
        """Sign this node's validator keys over the block header.

        #1298 T7a: at/above the armed domain-separation height the round is
        inside the signed attestation payload unconditionally (round_lock
        does not gate it), so local attestations must bind it exactly like
        remote ones or every importer rejects them.
        """
        attestations: list[dict[str, str]] = []
        if not self._validator_keys:
            return attestations
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

        domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_ATTESTATION)
        att_round: int | None = None
        if domain is not None:
            att_round = round_number
            if att_round is None and self._remote_attestation is not None:
                # No round threaded through (direct/test callers): derive
                # it exactly the way remote attesters will.
                att_round = self._remote_attestation._collect_round_for_block(block)
            if att_round is None:
                # Underivable round: sign the unbound domain preimage —
                # verifiers still accept it (mixed round-bound/unbound
                # handling) — rather than dropping the attestation.
                self._logger.warning(
                    "Attestation round underivable for block %s at height %s — signing unbound",
                    getattr(block, "hash", "")[:18],
                    block.height,
                )
        message = self._block_header_message(block)
        if att_round is not None:
            message["round"] = att_round
        for address, private_key in self._validator_keys.items():
            if canonical_address(address) == canonical_address(block.proposer):
                continue
            try:
                signature = _sign_consensus(message, private_key, domain)
                attestation: dict[str, str] = {"validator": address, "signature": signature}
                if att_round is not None:
                    # Import-side verification rebuilds the same
                    # round-bound preimage from this hint (or derives it).
                    attestation["round"] = str(att_round)
                attestations.append(attestation)
            except Exception as e:
                self._logger.warning("Failed to collect attestation from %s: %s", address, e)
        return attestations

    async def start(self) -> None:
        if self._task is not None:
            return
        from ..config import settings

        # Answering attestation requests is a validator duty, not a proposer duty:
        # a validator with ENABLE_BLOCK_PRODUCTION=false still has to sign other
        # validators' headers. Started before the block-production check because
        # it used to sit after it, so on a four-validator fleet where only two
        # nodes produce blocks the proposer could collect exactly one attestation
        # -- below MULTI_VALIDATOR_MIN_ATTESTATIONS=2 -- and every block was
        # dropped even though PBFT had reached quorum.
        if self._remote_attestation is not None:
            await self._remote_attestation.start()
            self._logger.info("Remote attestation listener started for chain %s", self._config.chain_id)

        if not getattr(settings, "enable_block_production", True):
            self._logger.info("Block production disabled, skipping PoA proposer loop")
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        # #1298: surface the effective same-hash retry horizon at startup —
        # a 0 here means every retry stamps a fresh hash (the fleet-wide
        # silent-disable the fh1298-leg drill caught).
        retry_enabled = getattr(settings, "proposer_same_hash_retry_enabled", False)
        retry_horizon = self._same_hash_retry_horizon_seconds() if retry_enabled else 0.0
        metrics_registry.set_gauge("proposer_same_hash_retry_horizon_seconds", retry_horizon)
        self._logger.info(
            "Same-hash retry horizon %.1fs (enabled=%s)",
            retry_horizon,
            retry_enabled,
        )
        await self._ensure_genesis_block()
        head = self._fetch_chain_head()
        if head is not None:
            self._last_block_timestamp = head.timestamp
            self._logger.info("Initialized last block timestamp from head", extra={"height": head.height})
        self._stop_event.clear()
        self._task = create_task_with_logging(self._run_loop(), name="poa_proposer_loop")

    async def stop(self) -> None:
        for republish_task in list(self._republish_tasks):  # #1268: seal re-announcers
            republish_task.cancel()
        # Mirrors start(): the attestation listener runs even when the proposer
        # loop does not, so it must be stopped before the "no loop" early return
        # or a non-producing validator would leak its gossip subscription.
        if self._remote_attestation is not None:
            try:
                await asyncio.wait_for(self._remote_attestation.stop(), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._logger.warning("Remote attestation listener did not stop within timeout")
            self._logger.info("Remote attestation listener stopped for chain %s", self._config.chain_id)
        if self._task is None:
            return
        self._logger.info("Stopping PoA proposer loop")
        self._stop_event.set()
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._logger.warning("PoA proposer loop did not stop within timeout")
        self._task = None
        self._same_hash_retry = None
        if self._multi_validator is not None:
            self._multi_validator.save_state()

    async def _run_loop(self) -> None:
        await asyncio.sleep(self._config.interval_seconds)
        from ..config import settings

        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        while not self._stop_event.is_set():
            if self._stop_event.is_set():
                break
            try:
                proposed = await self._propose_block_with_watchdog()
                if proposed:
                    await self._wait_until_next_slot()
                elif block_generation_mode == "hybrid":
                    check_interval = self._config.interval_seconds / 4
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=check_interval)
                    except TimeoutError:
                        pass
                else:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.interval_seconds)
                    except TimeoutError:
                        pass
            except Exception as exc:
                self._logger.error("Failed to propose block: %s\n%s", exc, traceback.format_exc())
                await asyncio.sleep(1.0)

    async def _propose_block_with_watchdog(self, *, watchdog_after: float | None = None) -> bool:
        """Run one proposal iteration under a silence watchdog.

        The 1804 freeze is the reason this exists: the proposer task hung at
        20:09:31 on 31 Aug with no error, no traceback, and no further log for
        ~16h — every wait inside the pipeline was individually bounded, but
        nothing observed the iteration *itself* stalling. An iteration that
        outlives this threshold is a stalled proposer, not an idle one, and the
        journal should say so.

        `watchdog_after` is public only for tests; production should leave it at
        the default computed from `interval_seconds`.
        """
        if watchdog_after is None:
            watchdog_after = max(60.0, self._config.interval_seconds * 4)
        task = asyncio.ensure_future(self._propose_block())

        async def _watch() -> None:
            await asyncio.sleep(watchdog_after)
            if not task.done():
                phase = self._propose_phase or "unknown"
                self._logger.error(
                    "[PROPOSE] proposal iteration still running after %.0fs on chain %s "
                    "(phase=%s) — the proposer is stalled, not idle; check gossip, sync, and PBFT state",
                    watchdog_after,
                    self._config.chain_id,
                    phase,
                )
                metrics_registry.increment("poa_proposer_stalled_iterations_total")
                metrics_registry.increment(f"poa_proposer_stalled_iterations_total_phase_{phase}")

        watcher = asyncio.ensure_future(_watch())
        try:
            return await task
        finally:
            watcher.cancel()

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        now = datetime.now(UTC)
        head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
        elapsed = (now - head_timestamp).total_seconds()
        sleep_for = max(self._config.interval_seconds - elapsed, 0.1)
        if sleep_for <= 0:
            sleep_for = 0.1
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
        except TimeoutError:
            return

    async def _ensure_synced_before_proposal(self) -> bool:
        """Wait until SyncManager reports a small enough gap, or timeout.

        Returns True if it is safe to propose, False if the node is too far
        behind and catch-up did not complete in time.
        """
        if self._sync_manager is None or not settings.sync_manager_enabled:
            return True
        status = self._sync_manager.get_sync_status(self._config.chain_id)
        max_gap = getattr(settings, "sync_manager_max_proposal_gap", 2)
        if status.get("gap", 0) <= max_gap:
            return True
        self._logger.warning(
            "[PROPOSE] Sync gap %s exceeds %s for chain %s, forcing catch-up before proposal",
            status.get("gap"),
            max_gap,
            self._config.chain_id,
        )
        await self._sync_manager.force_catch_up(self._config.chain_id)
        timeout = getattr(settings, "sync_manager_proposal_sync_timeout", 30)
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._sync_manager.get_sync_status(self._config.chain_id)
            if status.get("gap", 0) <= max_gap:
                return True
            try:
                await asyncio.wait_for(asyncio.sleep(1), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        self._logger.warning("[PROPOSE] Timed out waiting for sync on chain %s, skipping proposal", self._config.chain_id)
        return False

    def _reapply_parent_block(self, session: Session, parent: Block) -> bool:
        """Re-apply a parent block's transactions to bring local account state forward.

        Multi-validator PoA can select a validator that has the parent block in its
        database but has not yet applied the parent's state transition (for example
        because the block arrived through gossip while the validator was about to
        propose). The local `state_root` then lags behind the canonical parent
        `state_root`, and the next block would be built on stale state.

        This fallback loads the parent's recorded transactions and re-runs the state
        transition. It is idempotent when the local state is actually behind, because
        the function is only reached when ``_compute_state_root`` disagrees with the
        parent header.
        """
        state_transition = get_state_transition()
        state_transition.reset_processed_cache()
        chain_id = self._config.chain_id
        tx_recs = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.block_height == parent.height,
            )
        ).all()
        if not tx_recs:
            self._logger.warning(
                "[PROPOSE] Parent block %s has no transactions and local state root %s does not match parent %s; cannot repair",
                parent.height,
                _compute_state_root(session, chain_id),
                parent.state_root,
            )
            return False
        # Re-apply under a savepoint: a failed repair must not leave flushed
        # rows in the session — a caller that continues with this session
        # would otherwise commit a half-repaired state. The `with` form also
        # covers an exception mid-loop: a bare begin_nested() would leave the
        # savepoint open. Failure exits still roll back explicitly — a clean
        # `with` exit would release the savepoint over half-applied work.
        repair_version = get_block_version(parent, parent.height)
        with session.begin_nested() as repair:
            for tx_rec in tx_recs:
                sender = _to_ait_address(tx_rec.sender or "")
                recipient = _to_ait_address(tx_rec.recipient or "")
                # v22 (CONSENSUS-STATE-001, #1169): no pre-apply sender insert —
                # apply_transaction owns account creation on its success paths,
                # matching the importer and build paths.
                if sender and repair_version < 22:
                    _ensure_account(session, chain_id, sender)
                # Do not create the recipient account here, matching the import
                # path (sync_block_import) and the build path below:
                # apply_transaction ensures the recipient itself on the paths
                # that credit it. Pre-creating added a phantom leaf for
                # zero-value types (GPU_MARKET offers carry to=0x0000…0000), so
                # a parent carrying that shape could never recompute to its own
                # recorded root — repair always failed on it (bc-2 fork at 1462).
                env = tx_rec.envelope if isinstance(tx_rec.envelope, dict) else None
                if env:
                    # Re-apply the signed original: rebuilding from row columns
                    # drops the signature, which the v9 apply gate rejects.
                    tx_data = dict(env)
                    tx_data["tx_hash"] = tx_rec.tx_hash
                    if "amount" in tx_data:
                        tx_data["value"] = tx_data["amount"]
                    tx_data.setdefault("signature", "")
                else:
                    tx_data = {
                        "from": sender,
                        "to": recipient,
                        "amount": tx_rec.value,
                        "value": tx_rec.value,
                        "fee": tx_rec.fee,
                        "nonce": tx_rec.nonce,
                        "type": (tx_rec.type or "TRANSFER").upper(),
                        "payload": tx_rec.payload or {},
                        "signature": "",
                    }
                # skip_dedup: these txs are already recorded in the transaction
                # table — that is where we loaded them from — so the admission
                # replay check would reject the re-apply it exists to perform.
                success, msg = state_transition.apply_transaction_guarded(
                    session,
                    chain_id,
                    tx_data,
                    tx_rec.tx_hash,
                    block_version=repair_version,
                    block_height=parent.height,
                    block_time=parent.timestamp,
                    skip_dedup=True,
                )
                if not success:
                    self._logger.error(
                        "[PROPOSE] Failed to re-apply parent tx %s at height %s: %s",
                        tx_rec.tx_hash,
                        parent.height,
                        msg,
                    )
                    repair.rollback()
                    return False
            session.flush()
            recomputed = _compute_state_root(session, chain_id)
            if recomputed != parent.state_root:
                self._logger.error(
                    "[PROPOSE] Parent block %s state still mismatched after re-apply: expected %s, got %s",
                    parent.height,
                    parent.state_root,
                    recomputed,
                )
                repair.rollback()
                return False
        self._logger.info(
            "[PROPOSE] Re-applied parent block %s; local state now matches %s",
            parent.height,
            parent.state_root,
        )
        return True

    async def _propose_block(self) -> bool:
        # C-1: per-phase tracing. The 1804 freeze showed that a silent hang
        # between heartbeat lines is impossible to diagnose from logs alone.
        # Each phase now logs its start and duration so the journal shows
        # exactly which await blocked if the proposer stalls again.
        chain = self._config.chain_id
        self._propose_phase = "idle"
        _t0 = time.time()
        self._propose_phase = "early_gates"
        self._logger.debug("[PROPOSE:%s] phase=early_gates start", chain)
        mempool = await self._passes_early_gates()
        self._logger.debug("[PROPOSE:%s] phase=early_gates done %.3fs", chain, time.time() - _t0)
        if mempool is None:
            return False
        with self._session_factory() as session:
            _t1 = time.time()
            self._propose_phase = "resolve_head"
            resolved = self._resolve_proposal_head(session)
            self._logger.debug("[PROPOSE:%s] phase=resolve_head done %.3fs", chain, time.time() - _t1)
            if resolved is None:
                return False
            head, next_height, parent_hash, interval_seconds = resolved
            retry_cand = self._peek_same_hash_retry(next_height, parent_hash)
            timestamp = retry_cand[2] if retry_cand is not None else datetime.now(UTC)
            if session is not None:
                # Journal every mutation this proposal makes so a later fork
                # resolution can undo it — the same journal the import path keeps.
                BlockDeltaJournal.attach(session, chain, next_height)
            # v0.7.6: Determine the intended proposer before draining the
            # mempool or touching account state. This prevents a node from
            # consuming transactions, creating Transaction records, or
            # mutating balances when it is not this validator's turn to
            # propose.
            selected = self._select_round_proposer(head, next_height, timestamp)
            if selected is None:
                return False
            proposer, round_number = selected
            if await self._honor_prior_votes(next_height, round_number, proposer):
                return False
            self._propose_phase = "collect_txs"
            _t2 = time.time()
            reservation_owner = self._reservation_owner_for(proposer)
            pending_txs, account_map, existing_tx_map, reserved_hashes = self._collect_proposal_txs(
                session,
                mempool,
                reservation_owner=reservation_owner,
                reservation_proposer=proposer,
                reservation_height=next_height,
                reservation_round=round_number,
            )
            # #1300 §3 release map: every exit below accounts for the hashes
            # this attempt reserved; the finally is the BaseException safety
            # net (CancelledError included — the outer except Exception at the
            # watchdog level does not catch it).
            ledger = _ProposalReleaseLedger(
                mempool, self._config.chain_id, reserved_hashes, existing_tx_map, reservation_owner
            )
            try:
                resolved_tx = await self._resolve_post_collect_proposal(
                    head, next_height, timestamp, proposer, round_number, retry_cand, pending_txs
                )
                if resolved_tx is None:
                    ledger.release_hashes((tx.tx_hash for tx in pending_txs), "post_collect_abort")
                    return False
                timestamp, proposer, round_number = resolved_tx
                # DRAIN-SKIP-SILENT-1 (#669): every drained tx the apply path
                # refuses is collected here and written back as status='rejected'
                # so the submitter's hash query surfaces a terminal outcome instead
                # of the record vanishing with the mempool entry.
                rejected_txs: list[tuple[Any, str]] = []
                processed_txs, changed_addresses, ok = self._process_proposal_txs(
                    session, pending_txs, account_map, existing_tx_map, next_height, timestamp, rejected_txs
                )
                self._logger.debug("[PROPOSE:%s] phase=collect_txs done %.3fs", chain, time.time() - _t2)
                if not ok:
                    # The apply path already rolled the session back; commit the
                    # rejection records on their own so they survive the abort.
                    self._persist_rejected_txs(session, rejected_txs, next_height, timestamp, commit=True)
                    ledger.release_hashes((tx.tx_hash for tx, _ in rejected_txs), "apply_rejected")
                    ledger.release_hashes((tx.tx_hash for tx in pending_txs), "apply_abort")
                    self._evict_mempool_txs(mempool, [tx for tx, _ in rejected_txs])
                    return False
                if self._reject_if_all_invalid(session, pending_txs, processed_txs):
                    self._persist_rejected_txs(session, rejected_txs, next_height, timestamp, commit=True)
                    ledger.release_hashes((tx.tx_hash for tx, _ in rejected_txs), "apply_rejected")
                    ledger.release_hashes((tx.tx_hash for tx in pending_txs), "all_invalid_abort")
                    self._evict_mempool_txs(mempool, [tx for tx, _ in rejected_txs])
                    return False
                # Success path: the rows join the proposal's own transaction and
                # commit (or roll back) with the block.
                self._persist_rejected_txs(session, rejected_txs, next_height, timestamp, commit=False)
                _t3 = time.time()
                self._propose_phase = "assemble_block"
                block, block_hash = self._assemble_proposal_block(
                    session, next_height, parent_hash, timestamp, processed_txs, proposer
                )
                self._note_same_hash_retry(next_height, parent_hash, timestamp, self._tx_snapshot_key(pending_txs))
                self._logger.debug("[PROPOSE:%s] phase=assemble_block done %.3fs", chain, time.time() - _t3)
                # v0.7.2: sign the canonical block header here, before the gates —
                # the attest_request built inside _run_consensus_gates carries
                # block.signature as its proposer_signature, so it must exist at
                # request-build time, not only post-commit (#1156). The signed
                # message is the fixed 7-field header; block_metadata stamped
                # after signing stays valid.
                block.signature = self._sign_block_hash_for(proposer, block)
                metadata_dict: dict[str, Any] = {}
                _t4 = time.time()
                self._propose_phase = "consensus_gates"
                self._logger.info(
                    "[PROPOSE:%s] phase=consensus_gates start height=%s round=%s", chain, next_height, round_number
                )
                if not await self._run_journaled_gates(
                    session,
                    block,
                    block_hash,
                    proposer,
                    round_number,
                    next_height,
                    metadata_dict,
                    transactions=[{**(tx.content or {}), "tx_hash": tx.tx_hash} for tx in processed_txs],
                ):
                    self._logger.warning("[PROPOSE:%s] phase=consensus_gates failed %.3fs", chain, time.time() - _t4)
                    ledger.release_hashes((tx.tx_hash for tx, _ in rejected_txs), "apply_rejected")
                    ledger.release_hashes((tx.tx_hash for tx in pending_txs), "gate_abort")
                    self._evict_mempool_txs(mempool, [tx for tx, _ in rejected_txs])
                    return False
                self._logger.debug("[PROPOSE:%s] phase=consensus_gates done %.3fs", chain, time.time() - _t4)
                # v0.25.7: stamp the state-transition rule version so followers can
                # replay this block with the same rules that produced its state_root.
                metadata_dict["state_transition_version"] = get_block_version_for_height(next_height)
                # R14-M1 (#1248): publish the apply-rejected identities so followers
                # can release the dead (sender, nonce) slots instead of letting them
                # squat until mempool_entry_ttl. block_metadata is outside the
                # signed header and the block hash, so this cannot affect consensus.
                self._stamp_rejected_tx_metadata(metadata_dict, rejected_txs)
                # #1281: the sealed block carries its unlock justification so
                # late validators and auditors can verify the valve release
                # post-hoc. Additive field; absent for ordinary proposals.
                self._attach_unlock_justification(next_height, metadata_dict)
                block.block_metadata = json.dumps(metadata_dict)

                self._commit_and_record_block(session, block, proposer, interval_seconds, timestamp)
                _t5 = time.time()
                self._propose_phase = "broadcast"
                self._logger.debug("[PROPOSE:%s] phase=broadcast start", chain)
                result = await self._broadcast_block(block, processed_txs)
                self._logger.debug(
                    "[PROPOSE:%s] phase=broadcast done %.3fs total=%.3fs", chain, time.time() - _t5, time.time() - _t0
                )
                self._propose_phase = None
                # Commit ack reached: sealed txs' reservations die here; pool
                # rows are swept by reconcile_sealed. Rejected rows are
                # terminal — evict them and release their markers.
                ledger.release_hashes((tx.tx_hash for tx in processed_txs), "sealed")
                ledger.release_hashes((tx.tx_hash for tx, _ in rejected_txs), "apply_rejected")
                ledger.release_hashes((tx.tx_hash for tx in pending_txs), "sealed")
                self._evict_mempool_txs(mempool, [tx for tx, _ in rejected_txs])
                return result
            finally:
                ledger.release_leftovers("cancelled")

    def _own_addresses(self) -> set[str]:
        """Canonical addresses of every validator key this node holds."""
        return {canonical_address(a) for a in self._validator_keys}

    def _attach_unlock_justification(self, next_height: int, metadata_dict: dict[str, Any]) -> None:
        """#1281: move a pending valve justification onto block_metadata."""
        unlock_just = self._unlock_justifications.pop(next_height, None)
        if unlock_just is not None:
            metadata_dict["unlock_justification"] = unlock_just

    async def _honor_vote_journal(self, next_height: int, proposer: str) -> bool:
        """True while a live journal vote of ``proposer`` suppresses a proposal.

        #1268: a fresh proposal always hashes differently from any vote this
        validator already cast at the height, so any live entry conflicts. The
        suppression is durable (restart-safe) and has no wall-clock expiry;
        before the liveness valve may open, the voted block is looked up on
        the mesh and pulled if a peer serves it, so the head advances onto it
        instead of racing it. Flag off: returns False without touching the
        journal.
        """
        if not vote_journal_enabled():
            return False
        # #1281: a stale justification from an aborted attempt must never
        # leak onto a later proposal at this height.
        self._unlock_justifications.pop(next_height, None)
        journal = get_vote_journal(self._config.chain_id)
        journal.prune_below(next_height - 1)  # next_height - 1 is the local tip: decided history
        votes = journal.votes_at(next_height, proposer)
        if not votes:
            return False
        base = await locate_voted_block(self._config.chain_id, next_height, {v.block_hash for v in votes})
        if base is not None:
            pull = self._sync_manager.pull_from_peer if self._sync_manager is not None else None
            kick_pull(pull, self._config.chain_id, base)
            metrics_registry.increment("vote_journal_proposal_suppressed_total")
            self._logger.warning(
                "[PROPOSE] Vote journal: already voted at height %s — pulling the voted block from %s instead of proposing",
                next_height,
                base,
            )
            return True
        unlock = float(getattr(settings, "vote_journal_unlock_seconds", 300.0))
        if all(valve_open(v, unlock) for v in votes):
            # #1280: fresh contention evidence (a peer serving a different
            # block at this height) suppresses the proposal too — delay only,
            # capped, never a signature outside the journal/UC path.
            hold = contention_hold(self._config.chain_id, next_height)
            if hold is not None:
                pull = self._sync_manager.pull_from_peer if self._sync_manager is not None else None
                if hold.sealed and hold.base and getattr(settings, "vote_journal_sealed_rival_pull", False):
                    kick_pull(pull, self._config.chain_id, hold.base)
                    metrics_registry.increment("vote_journal_sealed_rival_pull_total")
                metrics_registry.increment("vote_journal_contention_hold_total")
                self._logger.warning(
                    "[PROPOSE] Vote journal contention hold at height %s: peer serves rival %s "
                    "(sealed=%s) — holding despite valve age",
                    next_height,
                    hold.rival_hash[:18],
                    hold.sealed,
                )
                return True
            justification: dict[str, Any] | None = None
            if unavail.justification_enabled():
                # #1281 armed barrier: age+miss only triggers collection —
                # release needs the verifiable justification bundle.
                justification = await unavail.unlock_justification(
                    self._config.chain_id,
                    next_height,
                    {v.block_hash for v in votes},
                    ignore=self._own_addresses(),
                    # Propose path may await the shared UC probe — it is not
                    # the gossip listener; single-flight keeps it to one
                    # collection per (height, hash) mesh-wide per node.
                    wait_for_probe=True,
                )
                if justification is None:
                    metrics_registry.increment("vote_journal_proposal_suppressed_total")
                    self._logger.warning(
                        "[PROPOSE] Vote journal barrier holds height %s — "
                        "valve expired but no verifiable unlock justification",
                        next_height,
                    )
                    return True
                self._unlock_justifications[next_height] = justification
            metrics_registry.increment("vote_journal_valve_opened_total")
            self._logger.warning(
                "[PROPOSE] Vote journal valve opened at height %s: voted block unserved for over %.0fs — proposing%s",
                next_height,
                unlock,
                " [justified: unavailability_cert]" if justification is not None else "",
            )
            return False
        metrics_registry.increment("vote_journal_proposal_suppressed_total")
        self._logger.warning(
            "[PROPOSE] Vote journal: already voted at height %s and no peer serves the voted block; holding",
            next_height,
        )
        return True

    async def _publish_abandon(self, block: Block, block_hash: str) -> None:
        """#1301 L2: tell voters this proposer will never seal ``block_hash``.

        Best-effort and flag-gated; the proposer's own journal entry stays
        (self-lock), so it cannot reseal the abandoned hash itself.
        """
        if not abandon.abandon_enabled():
            return
        proposer = str(block.proposer)
        private_key = self._validator_keys.get(proposer) or getattr(settings, "proposer_key", None)
        if not private_key:
            return
        try:
            stmt = abandon.build_abandon(self._config.chain_id, block.height, block_hash, None, proposer, private_key)
            await gossip_broker.publish(abandon.abandon_topic(self._config.chain_id), stmt)
            metrics_registry.increment("vote_journal_abandon_published_total")
            self._logger.warning("[PROPOSE] Published abandon for %s at height %s", block_hash[:18], block.height)
        except Exception as exc:  # noqa: BLE001 - best effort; the valve remains the backstop
            self._logger.warning("Abandon publish failed at height %s: %s", block.height, exc)

    def _reservation_owner_for(self, proposer: str) -> str:
        """Reservation owner id when the P2 flag is armed, else "" (drain path)."""
        if not settings.mempool_reservation_enabled:
            return ""
        return self._reservation_owner_id(proposer)

    def _reservation_owner_id(self, proposer: str) -> str:
        """#1300 owner identity ``proposer:boot_uuid`` — stable for the life of
        this process so a restart never inherits or clears markers."""
        boot = getattr(self, "_reservation_boot_id", None)
        if boot is None:
            from uuid import uuid4

            boot = settings.p2p_node_id or uuid4().hex
            self._reservation_boot_id = boot
        return f"{proposer}:{boot}"

    def _commit_and_record_block(
        self,
        session: Session,
        block: Block,
        proposer: str,
        interval_seconds: float | None,
        timestamp: datetime,
    ) -> None:
        """Commit the signed block and update caches, metrics and proposer state."""
        session.add(block)
        journal = BlockDeltaJournal.get(session)
        if journal is not None:
            journal.persist(session)
        try:
            session.commit()
        except Exception as exc:
            # #1740: a disk-full/I/O-error commit leaves quick_check green —
            # quarantine on the error shape so import/propose/attest all
            # refuse instead of the proposer retrying into a dead disk.
            from ..database import quarantine_chain_db_for_error

            if quarantine_chain_db_for_error(self._config.chain_id, exc, session=session) is not None:
                session.rollback()
                self._logger.error(
                    "[PROPOSE] chain.db quarantined during block commit on chain %s",
                    self._config.chain_id,
                )
            raise
        # V-3 shadow (flag-gated, compare-only — never affects the sealed block).
        side_root_shadow.on_block_sealed(
            session, self._config.chain_id, block.height, block_version=get_block_version(block, block.height)
        )
        # Invalidate the in-process block header cache for the new block
        # so stale entries are not served by rpc/blocks.py.
        from ..block_cache import get_block_header_cache

        get_block_header_cache().invalidate(self._config.chain_id, height=block.height, hash=block.hash)
        metrics_registry.increment("blocks_proposed_total")
        metrics_registry.set_gauge("chain_head_height", float(block.height))
        if interval_seconds is not None and interval_seconds >= 0:
            metrics_registry.observe("block_interval_seconds", interval_seconds)
            metrics_registry.set_gauge("poa_last_block_interval_seconds", float(interval_seconds))
        proposer_suffix = _sanitize_metric_suffix(proposer)
        metrics_registry.increment(f"poa_blocks_proposed_total_{proposer_suffix}")
        if self._last_proposer_id is not None and self._last_proposer_id != proposer:
            metrics_registry.increment("poa_proposer_switches_total")
        self._last_proposer_id = proposer
        self._last_block_timestamp = timestamp
        block_height.set(block.height)
        self._logger.info("Proposed block", extra={"height": block.height, "hash": block.hash, "proposer": block.proposer})

    def _compute_bridge_state_root(
        self, session: Session, processed_txs: list[Any], chain_id: str, height: int | None = None
    ) -> str:
        """Build a Merkle trie from the BRIDGE_LOCK events in this block.

        The trie key is the lock transfer ID and the value is the canonical
        lock event string. The root hash becomes ``block.bridge_state_root``
        and is used by bridge proofs to prove inclusion of a lock.
        """
        from ..state.merkle_patricia_trie import MerklePatriciaTrie

        trie = MerklePatriciaTrie()
        lock_txs = [tx for tx in processed_txs if (tx.content or {}).get("type", "").upper() == "BRIDGE_LOCK"]
        if not lock_txs:
            return "0x" + trie.get_root().hex()
        transfer_ids = [tx.tx_hash for tx in lock_txs]
        records = session.exec(
            select(CrossChainTransfer).where(
                CrossChainTransfer.source_chain == chain_id,
                CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
            )
        ).all()
        record_map = {r.transfer_id: r for r in records}
        for tx in lock_txs:
            record = record_map.get(tx.tx_hash)
            if record is None:
                value = unknown_lock_leaf(tx.tx_hash)
            else:
                value = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, height)
            trie.put(tx.tx_hash.encode(), value.encode())
        return "0x" + trie.get_root().hex()

    def _block_header_message(self, block: Block) -> dict[str, Any]:
        """Canonical header message that the bridge verifier signs/verifies."""
        return {
            "chain_id": block.chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
        }

    def _compute_block_hash(
        self,
        height: int,
        parent_hash: str,
        timestamp: datetime,
        transactions: list[Any] | None = None,
        proposer: str = "",
        state_root: str | None = None,
        bridge_state_root: str | None = None,
        aux_state_root: str | None = None,
    ) -> str:
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]
        # v0.7.2: block hash binds the state roots and proposer so that bridge
        # proofs can be anchored to a signed block header. The formula lives
        # in consensus.block_hash so remote attesters recompute the identical
        # digest when binding an attestation request's tx list to the header.
        # v14 adds the aux term only when set, keeping pre-v14 digests
        # byte-identical.
        return compute_block_hash(
            self._config.chain_id,
            height,
            parent_hash,
            timestamp,
            tx_hashes,
            proposer,
            state_root,
            bridge_state_root,
            aux_state_root,
        )

    def _sign_block_hash(self, block: Block) -> str:
        """Sign a block header with the proposer's private key (v0.7.2).

        The signed message is the canonical-JSON encoding of the block header
        fields that the bridge verifier expects (chain_id, height, hash,
        parent_hash, proposer, state_root, bridge_state_root). This makes the
        same signature verifiable by both PoA consensus and bridge proof
        verification.

        Returns the hex signature, or empty string if no private key is
        configured (legacy mode — block signature verification skipped).
        """
        from ..config import settings

        private_key = getattr(settings, "proposer_key", None)
        if not private_key:
            self._logger.debug("No proposer_key configured; block signature omitted")
            return ""
        try:
            from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_PROPOSAL

            domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_PROPOSAL)
            message = self._block_header_message(block)
            return _sign_consensus(message, private_key, domain)
        except Exception as e:
            self._logger.warning("Failed to sign block header: %s", e)
            return ""

    @property
    def pbft_consensus(self) -> PBFTConsensus | None:
        """Return the PBFT consensus instance for this proposer, if any."""
        return self._pbft_consensus


from .poa_ops import _OpsMixin
from .poa_proposal_gates import _ProposalGatesMixin
from .poa_tx_pipeline import _TxPipelineMixin


class PoAProposer(_ProposalGatesMixin, _TxPipelineMixin, _OpsMixin):
    """Proof-of-Authority block proposer.

    Responsible for periodically proposing blocks if this node is configured as a proposer.
    In the real implementation, this would involve checking the mempool, validating transactions,
    and signing the block.
    """
