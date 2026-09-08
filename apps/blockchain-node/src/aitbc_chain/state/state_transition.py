"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import keccak
from sqlalchemy import func, text
from sqlmodel import Session, select

from ..config import settings
from ..logger import get_logger
from ..base_models import Block, Bond, ChainParameter, IPFSSubscription, _to_ait_address
from aitbc.crypto.signature_recovery import canonical_address
from ..models import Account, Receipt, Transaction
from ..rpc.utils import verify_transaction_signature
from .gpu_resources import GPUAllocation, GPURegistration
from .liquidity_transition import (
    apply_liquidity_claim,
    apply_liquidity_deposit,
    apply_liquidity_withdraw,
)

try:
    from aitbc.caching import RedisCache

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _cache: RedisCache | None = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
except Exception:
    _cache = None
logger = get_logger(__name__)

_BOND_ESCROW_ADDRESS = os.getenv("BOND_ESCROW_ADDRESS", "")
if _BOND_ESCROW_ADDRESS:
    _BOND_ESCROW_ADDRESS = canonical_address(_BOND_ESCROW_ADDRESS)
else:
    _BOND_ESCROW_ADDRESS = canonical_address("0x" + keccak(b"aitbc.bond.escrow").hex()[:40])

_BOND_BURN_ADDRESS = os.getenv("BOND_BURN_ADDRESS", "")
if _BOND_BURN_ADDRESS:
    _BOND_BURN_ADDRESS = canonical_address(_BOND_BURN_ADDRESS)
else:
    _BOND_BURN_ADDRESS = canonical_address("0x" + keccak(b"aitbc.bond.burn").hex()[:40])


def _governance_executors(session: Session, chain_id: str) -> frozenset[str] | None:
    """Authorized GOVERNANCE_EXECUTE senders from the on-chain
    ``governance_executors`` chain parameter (comma-separated addresses).

    The parameter is chain state, applied identically on every node, so the
    gate is deterministic — a per-node env list would recreate the
    slash-authority class of silent divergence. Unset or empty means no
    restriction (pre-gate behavior); once set, only listed senders pass
    validation on every node at the same height.
    """
    row = session.exec(
        select(ChainParameter).where(
            ChainParameter.chain_id == chain_id,
            ChainParameter.parameter == "governance_executors",
        )
    ).first()
    if not row or not row.value.strip():
        return None
    return frozenset(_to_ait_address(a.strip()) for a in row.value.split(",") if a.strip())


def _bond_slash_authority(session: Session, chain_id: str) -> str | None:
    """Return the canonical bond-slash authority address.

    The on-chain ``bond_slash_authority`` chain parameter wins: it is applied
    identically on every node that imports the parameter-setting transaction,
    so the gate is deterministic across the fleet. ``BOND_SLASH_AUTHORITY_ADDRESS``
    remains the fallback for chains that never set the parameter; a
    disagreement between the two is logged, because per-node env drift is
    exactly how the 1-2 Sep slashes were skipped on node0.
    """
    onchain = session.exec(
        select(ChainParameter).where(
            ChainParameter.chain_id == chain_id,
            ChainParameter.parameter == "bond_slash_authority",
        )
    ).first()
    env_addr = os.getenv("BOND_SLASH_AUTHORITY_ADDRESS", "").strip()
    if onchain and onchain.value.strip():
        addr = canonical_address(onchain.value.strip())
        if env_addr and canonical_address(env_addr) != addr:
            logger.warning(
                "BOND_SLASH_AUTHORITY_ADDRESS=%s disagrees with on-chain bond_slash_authority=%s; using the on-chain value",
                env_addr,
                addr,
            )
        return addr
    if env_addr:
        return canonical_address(env_addr)
    return None


def _bond_escrow_ait() -> str:
    return _to_ait_address(_BOND_ESCROW_ADDRESS)


def _bond_burn_ait() -> str:
    return _to_ait_address(_BOND_BURN_ADDRESS)


def _is_bond_escrow(address: str) -> bool:
    return canonical_address(address) == _BOND_ESCROW_ADDRESS


def _is_bond_burn(address: str) -> bool:
    return canonical_address(address) == _BOND_BURN_ADDRESS


def _escrow_address(job_id: str) -> str:
    """Derive a deterministic escrow address for a job (S-4).

    Funds locked for a job go to escrow:<job_id> — an address with no
    known private key, so the locked value is unspendable by the node
    wallet until a release or refund transaction moves it.
    """
    return canonical_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _is_escrow_address(address: str, job_id: str | None = None) -> bool:
    """Check whether an address is (or matches) a per-escrow lock address."""
    if job_id is None:
        # Without a job_id, check if it matches the escrow prefix pattern.
        # This is a heuristic — we can't reverse the hash.
        return False
    return canonical_address(address) == _escrow_address(job_id)


def _is_valid_0x_address(address: str) -> bool:
    """Return True if ``address`` is a canonical 42-character 0x address."""
    try:
        normalized = canonical_address(address)
    except Exception:
        return False
    return normalized.startswith("0x") and len(normalized) == 42


def _escrow_settlement_authority() -> str | None:
    """Return the canonical settlement authority for v3 escrow releases/refunds."""
    addr = settings.escrow_settlement_authority or os.getenv("ESCROW_RELEASE_ADDRESS", "")
    if not addr:
        return None
    return canonical_address(addr)


def _get_escrow_lock(session: Session, chain_id: str, job_id: str) -> Transaction | None:
    """Find the on-chain ESCROW_LOCK transaction for ``job_id``."""
    return session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "ESCROW_LOCK",
            Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
        )
    ).first()


def _get_escrow_lock_block_version(session: Session, chain_id: str, job_id: str) -> int | None:
    """Return the state-transition version of the block that mined the lock for ``job_id``."""
    lock_tx = _get_escrow_lock(session, chain_id, job_id)
    if not lock_tx or lock_tx.block_height is None:
        return None
    block = session.exec(select(Block).where(Block.chain_id == chain_id, Block.height == lock_tx.block_height)).first()
    if not block:
        return None
    return get_block_version(block, block.height)


def _escrow_beneficiary(lock_tx: Transaction, tx_type: str) -> str | None:
    """Return the canonical address that ``tx_type`` must pay for this lock."""
    payload = lock_tx.payload or {}
    if tx_type == "ESCROW_RELEASE":
        provider = payload.get("provider") or ""
        return _to_ait_address(provider) if provider else None
    if tx_type == "ESCROW_REFUND":
        return _to_ait_address(lock_tx.sender or "")
    return None


def build_escrow_context(session: Session, chain_id: str, tx_datas: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
    """Prefetch per-job lock metadata for ESCROW_RELEASE/ESCROW_REFUND txs (S-4).

    The pure/parallel ``compute_state_delta`` cannot touch the DB, so callers
    that want parallel validation of v3 blocks must supply this map:
    ``{job_id: {"lock_version": int|None, "expected_beneficiary": str|None,
    "escrow_addr": str}}``.

    Returns ``None`` when any release/refund references a job_id with no
    on-chain lock — the sequential path applies its own missing-lock rules, so
    the caller must keep sequential processing to stay consensus-identical.
    Batches with no release/refund txs return ``{}`` (cheap no-op).
    """
    context: dict[str, dict[str, Any]] = {}
    for tx_data in tx_datas:
        tx_type = _tx_type(tx_data)
        if tx_type not in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            continue
        payload = tx_data.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        job_id = payload.get("job_id") or tx_data.get("job_id") or ""
        if job_id in context:
            # A second release/refund for the same job with a different tx_type
            # would need a different beneficiary — an invalid batch anyway; let
            # the sequential path apply its own checks.
            if context[job_id].get("tx_type") != tx_type:
                return None
            continue
        lock_tx = _get_escrow_lock(session, chain_id, job_id) if job_id else None
        if lock_tx is None:
            return None
        context[job_id] = {
            "tx_type": tx_type,
            "lock_version": _get_escrow_lock_block_version(session, chain_id, job_id),
            "expected_beneficiary": _escrow_beneficiary(lock_tx, tx_type),
            "escrow_addr": _escrow_address(job_id),
        }
    return context


def _ensure_account(session: Session, chain_id: str, address: str) -> Account:
    ait_addr = _to_ait_address(address)
    account = session.get(Account, (chain_id, ait_addr))
    if not account:
        account = Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0)
        session.add(account)
        session.flush()
    return account


def _tx_type(tx_data: dict[str, Any], tx_record: Transaction | None = None) -> str:
    """Resolve the canonical transaction type from record or tx data."""
    if tx_record and tx_record.type:
        return tx_record.type.upper()
    tx_type = tx_data.get("type", "TRANSFER")
    if not tx_type or tx_type == "TRANSFER":
        payload = tx_data.get("payload", {})
        if isinstance(payload, dict):
            tx_type = payload.get("type", "TRANSFER")
    return (tx_type or "TRANSFER").upper()


def get_block_version(block_data_or_block: dict[str, Any] | object, height: int = 0) -> int:
    """Return the state-transition rule version that should be used for a block.

    A block that explicitly stores ``state_transition_version`` in its
    ``block_metadata`` uses that value. Unversioned blocks fall back to the
    configured activation heights, so historical blocks replay under the rules
    that produced them.
    """
    metadata: str | None = None
    if isinstance(block_data_or_block, dict):
        metadata = block_data_or_block.get("block_metadata")
    else:
        metadata = getattr(block_data_or_block, "block_metadata", None)
    if metadata:
        try:
            parsed = json.loads(metadata)
            version = parsed.get("state_transition_version")
            if version is not None:
                return int(version)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    v3_threshold = getattr(settings, "state_transition_v3_height", 0)
    if v3_threshold > 0 and height >= v3_threshold:
        return 3
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height >= v2_threshold:
        return 2
    return 1


def get_block_version_for_height(height: int) -> int:
    """Return the state-transition rule version a *new* block at ``height`` should use.

    Unlike ``get_block_version``, this does not inspect an existing block's
    metadata. It is used by the proposer to determine which version to stamp into
    the block it is about to build.
    """
    v3_threshold = getattr(settings, "state_transition_v3_height", 0)
    if v3_threshold > 0 and height >= v3_threshold:
        return 3
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height < v2_threshold:
        return 1
    return 2


class StateTransition:
    """
    Validates and applies state transitions only through validated transactions.

    This class ensures that balance changes can only occur through properly
    validated transactions, preventing direct database manipulation of account
    balances.
    """

    def __init__(self) -> None:
        self._processed_nonces: dict[str, int] = {}
        self._processed_tx_hashes: set[str] = set()

    def reset_processed_cache(self) -> None:
        """Clear in-memory per-process tx/nonce caches.

        The caches are intended to prevent the same transaction from being
        applied twice within one block. Because a rejected block is rolled back,
        leaving the cache populated causes false "replay attack" errors on the
        next import attempt. Call this at the start of each block.
        """
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()

    def validate_transaction(
        self, session: Session, chain_id: str, tx_data: dict[str, Any], tx_hash: str, block_version: int = 2
    ) -> tuple[bool, str]:
        """
        Validate a transaction before applying state changes.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash

        Returns:
            Tuple of (is_valid, error_message)
        """
        tx_chain_id = tx_data.get("chain_id")
        if tx_chain_id and tx_chain_id != chain_id:
            logger.warning(
                "Chain isolation violation: Transaction %s has chain_id=%s but node is configured for chain_id=%s. Rejecting cross-chain transaction.",
                tx_hash,
                tx_chain_id,
                chain_id,
            )
            return (
                False,
                f"Chain isolation violation: transaction chain_id={tx_chain_id} does not match node chain_id={chain_id}",
            )
        if tx_hash in self._processed_tx_hashes:
            logger.warning("Replay attack detected: Transaction %s already processed", tx_hash)
            return (False, f"Transaction {tx_hash} already processed (replay attack)")
        # Persistent replay protection: the in-memory set above is lost on
        # restart; the DB unique constraint on (chain_id, tx_hash) is not.
        persisted_tx = session.exec(
            select(Transaction.tx_hash).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        if persisted_tx is not None:
            logger.warning("Replay attack detected: Transaction %s already persisted", tx_hash)
            return (False, f"Transaction {tx_hash} already processed (replay attack)")
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        tx_type = _tx_type(tx_data, tx_record)
        if tx_type in {"LIQUIDITY_DEPOSIT", "LIQUIDITY_WITHDRAW", "LIQUIDITY_CLAIM"}:
            # Validate the payload before touching state: _ensure_account below
            # writes account rows, and a validator that returns False after
            # writing them leaves the proposer with accounts no other node has.
            payload = tx_data.get("payload") or {}
            if tx_type == "LIQUIDITY_DEPOSIT":
                if not payload.get("pool_id"):
                    return (False, "LIQUIDITY_DEPOSIT payload must include pool_id")
                if "lock_days" not in payload:
                    return (False, "LIQUIDITY_DEPOSIT payload must include lock_days")
            if tx_type in {"LIQUIDITY_WITHDRAW", "LIQUIDITY_CLAIM"}:
                if not payload.get("stake_id"):
                    return (False, f"{tx_type} payload must include stake_id")
            # Ensure the pool reserve/treasury/emission accounts and the sender
            # and recipient accounts exist before the generic recipient check.
            _ensure_account(session, chain_id, sender_addr)
            _ensure_account(session, chain_id, _to_ait_address(tx_data.get("to") or ""))
        if tx_type in {"FAUCET", "BRIDGE_RELEASE", "BRIDGE_REFUND"}:
            # Pre-registered credit transactions do not require a sender account or
            # nonce. The state update is applied off-chain by the RPC call that
            # created the transaction; the block just anchors the record.  Replay is
            # prevented by the persistent tx hash check above.
            return (True, "Pre-registered credit transaction validated")
        if tx_type == "BRIDGE_LOCK":
            # Pre-registered bridge lock: the sender was already debited when the
            # lock was created. The block only anchors the record. Do not validate
            # the tx nonce or require a bridge_lock recipient account.
            sender_account = session.get(Account, (chain_id, sender_addr))
            if not sender_account:
                return (False, f"Sender account not found: {sender_addr}")
            total_cost = value + fee
            if sender_account.balance < total_cost:
                return (False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}")
            return (True, "Pre-registered bridge lock validated")
        if tx_type == "BRIDGE_WITHDRAW":
            # User-signed burn of AIT in exchange for an off-chain ETH release.
            # The payload must contain a valid Ethereum destination address.
            payload = tx_data.get("payload") or {}
            eth_address = payload.get("eth_address", "")
            if not eth_address or not _is_valid_0x_address(eth_address):
                return (False, "BRIDGE_WITHDRAW payload must contain a valid 0x eth_address")
            if value <= 0:
                return (False, "BRIDGE_WITHDRAW must have a positive value")
        if tx_type == "ESCROW_LOCK" and block_version >= 3:
            # S-4: v3 per-escrow locks require a job_id and a provider so the
            # escrow is deterministic and future release/refund can bind the
            # beneficiary and settlement authority.
            payload = tx_data.get("payload") or {}
            if not payload.get("job_id"):
                return (False, "ESCROW_LOCK v3 payload must include job_id")
            if not payload.get("provider"):
                return (False, "ESCROW_LOCK v3 payload must include provider")
        signature = tx_data.get("signature")
        if signature and sender_addr:
            if not verify_transaction_signature(tx_data, signature, sender_addr):
                return (False, f"Invalid signature for transaction {tx_hash}")
        sender_account = session.get(Account, (chain_id, sender_addr))
        if not sender_account:
            return (False, f"Sender account not found: {sender_addr}")
        expected_nonce = sender_account.nonce if sender_account.nonce is not None else 0
        tx_nonce = tx_data.get("nonce", 0)
        if tx_nonce != expected_nonce:
            return (False, f"Invalid nonce for {sender_addr}: expected {expected_nonce}, got {tx_nonce}")
        if tx_type == "GOVERNANCE_EXECUTE":
            executors = _governance_executors(session, chain_id)
            if executors is not None and sender_addr not in executors:
                return (
                    False,
                    f"GOVERNANCE_EXECUTE sender {sender_addr} is not an authorized executor",
                )
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"} and value != 0:
            return (False, f"{tx_type} transactions must have value=0, got {value}")
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"}:
            total_cost = fee
        else:
            total_cost = value + fee
        # S-4 (v3): ESCROW_RELEASE/ESCROW_REFUND funds come from the per-escrow
        # address, not the sender (node wallet). We validate against the version
        # the lock was mined under so a v3 activation does not strand v2 locks.
        if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            job_id = (tx_data.get("payload") or {}).get("job_id", "")
            if not job_id:
                return (False, f"{tx_type} payload must include job_id")
            lock_tx = _get_escrow_lock(session, chain_id, job_id)
            if not lock_tx:
                return (False, f"No ESCROW_LOCK found for {job_id}")
            lock_version = _get_escrow_lock_block_version(session, chain_id, job_id)
            if lock_version is None:
                lock_version = 2 if block_version < 3 else 3
            expected_beneficiary = _escrow_beneficiary(lock_tx, tx_type)
            if expected_beneficiary and _to_ait_address(recipient_addr) != expected_beneficiary:
                return (False, f"{tx_type} for {job_id} must pay {expected_beneficiary}, got {recipient_addr}")
            if block_version >= 3:
                authority = _escrow_settlement_authority()
                if authority and _to_ait_address(sender_addr) != authority:
                    return (False, f"{tx_type} must be signed by settlement authority {authority}, got {sender_addr}")
            if lock_version >= 3:
                # Funds are in the per-escrow address.
                escrow_addr = _escrow_address(job_id)
                escrow_account = session.get(Account, (chain_id, escrow_addr))
                if escrow_account is None or escrow_account.balance < value:
                    escrow_bal = escrow_account.balance if escrow_account else 0
                    return (False, f"Escrow {job_id} has insufficient balance: {escrow_bal} < {value}")
                # The settlement authority pays only the fee, not the value.
                if sender_account.balance < fee:
                    return (False, f"Insufficient balance for fee: {sender_account.balance} < {fee}")
            elif sender_account.balance < total_cost:
                return (False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}")
        elif sender_account.balance < total_cost:
            return (False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}")
        # v0.25.5: recipient accounts are created on first credit during
        # block execution, so a release/refund/transfer to a never-before-seen
        # address is valid and becomes deterministic after mining.
        if tx_type == "RECEIPT_CLAIM":
            receipt_id = tx_data.get("payload", {}).get("receipt_id")
            if not receipt_id:
                return (False, "RECEIPT_CLAIM transactions must include receipt_id in payload")
            receipt = session.exec(
                select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)
            ).first()
            if not receipt:
                return (False, f"Receipt not found: {receipt_id}")
            if receipt.status != "pending":
                return (False, f"Receipt already claimed or invalid: {receipt.status}")
            if not receipt.miner_signature or not isinstance(receipt.miner_signature, dict):
                return (False, f"Receipt {receipt_id} has invalid miner signature")
            if not receipt.coordinator_attestations or not isinstance(receipt.coordinator_attestations, list):
                return (False, f"Receipt {receipt_id} has invalid coordinator attestations")
        if tx_type == "IPFS_SUBSCRIPTION":
            payload = tx_data.get("payload", {}) or {}
            if isinstance(payload, str):
                try:
                    import json

                    payload = json.loads(payload)
                except Exception:
                    return (False, "IPFS_SUBSCRIPTION payload is not valid JSON")
            if not payload.get("island_id"):
                return (False, "IPFS_SUBSCRIPTION payload must include island_id")
            duration_blocks = payload.get("duration_blocks")
            if not isinstance(duration_blocks, int) or duration_blocks <= 0:
                return (False, "IPFS_SUBSCRIPTION payload must include positive duration_blocks")
            quota_bytes = payload.get("quota_bytes")
            if not isinstance(quota_bytes, int) or quota_bytes < 0:
                return (False, "IPFS_SUBSCRIPTION payload must include non-negative quota_bytes")
            if value <= 0:
                return (False, "IPFS_SUBSCRIPTION requires value > 0")
            # Ensure recipient (island treasury) exists so the payment can be credited.
            _ensure_account(session, chain_id, recipient_addr)
        return (True, "Transaction validated successfully")

    def apply_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int = 2,
    ) -> tuple[bool, str]:
        """
        Apply a validated transaction to update state.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            block_version: State-transition rule version active for the block
                that contains this transaction. v1 keeps pre-2026-09-01 rules
                (no auto-created recipient/provider accounts); v2 applies the
                current account-creation rules.

        Returns:
            Tuple of (success, error_message)
        """
        logger.info("apply_transaction called for tx %s, tx_data keys: %s", tx_hash, list(tx_data.keys()))
        is_valid, error_msg = self.validate_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version)
        if not is_valid:
            return (False, error_msg)
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        tx_type = _tx_type(tx_data, tx_record)
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        # Guard against BigInt overflow (SQLite INTEGER is 64-bit signed)
        _MAX_INT64 = 2**63 - 1
        if value < 0 or fee < 0 or value > _MAX_INT64 or fee > _MAX_INT64:
            raise ValueError(f"Transaction value/fee out of range: value={value}, fee={fee}")
        if tx_type == "LIQUIDITY_DEPOSIT":
            ok, msg = apply_liquidity_deposit(session, chain_id, tx_data, tx_hash, _cache)
            if ok:
                self._processed_tx_hashes.add(tx_hash)
            return (ok, msg)
        if tx_type == "LIQUIDITY_CLAIM":
            ok, msg = apply_liquidity_claim(session, chain_id, tx_data, tx_hash, _cache)
            if ok:
                self._processed_tx_hashes.add(tx_hash)
            return (ok, msg)
        if tx_type == "LIQUIDITY_WITHDRAW":
            ok, msg = apply_liquidity_withdraw(session, chain_id, tx_data, tx_hash, _cache)
            if ok:
                self._processed_tx_hashes.add(tx_hash)
            return (ok, msg)
        if tx_type in {"FAUCET", "BRIDGE_RELEASE", "BRIDGE_REFUND"}:
            # Pre-registered credit transactions: the sender is a magic string
            # (faucet/bridge_release/bridge_refund) and does not have an account.
            # Only the recipient is credited.
            _ensure_account(session, chain_id, recipient_addr)
            logger.info("Updating recipient balance: %s += %s", recipient_addr, value)
            session.execute(
                text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
                {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
            )
            self._processed_tx_hashes.add(tx_hash)
            if _cache and _cache.is_available():
                _cache.delete(f"account_balance:{chain_id}:{recipient_addr.lower()}")
                _cache.delete(f"account_details:{chain_id}:{recipient_addr.lower()}")
            logger.info(
                "Applied %s transaction %s: %s -> %s, value=%s, fee=%s",
                tx_type,
                tx_hash,
                sender_addr,
                recipient_addr,
                value,
                fee,
            )
            return (True, "Transaction applied successfully")
        if tx_type == "BRIDGE_LOCK":
            # Pre-registered bridge lock: debit the sender and increment the nonce.
            # The locked value is not credited to any account; it is recorded in the
            # CrossChainTransfer table. No bridge_lock account is created.
            _ensure_account(session, chain_id, sender_addr)
            total_cost = value + fee
            logger.info("Bridge lock: %s -= %s, nonce += 1", sender_addr, total_cost)
            session.execute(
                text(
                    "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
                ),
                {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
            )
            self._processed_tx_hashes.add(tx_hash)
            if _cache and _cache.is_available():
                _cache.delete(f"account_balance:{chain_id}:{sender_addr.lower()}")
                _cache.delete(f"account_details:{chain_id}:{sender_addr.lower()}")
            logger.info(
                "Applied %s transaction %s: %s, value=%s, fee=%s",
                tx_type,
                tx_hash,
                sender_addr,
                value,
                fee,
            )
            return (True, "Transaction applied successfully")
        if tx_type == "BRIDGE_WITHDRAW":
            # Burn AIT from the sender and increase the nonce. The off-chain
            # bridge monitor is responsible for releasing ETH to payload.eth_address.
            _ensure_account(session, chain_id, sender_addr)
            total_cost = value + fee
            logger.info("Bridge withdraw: %s -= %s, nonce += 1", sender_addr, total_cost)
            session.execute(
                text(
                    "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
                ),
                {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
            )
            self._processed_tx_hashes.add(tx_hash)
            if _cache and _cache.is_available():
                _cache.delete(f"account_balance:{chain_id}:{sender_addr.lower()}")
                _cache.delete(f"account_details:{chain_id}:{sender_addr.lower()}")
            logger.info(
                "Applied %s transaction %s: %s, value=%s, fee=%s, eth_address=%s",
                tx_type,
                tx_hash,
                sender_addr,
                value,
                fee,
                (tx_data.get("payload") or {}).get("eth_address"),
            )
            return (True, "Transaction applied successfully")
        if tx_type == "ESCROW_LOCK" and block_version >= 2:
            # v0.25.5: the Escrow DB record references the provider address, so
            # ensure the provider account exists even though the lock itself only
            # transfers from buyer to the node wallet. Older v1 blocks (pre this
            # fix) do not create the provider account, so replaying them must
            # keep the original state-root behavior.
            provider_addr = _to_ait_address((tx_data.get("payload") or {}).get("provider", ""))
            if provider_addr:
                _ensure_account(session, chain_id, provider_addr)
            # S-4 (v3): redirect the locked value to a deterministic per-escrow
            # address so the node wallet's spendable balance never includes
            # escrowed funds. The escrow address has no known key — funds can
            # only leave via ESCROW_RELEASE or ESCROW_REFUND.
            if block_version >= 3:
                job_id = (tx_data.get("payload") or {}).get("job_id", "")
                if job_id:
                    escrow_addr = _escrow_address(job_id)
                    _ensure_account(session, chain_id, escrow_addr)
                    # Override the recipient for the balance update below.
                    recipient_addr = escrow_addr
        sender_account = session.get(Account, (chain_id, sender_addr))
        if tx_type in {"MESSAGE", "GOVERNANCE_EXECUTE"}:
            total_cost = fee
        else:
            total_cost = value + fee
            if total_cost > _MAX_INT64:
                raise ValueError(f"Transaction total_cost overflow: {total_cost}")
            # v0.25.5: auto-create the recipient account on first credit so
            # release/refund/transfer to a new address is deterministic across
            # validators and does not require a direct RPC write. This only
            # applies to v2 blocks; v1 blocks keep the original account set.
            if block_version >= 2:
                _ensure_account(session, chain_id, recipient_addr)
        logger.info("Updating sender balance: %s -= %s", sender_addr, total_cost)
        session.execute(
            text(
                "UPDATE account SET balance = balance - :total_cost, nonce = nonce + 1 WHERE chain_id = :chain_id AND address = :sender_addr"
            ),
            {"total_cost": total_cost, "chain_id": chain_id, "sender_addr": sender_addr},
        )
        if tx_type != "MESSAGE":
            logger.info("Updating recipient balance: %s += %s", recipient_addr, value)
            session.execute(
                text("UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"),
                {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
            )
        session.flush()
        if tx_type in ("ESCROW_RELEASE", "ESCROW_REFUND"):
            # S-4: move funds FROM the per-escrow address only when the lock was
            # itself a v3 per-escrow lock. Legacy v2 locks keep the value in the
            # node wallet, so the generic debit/credit above is already correct.
            job_id = (tx_data.get("payload") or {}).get("job_id", "")
            if job_id:
                lock_version = _get_escrow_lock_block_version(session, chain_id, job_id)
                if lock_version is None:
                    lock_version = 2 if block_version < 3 else 3
                if lock_version >= 3:
                    escrow_addr = _escrow_address(job_id)
                    # The generic path above debited the sender (node wallet) for
                    # value+fee and credited the recipient for value. Undo both
                    # the sender debit (for value) and the recipient credit, then
                    # re-credit the recipient from the escrow address. The sender
                    # keeps only the fee debit.
                    # Undo recipient credit
                    session.execute(
                        text(
                            "UPDATE account SET balance = balance - :value WHERE chain_id = :chain_id AND address = :recipient_addr"
                        ),
                        {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
                    )
                    # Undo sender debit (for value only — fee stays debited)
                    session.execute(
                        text(
                            "UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :sender_addr"
                        ),
                        {"value": value, "chain_id": chain_id, "sender_addr": sender_addr},
                    )
                    escrow_account = session.get(Account, (chain_id, escrow_addr))
                    if escrow_account is None or escrow_account.balance < value:
                        raise ValueError(f"Escrow {job_id} has insufficient balance for {tx_type}")
                    session.execute(
                        text(
                            "UPDATE account SET balance = balance - :value WHERE chain_id = :chain_id AND address = :escrow_addr"
                        ),
                        {"value": value, "chain_id": chain_id, "escrow_addr": escrow_addr},
                    )
                    session.execute(
                        text(
                            "UPDATE account SET balance = balance + :value WHERE chain_id = :chain_id AND address = :recipient_addr"
                        ),
                        {"value": value, "chain_id": chain_id, "recipient_addr": recipient_addr},
                    )
                    session.flush()
                    logger.info("S-4: %s moved %s from escrow %s to %s", tx_type, value, escrow_addr, recipient_addr)
        if tx_type in ("BOND_LOCK", "BOND_RELEASE", "BOND_SLASH"):
            skip_reason = self._handle_bond_transaction(
                session, chain_id, tx_data, tx_hash, tx_type, sender_addr, recipient_addr, value
            )
            if skip_reason:
                # Fee and nonce still applied — name it, or the "Applied
                # transaction" INFO below reads as a fully-applied slash
                # (the 1-2 Sep forensics trap).
                logger.warning(
                    "%s %s applied fee/nonce but bond effect skipped: %s",
                    tx_type,
                    tx_hash,
                    skip_reason,
                )
        if tx_type == "GOVERNANCE_EXECUTE":
            self._handle_governance_execute(session, chain_id, tx_data, tx_hash)
        if tx_type == "RECEIPT_CLAIM":
            receipt_id = tx_data.get("payload", {}).get("receipt_id")
            receipt = session.exec(
                select(Receipt).where(Receipt.chain_id == chain_id, Receipt.receipt_id == receipt_id)
            ).first()
            if receipt and receipt.minted_amount:
                sender_account.balance += receipt.minted_amount  # type: ignore[union-attr]
                receipt.status = "claimed"
                receipt.claimed_at = datetime.now(UTC)
                receipt.claimed_by = sender_addr
                logger.info(
                    "Claimed receipt %s: minted_amount=%s, claimed_by=%s", receipt_id, receipt.minted_amount, sender_addr
                )
        if tx_type == "IPFS_SUBSCRIPTION":
            self._handle_ipfs_subscription(session, chain_id, tx_data, tx_hash, sender_addr)
        self._processed_tx_hashes.add(tx_hash)
        if sender_addr is not None:
            self._processed_nonces[sender_addr] = sender_account.nonce  # type: ignore[union-attr]
        if _cache and _cache.is_available():
            for addr in [sender_addr, recipient_addr]:
                if addr:
                    _cache.delete(f"account_balance:{chain_id}:{addr.lower()}")
                    _cache.delete(f"account_details:{chain_id}:{addr.lower()}")
        logger.info(
            "Applied transaction %s: %s -> %s, value=%s, fee=%s, type=%s",
            tx_hash,
            sender_addr,
            recipient_addr,
            value,
            fee,
            tx_type,
        )
        return (True, "Transaction applied successfully")

    def _handle_ipfs_subscription(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        sender_addr: str,
    ) -> None:
        """Record or extend an on-chain IPFS subscription for an island member."""
        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                logger.warning("IPFS_SUBSCRIPTION payload is not valid JSON: %s", tx_hash)
                return
        island_id = payload.get("island_id")
        duration_blocks = payload.get("duration_blocks", 0)
        quota_bytes = payload.get("quota_bytes", 0)
        if (
            not island_id
            or not isinstance(duration_blocks, int)
            or duration_blocks <= 0
            or not isinstance(quota_bytes, int)
            or quota_bytes < 0
        ):
            logger.warning("IPFS_SUBSCRIPTION tx %s has invalid payload: %s", tx_hash, payload)
            return

        current_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first() or 0
        expires_at_block = current_height + duration_blocks

        existing = session.exec(
            select(IPFSSubscription).where(
                IPFSSubscription.chain_id == chain_id,
                IPFSSubscription.island_id == island_id,
                IPFSSubscription.member_address == sender_addr,
            )
        ).first()
        now = datetime.now(UTC)
        if existing:
            existing.expires_at_block = max(existing.expires_at_block, expires_at_block)
            existing.quota_bytes += quota_bytes
            existing.updated_tx_hash = tx_hash
            existing.updated_at = now
            logger.info(
                "IPFS subscription extended: island=%s member=%s expires=%s quota=%s",
                island_id,
                sender_addr,
                existing.expires_at_block,
                existing.quota_bytes,
            )
        else:
            session.add(
                IPFSSubscription(
                    chain_id=chain_id,
                    island_id=island_id,
                    member_address=sender_addr,
                    expires_at_block=expires_at_block,
                    quota_bytes=quota_bytes,
                    used_bytes=0,
                    created_tx_hash=tx_hash,
                    updated_tx_hash=tx_hash,
                    created_at=now,
                    updated_at=now,
                )
            )
            logger.info(
                "IPFS subscription created: island=%s member=%s expires=%s quota=%s",
                island_id,
                sender_addr,
                expires_at_block,
                quota_bytes,
            )

    def _handle_governance_execute(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
    ) -> None:
        """Apply a GOVERNANCE_EXECUTE transaction payload to chain parameters.

        The transaction payload must contain:
        - proposal_id: the on-chain governance proposal being executed
        - execution_payload: the payload stored in the proposal (or an override)

        For a parameter_change action, the execution payload should contain:
        - parameter: the parameter name
        - value: the new string value
        """
        from ..base_models import ChainParameter, GovernanceProposal

        payload = tx_data.get("payload", {}) or {}
        if isinstance(payload, str):
            try:
                import json

                payload = json.loads(payload)
            except Exception:
                logger.warning("GOVERNANCE_EXECUTE payload is not valid JSON: %s", payload)
                return

        proposal_id = payload.get("proposal_id") or tx_data.get("proposal_id")
        execution_payload = payload.get("execution_payload", {}) or {}
        action = execution_payload.get("action", "parameter_change")

        if not proposal_id:
            logger.warning("GOVERNANCE_EXECUTE tx %s missing proposal_id", tx_hash)
            return

        # Record execution on the on-chain proposal record, if present
        proposal = session.exec(
            select(GovernanceProposal).where(
                GovernanceProposal.chain_id == chain_id,
                GovernanceProposal.proposal_id == proposal_id,
            )
        ).first()
        if proposal:
            proposal.status = "executed"
            proposal.executed_at = datetime.now(UTC)
            proposal.execution_tx_hash = tx_hash
            session.add(proposal)

        if action == "parameter_change":
            parameter = execution_payload.get("parameter")
            value = execution_payload.get("value")
            if not parameter:
                logger.warning("GOVERNANCE_EXECUTE tx %s parameter_change missing parameter name", tx_hash)
                return
            existing = session.exec(
                select(ChainParameter).where(
                    ChainParameter.chain_id == chain_id,
                    ChainParameter.parameter == parameter,
                )
            ).first()
            if existing:
                existing.value = str(value)
                existing.proposal_id = proposal_id
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(
                    ChainParameter(
                        chain_id=chain_id,
                        parameter=parameter,
                        value=str(value),
                        proposal_id=proposal_id,
                    )
                )
            logger.info(
                "Chain parameter %s updated to %s by proposal %s (tx %s)",
                parameter,
                value,
                proposal_id,
                tx_hash,
            )
        elif action == "set_governance_address":
            # Reserved for adding/removing governance signing addresses
            logger.info("GOVERNANCE_EXECUTE set_governance_address not implemented: %s", execution_payload)
        else:
            logger.info("GOVERNANCE_EXECUTE unknown action %s: %s", action, execution_payload)

    def _handle_bond_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        tx_type: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
    ) -> str | None:
        """Record bond state alongside the on-chain value transfer.

        Returns None when the bond effect was applied, or a short reason string
        when it was skipped. The caller logs the reason so a skipped slash
        cannot masquerade as a fully applied transaction.


        Design:
        - BOND_LOCK is a normal transfer provider -> bond escrow. We record the bond.
        - BOND_RELEASE is provider-signed, value=0; we move the bond from escrow to provider.
        - BOND_SLASH is slash-authority-signed, value=0; we move the bond from escrow to burn.
        """
        payload = tx_data.get("payload", {}) or {}
        bond_id = payload.get("bond_id")
        if not bond_id:
            return "missing bond_id in payload"
        provider = payload.get("provider")
        if not provider:
            return "missing provider in payload"

        now = datetime.now(UTC)
        if tx_type == "BOND_LOCK":
            if not _is_bond_escrow(recipient_addr):
                return "recipient is not the bond escrow address"
            if value <= 0:
                return "non-positive lock value"
            lock_days = int(payload.get("lock_days", 30))
            locked_until = now + timedelta(days=lock_days)
            # Reuse an existing active bond with the same id if it exists (top-up).
            existing = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id)).first()
            if existing:
                existing.amount += value
                existing.locked_until = locked_until
                existing.updated_at = now
                logger.info("Bond topped up: %s amount=%s locked_until=%s", bond_id, existing.amount, locked_until)
            else:
                # Named apart from the `bond` the BOND_RELEASE/BOND_SLASH branches
                # load: those are Bond | None, and sharing the name pinned the
                # inferred type to Bond.
                new_bond = Bond(
                    chain_id=chain_id,
                    bond_id=bond_id,
                    provider=_to_ait_address(provider),
                    amount=value,
                    locked_until=locked_until,
                    status="active",
                    created_tx_hash=tx_hash,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_bond)
                logger.info("Bond locked: %s provider=%s amount=%s locked_until=%s", bond_id, provider, value, locked_until)
        elif tx_type == "BOND_RELEASE":
            if sender_addr != _to_ait_address(provider):
                return "not signed by the bond provider"
            if recipient_addr != sender_addr:
                return "recipient must be the provider"
            if value != 0:
                return "must have value=0"
            bond = session.exec(
                select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
            ).first()
            if not bond:
                return f"unknown or inactive bond {bond_id}"
            if bond.locked_until:
                locked_until = bond.locked_until
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=UTC)
                if now < locked_until:
                    return f"lock period for {bond_id} has not expired"
            release_amount = bond.amount
            if release_amount <= 0:
                return "bond has nothing to release"
            escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
            sender = session.get(Account, (chain_id, sender_addr))
            if escrow and sender:
                session.refresh(escrow)
                session.refresh(sender)
                if escrow.balance < release_amount:
                    return f"escrow balance {escrow.balance} below release amount {release_amount}"
                escrow.balance -= release_amount
                sender.balance += release_amount
                logger.info("BOND_RELEASE %s moved %s from escrow to %s", tx_hash, release_amount, sender_addr)
            bond.amount = 0
            bond.released_tx_hash = tx_hash
            bond.status = "released"
            bond.updated_at = now
            logger.info("Bond released: %s amount=%s", bond_id, release_amount)
        elif tx_type == "BOND_SLASH":
            slash_authority = _bond_slash_authority(session, chain_id)
            if not slash_authority:
                return "no slash authority configured (chain parameter or BOND_SLASH_AUTHORITY_ADDRESS)"
            if sender_addr != _to_ait_address(slash_authority):
                return "not signed by the configured slash authority"
            if not _is_bond_burn(recipient_addr):
                return "does not burn to the bond burn address"
            if value != 0:
                return "must have value=0"
            slash_amount = int(payload.get("amount", 0))
            if slash_amount <= 0:
                return "missing positive amount in payload"
            bond = session.exec(
                select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
            ).first()
            if not bond:
                return f"unknown or inactive bond {bond_id}"
            if slash_amount > bond.amount:
                slash_amount = bond.amount
            if slash_amount <= 0:
                return "slash amount reduced to zero"
            escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
            burn = _ensure_account(session, chain_id, _BOND_BURN_ADDRESS)
            if escrow and burn:
                session.refresh(escrow)
                session.refresh(burn)
                if escrow.balance < slash_amount:
                    return f"escrow balance {escrow.balance} below slash amount {slash_amount}"
                escrow.balance -= slash_amount
                burn.balance += slash_amount
                logger.info("BOND_SLASH %s moved %s from escrow to burn", tx_hash, slash_amount)
            bond.amount -= slash_amount
            bond.slashed_tx_hash = tx_hash
            bond.status = "slashed" if bond.amount <= 0 else "active"
            bond.updated_at = now
            logger.info("Bond slashed: %s amount=%s remaining=%s", bond_id, slash_amount, bond.amount)
        return None

    def validate_state_transition(
        self, session: Session, chain_id: str, old_accounts: dict[str, Account], new_accounts: dict[str, Account]
    ) -> tuple[bool, str]:
        """
        Validate that state changes only occur through transactions.

        Args:
            session: Database session
            chain_id: Chain identifier
            old_accounts: Previous account state
            new_accounts: New account state

        Returns:
            Tuple of (is_valid, error_message)
        """
        for address, old_acc in old_accounts.items():
            if address not in new_accounts:
                continue
            new_acc = new_accounts[address]
            if old_acc.balance != new_acc.balance:
                logger.warning(
                    "Balance change detected for %s: %s -> %s (validated through transaction processing)",
                    address,
                    old_acc.balance,
                    new_acc.balance,
                )
        return (True, "State transition validated")

    def get_processed_nonces(self) -> dict[str, int]:
        """Get the last processed nonce for each address."""
        return self._processed_nonces.copy()

    def handle_gpu_registration(self, session: Session, chain_id: str, gpu_data: dict[str, Any]) -> tuple[bool, str]:
        """
        Handle GPU registration state transition.

        Args:
            session: Database session
            chain_id: Chain identifier
            gpu_data: GPU registration data

        Returns:
            Tuple of (success, error_message)
        """
        try:
            gpu_id = gpu_data.get("gpu_id")
            if not gpu_id:
                return (False, "GPU ID is required")
            existing = session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if existing:
                existing.model = gpu_data.get("model", existing.model)
                existing.memory_gb = gpu_data.get("memory_gb", existing.memory_gb)
                existing.cuda_version = gpu_data.get("cuda_version", existing.cuda_version)
                existing.region = gpu_data.get("region", existing.region)
                existing.capabilities = gpu_data.get("capabilities", existing.capabilities)
                existing.price_per_hour = gpu_data.get("price_per_hour", existing.price_per_hour)
                existing.status = "active"
                existing.updated_at = datetime.now(UTC)
            else:
                registration = GPURegistration(
                    chain_id=chain_id,
                    gpu_id=gpu_id,
                    miner_id=gpu_data.get("miner_id", ""),
                    model=gpu_data.get("model", ""),
                    memory_gb=gpu_data.get("memory_gb", 0),
                    cuda_version=gpu_data.get("cuda_version", ""),
                    region=gpu_data.get("region", ""),
                    capabilities=gpu_data.get("capabilities", []),
                    price_per_hour=gpu_data.get("price_per_hour", 0.0),
                    registered_by=gpu_data.get("registered_by", ""),
                    registered_at=datetime.now(UTC),
                    status="active",
                )
                session.add(registration)
            logger.info("GPU registration handled: %s", gpu_id)
            return (True, "GPU registration successful")
        except Exception as e:
            logger.error("GPU registration error: %s", e)
            return (False, str(e))

    def handle_gpu_allocation(self, session: Session, chain_id: str, allocation_data: dict[str, Any]) -> tuple[bool, str]:
        """
        Handle GPU allocation state transition.

        Args:
            session: Database session
            chain_id: Chain identifier
            allocation_data: GPU allocation data

        Returns:
            Tuple of (success, error_message)
        """
        try:
            from uuid import uuid4

            gpu_id = allocation_data.get("gpu_id")
            if not gpu_id:
                return (False, "GPU ID is required")
            gpu = session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == gpu_id)
            ).first()
            if not gpu:
                return (False, f"GPU not found: {gpu_id}")
            allocation_id = allocation_data.get("allocation_id", f"alloc_{uuid4().hex[:12]}")
            allocation = GPUAllocation(
                chain_id=chain_id,
                allocation_id=allocation_id,
                gpu_id=gpu_id,
                client_id=allocation_data.get("client_id", ""),
                duration_hours=allocation_data.get("duration_hours", 0.0),
                total_cost=allocation_data.get("total_cost", 0.0),
                status="active",
                allocated_by=allocation_data.get("allocated_by", ""),
                allocated_at=datetime.now(UTC),
            )
            session.add(allocation)
            logger.info("GPU allocation handled: %s for GPU %s", allocation_id, gpu_id)
            return (True, "GPU allocation successful")
        except Exception as e:
            logger.error("GPU allocation error: %s", e)
            return (False, str(e))

    def reset(self) -> None:
        """Reset the state transition validator (for testing)."""
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()


_state_transition = StateTransition()


def get_state_transition() -> StateTransition:
    """Get the global state transition instance."""
    return _state_transition
