"""Blockchain client for pool-hub reward distribution (v0.6.7 §B2).

Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
- Submit reward transactions on job completion
- Register miners on blockchain via GPU registration endpoint
- Track reward payouts to prevent duplicates, via the reward_payouts unique
  constraint (RewardPolicy's in-process state cannot survive a restart or span
  replicas, so it is bookkeeping only -- not the guarantee)

Reward transactions are signed with secp256k1 (Ethereum-style) over the
canonical JSON of the signed fields, matching the blockchain node's verifier
(see ``aitbc.crypto.transaction_service``).
"""

from __future__ import annotations

import hashlib
import json
import logging

import httpx
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.config.hub import hub_agent_url
from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.market import BlockchainRPCClient
from aitbc.rewards import (
    MAX_REWARD_PER_EPOCH,
    MINIMUM_PAYOUT,
    REWARD_EPOCH_LENGTH,
    REWARD_PER_SHARE,
    RewardPolicy,
    calculate_block_reward,
    calculate_epoch_number,
)
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS

from ..models import Miner, RewardPayout, RewardShare
from ..services.reward_shares import VERIFIED_CHAIN_SOURCE

logger = logging.getLogger(__name__)

# Mempool probe page size for the nonce floor — same order as the settlement
# path's _FUNDING_LOCK_MEMPOOL_LIMIT.
_MEMPOOL_PROBE_LIMIT = 500

# Defaults for the reconciliation sweep; the scheduler passes the operator's
# settings values explicitly.
DEFAULT_RECONCILE_MIN_AGE_SECONDS = 300.0
DEFAULT_MAX_RECONCILE_ATTEMPTS = 3
# Blocks an epoch must be sealed past its end before it is payable. PBFT
# finality is fast, but paying on the epoch boundary itself leaves no room
# for a reorg of the last blocks of the epoch.
DEFAULT_FINALITY_CONFIRMATIONS = 3
# Cap on chain submissions per distribute run. The node's mempool admission
# refuses nonces more than ``mempool_nonce_lookahead`` (default 16) ahead of
# the account nonce, so a large epoch must be paid over several cycles —
# the remainder is simply claimed next run (claims dedupe per miner+epoch).
DEFAULT_MAX_SUBMISSIONS_PER_CYCLE = 12


class _LookupUnknown:
    """Sentinel: a chain/mempool read failed — absence is NOT proven.

    Reconciliation must never treat an RPC error as "the payout never
    landed": a sealed tx whose lookup errored would be judged absent and
    resubmitted — a double payment. Unknown lookups skip the row for this
    cycle instead (#3058 respin).
    """


_LOOKUP_UNKNOWN = _LookupUnknown()

# Expected operational failure surface: DB session work, reward RPC calls
# (httpx transport/status errors), and payout data-shape errors.
_OPS_ERRORS = (
    SQLAlchemyError,
    httpx.HTTPError,
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
)

# Transaction fields covered by the signature — must match the node verifier.
_SIGNED_FIELDS = ("from", "to", "amount", "fee", "nonce", "payload", "type", "chain_id")


def _lowest_free_nonce(sealed: int, occupied: frozenset[int] | set[int]) -> int:
    """Lowest nonce >= ``sealed`` not in ``occupied`` — gap-fill semantics.

    Port of ``pending_nonce_floor`` (cli/aitbc_cli/utils/nonce.py, #2745):
    apply seals nonces sequentially, so the lowest free slot is the only
    one guaranteed to land; jumping past a stranded entry ahead of a hole
    would sign into future-nonce territory that never seals.
    """
    nonce = sealed
    while nonce in occupied:
        nonce += 1
    return nonce


def _canonical_signing_message(tx: dict[str, Any]) -> bytes:
    """Return the exact bytes that are hashed and signed for a transaction."""
    signed = {k: tx[k] for k in _SIGNED_FIELDS if k in tx}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()


class PoolHubBlockchainClient:
    """Blockchain client for pool-hub reward distribution and miner registration.

    Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
    - Submit reward transactions on job completion
    - Register miners on blockchain via agent-coordinator
    - Track reward payouts to prevent duplicates
    """

    def __init__(
        self,
        rpc_url: str = BLOCKCHAIN_RPC_URL,
        chain_id: str = "ait-hub",
        coordinator_url: str | None = None,
        signer_address: str | None = None,
        signer_private_key: str | None = None,
        api_key: str | None = None,
        finality_confirmations: int = DEFAULT_FINALITY_CONFIRMATIONS,
        reconcile_min_age_seconds: float = DEFAULT_RECONCILE_MIN_AGE_SECONDS,
        max_reconcile_attempts: int = DEFAULT_MAX_RECONCILE_ATTEMPTS,
        max_submissions_per_cycle: int = DEFAULT_MAX_SUBMISSIONS_PER_CYCLE,
    ) -> None:
        self._rpc = BlockchainRPCClient(rpc_url=rpc_url, api_key=api_key)
        self._chain_id = chain_id
        self._coordinator_url = coordinator_url or hub_agent_url() or ""
        self._reward_policy = RewardPolicy()
        self._signer_address = signer_address or os.getenv("POOL_REWARD_ADDRESS")
        self._signer_private_key = signer_private_key or os.getenv("POOL_REWARD_PRIVATE_KEY")
        self._finality_confirmations = finality_confirmations
        self._reconcile_min_age_seconds = reconcile_min_age_seconds
        self._max_reconcile_attempts = max_reconcile_attempts
        self._max_submissions_per_cycle = max_submissions_per_cycle

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def reward_policy(self) -> RewardPolicy:
        return self._reward_policy

    @property
    def rpc_client(self) -> BlockchainRPCClient:
        return self._rpc

    async def submit_reward_transaction(
        self,
        miner_address: str,
        amount: int,
        job_id: str,
        nonce: int | None = None,
    ) -> dict[str, Any]:
        """Submit a signed reward transaction to the blockchain.

        Args:
            miner_address: Miner's wallet address (recipient)
            amount: Reward amount in compute-units (smallest unit)
            job_id: Job ID for tracking (included in payload). For epoch
                payouts this is ``epoch-<n>-<miner_id>`` so reconciliation
                can find the tx by its unique payload job_id.
            nonce: Explicit sender nonce. When omitted the nonce is probed
                mempool-aware via :meth:`_probe_reward_nonce`. Callers
                submitting a batch MUST pass sequential nonces — blocks do
                not seal between loop iterations, so re-reading the sealed
                nonce per tx hands every payout after the first the same
                nonce and they collide (#3058).

        Returns:
            Blockchain response dict with tx_hash

        Raises:
            ValueError: If reward signer key/address is not configured or mismatched.
        """
        tx_data = await self._build_reward_tx(miner_address, amount, job_id, nonce)
        return await self._submit_signed_tx(tx_data, miner_address=miner_address, amount=amount, job_id=job_id)

    async def _build_reward_tx(
        self,
        miner_address: str,
        amount: int,
        job_id: str,
        nonce: int | None,
    ) -> dict[str, Any]:
        """Build and sign the reward transaction without submitting it.

        Split from :meth:`submit_reward_transaction` so the payout path can
        persist the content-deterministic tx hash on the claim row BEFORE
        the chain submit — a lost submit response then still leaves
        reconciliation an exact lookup key (#3058 respin).
        """
        if not self._signer_private_key or not self._signer_address:
            raise ValueError("Reward signer not configured; set POOL_REWARD_PRIVATE_KEY and POOL_REWARD_ADDRESS")

        from eth_keys import keys
        from eth_utils import keccak

        pk = keys.PrivateKey(bytes.fromhex(self._signer_private_key.removeprefix("0x")))
        derived_address = pk.public_key.to_checksum_address()
        if self._signer_address.lower() != derived_address.lower():
            raise ValueError(
                f"POOL_REWARD_ADDRESS {self._signer_address} does not match address derived from key ({derived_address})"
            )

        # Canonical tx includes the mining-reward payload; payload is part of the signed fields.
        tx_data: dict[str, Any] = {
            "from": self._signer_address,
            "to": miner_address,
            "amount": amount,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce if nonce is not None else await self._probe_reward_nonce(),
            "payload": {"purpose": "mining_reward", "job_id": job_id},
            "type": "TRANSFER",
            "chain_id": self._chain_id,
        }

        signature = pk.sign_msg_hash(keccak(_canonical_signing_message(tx_data)))
        tx_data["signature"] = signature.to_bytes().hex()
        return tx_data

    def _expected_tx_hash(self, tx_data: dict[str, Any]) -> str:
        """The tx_hash the node WILL assign this transaction (#3058 respin).

        The node's ``compute_tx_hash`` is sha256 over the canonical JSON of
        the *normalized* admitted body
        (``aitbc_chain.rpc.utils.normalize_transaction_data`` +
        ``aitbc_chain.mempool_common.compute_tx_hash``): keys ``chain_id``,
        ``type`` (upper), ``from``/``to`` (stripped), ``amount`` and
        ``value`` (both the int amount), ``fee``, ``nonce``, ``payload``,
        ``signature``. Our reward txs already satisfy every normalization
        rule (int amount/fee/nonce, dict payload, TRANSFER, stripped
        addresses), so the hash is computable before submit. If the node's
        normalization ever drifts, the stored hash simply stops matching —
        the job_id sweep remains the fallback, never a false positive.
        """
        payload = tx_data.get("payload")
        normalized = {
            "chain_id": tx_data["chain_id"],
            "type": str(tx_data.get("type") or "TRANSFER").upper(),
            "from": str(tx_data["from"]).strip(),
            "to": str(tx_data["to"]).strip(),
            "amount": int(tx_data["amount"]),
            "value": int(tx_data["amount"]),
            "fee": int(tx_data.get("fee", DEFAULT_TX_FEE_UNITS)),
            "nonce": int(tx_data["nonce"]),
            "payload": payload if isinstance(payload, dict) else {},
            "signature": tx_data.get("signature"),
        }
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        return f"0x{hashlib.sha256(canonical).hexdigest()}"

    async def _submit_signed_tx(
        self,
        tx_data: dict[str, Any],
        *,
        miner_address: str,
        amount: int,
        job_id: str,
    ) -> dict[str, Any]:
        """POST a signed reward tx and log the submission."""
        result = await self._rpc.submit_transaction(tx_data)
        logger.info("Reward tx submitted: miner=%s, amount=%d, job=%s", miner_address, amount, job_id)
        return result

    async def register_miner_on_chain(self, signed_tx: dict[str, Any]) -> dict[str, Any]:
        """Submit a miner's signed GPU_REGISTER transaction on its behalf.

        The GPU register route only accepts a signed envelope (FORK-OOB-1,
        issue #382) and pool-hub holds no miner key — signing stays with the
        miner (``aitbc gpu onchain register`` or the gpu_service relayer on
        the miner's own host). This method is a relay, not a second
        registration path.

        Args:
            signed_tx: Signed GPU_REGISTER transaction envelope.

        Returns:
            Blockchain response dict (tx hash, pending status).
        """
        result = await self._rpc.register_gpu(signed_tx)
        logger.info("Miner registration submitted on-chain: chain=%s", self._chain_id)
        return result

    async def distribute_rewards(self, block_height: int, session: AsyncSession) -> list[dict[str, Any]]:
        """Distribute rewards for every finalized epoch with verified shares, at most once per miner per epoch.

        #3058 safety properties, all fail-closed:

        - **Epoch finality**: only the epoch that ended at least
          ``finality_confirmations`` blocks ago is payable
          (``calculate_epoch_number(block_height) - 1``). The in-progress
          epoch is never paid — contributions can still arrive for it.
        - **Verified shares only**: payout amounts derive from the persistent
          ``reward_shares`` table (``verified=True`` rows written exclusively
          by ``record_verified_share`` with chain evidence). The in-memory
          ``RewardPolicy`` contribution ledger is bookkeeping only and feeds
          nothing here — it cannot survive a restart and accepts
          caller-asserted shares.
        - **Nonce gap-fill**: nonces are allocated mempool-aware as the
          LOWEST free slot at/above the sealed nonce (a stranded entry
          ahead of a hole cannot push later payouts into never-sealing
          future-nonce territory), marked occupied per submit, and
          re-probed after any failure.
        - **Durable claim**: each payout is claimed (committed) before the
          chain submit; the ``reward_payouts`` unique constraint arbitrates
          duplicates. See :meth:`_claim_payout`.

        Args:
            block_height: Current sealed block height
            session: Database session providing the idempotency guarantee

        Returns:
            List of payout results (one per payable miner). Miners already
            claimed for this epoch are reported ``"already_paid"``.
        """
        latest_payable = calculate_epoch_number(block_height) - 1
        if latest_payable < 0:
            return []

        # One read for the whole run: verified shares grouped by epoch, then
        # every finalized epoch with shares is paid in order. Iterating all
        # payable epochs (not just the latest) means a scheduler outage does
        # not silently skip an epoch — unpaid claims simply dedupe on rerun.
        shares_by_epoch = await self._verified_shares_by_epoch(session)
        if not shares_by_epoch:
            return []

        payouts: list[dict[str, Any]] = []
        # Lazy nonce state for this run: (sealed_nonce, occupied_nonces)
        # probed once, then the lowest free nonce is handed out per submit —
        # gap-filling like cli/aitbc_cli/utils/nonce.py so a stranded mempool
        # entry ahead of a hole cannot push later payouts into future-nonce
        # territory where apply would never seal them. Re-probed (state reset
        # to None) after any failure: the failed tx may or may not hold a
        # mempool slot — the probe is the only safe answer.
        nonce_state: tuple[int, frozenset[int]] | None = None
        submissions = 0
        for epoch_number in sorted(e for e in shares_by_epoch if e <= latest_payable):
            # Finality gate: the epoch must be sealed AND far enough behind
            # the head that its last blocks cannot be reorged out from under
            # the payout decision.
            epoch_end = epoch_number * REWARD_EPOCH_LENGTH + REWARD_EPOCH_LENGTH - 1
            if block_height < epoch_end + 1 + self._finality_confirmations:
                logger.info(
                    "Reward epoch %s not final at height %s (needs > %s); skipping",
                    epoch_number,
                    block_height,
                    epoch_end + self._finality_confirmations,
                )
                continue

            shares_by_miner = shares_by_epoch[epoch_number]
            total_shares = sum(shares_by_miner.values())
            epoch_start = epoch_number * REWARD_EPOCH_LENGTH
            total_pool = calculate_block_reward(epoch_start) * REWARD_EPOCH_LENGTH
            if total_pool <= 0 or total_shares <= 0:
                continue

            cap_hit, nonce_state, submissions = await self._pay_epoch_miners(
                session=session,
                epoch_number=epoch_number,
                shares_by_miner=shares_by_miner,
                total_pool=total_pool,
                total_shares=total_shares,
                payouts=payouts,
                nonce_state=nonce_state,
                submissions=submissions,
            )
            if cap_hit:
                return payouts
        return payouts

    async def _pay_epoch_miners(
        self,
        session: AsyncSession,
        epoch_number: int,
        shares_by_miner: dict[str, int],
        total_pool: int,
        total_shares: int,
        payouts: list[dict[str, Any]],
        nonce_state: tuple[int, frozenset[int]] | None,
        submissions: int,
    ) -> tuple[bool, tuple[int, frozenset[int]] | None, int]:
        """Pay every miner's share of one finalized epoch.

        Returns ``(cap_hit, nonce_state, submissions)`` — ``cap_hit`` True
        means the per-cycle submission budget ran out and the caller must
        stop iterating epochs entirely.
        """
        for miner_id, shares in shares_by_miner.items():
            if submissions >= self._max_submissions_per_cycle:
                # The node's mempool_nonce_lookahead refuses nonces too
                # far ahead of the account nonce; unclaimed miners simply
                # pay on the next cycle — claims dedupe per miner+epoch.
                logger.warning(
                    "Reward submission cap %d reached; deferring remaining epoch-%s payouts to the next cycle",
                    self._max_submissions_per_cycle,
                    epoch_number,
                )
                return True, nonce_state, submissions
            proportional = int(total_pool * shares / total_shares)
            amount = min(proportional, MAX_REWARD_PER_EPOCH)
            if amount < MINIMUM_PAYOUT:
                continue
            outcome, nonce_state = await self._payout_one_miner(
                session=session,
                epoch_number=epoch_number,
                miner_id=miner_id,
                amount=amount,
                nonce_state=nonce_state,
            )
            if outcome is not None:
                payouts.append(outcome)
                if outcome["status"] == "paid":
                    submissions += 1
        return False, nonce_state, submissions

    async def _payout_one_miner(
        self,
        session: AsyncSession,
        epoch_number: int,
        miner_id: str,
        amount: int,
        nonce_state: tuple[int, frozenset[int]] | None,
    ) -> tuple[dict[str, Any] | None, tuple[int, frozenset[int]] | None]:
        """Claim and pay one miner's epoch reward; returns (outcome, nonce_state).

        ``outcome`` is None only when the miner is skipped before any claim
        bookkeeping (below-minimum handled by caller; here every path yields
        a status dict). ``nonce_state`` is the caller's (sealed, occupied)
        nonce cursor: probed lazily, the lowest free nonce is taken per
        submit and marked occupied on success, reset to None on failure so
        the next payout re-probes the mempool.
        """
        # #1401: miner_id is the pool-hub identifier, not a wallet
        # address — resolve the registered wallet before claiming a payout.
        # A miner without wallet_address is not payable yet; skipping
        # without a claim lets a later epoch pay once it registers.
        miner = (
            await session.execute(select(Miner).where(Miner.miner_id == miner_id, Miner.chain_id == self._chain_id))
        ).scalar_one_or_none()
        wallet_address = miner.wallet_address if miner else None
        if not wallet_address:
            logger.warning(
                "Skipping reward for %s in epoch %s: miner has no wallet_address",
                miner_id,
                epoch_number,
            )
            return (
                {
                    "miner_id": miner_id,
                    "amount": amount,
                    "epoch": epoch_number,
                    "status": "no_wallet_address",
                },
                nonce_state,
            )

        claim = await self._claim_payout(
            session=session,
            miner_id=miner_id,
            epoch_number=epoch_number,
            amount=amount,
        )
        if claim is None:
            logger.info(
                "Skipping reward for %s in epoch %s: already claimed or paid",
                miner_id,
                epoch_number,
            )
            return (
                {
                    "miner_id": miner_id,
                    "amount": amount,
                    "epoch": epoch_number,
                    "status": "already_paid",
                },
                nonce_state,
            )

        if nonce_state is None:
            nonce_state = await self._probe_reward_nonce_state()
        sealed_nonce, occupied = nonce_state
        nonce = _lowest_free_nonce(sealed_nonce, occupied)
        job_id = f"epoch-{epoch_number}-{miner_id}"
        outcome = await self._pay_claim(
            session=session,
            claim=claim,
            wallet_address=wallet_address,
            job_id=job_id,
            nonce=nonce,
        )
        if outcome["status"] == "paid":
            # Mark the spent nonce occupied so the next payout gap-fills
            # above it (and above any still-pending mempool entries).
            nonce_state = (sealed_nonce, occupied | {nonce})
        else:
            # The failed tx may still occupy a mempool slot — the next
            # iteration re-probes instead of guessing.
            nonce_state = None
        return outcome, nonce_state

    async def _verified_shares_by_epoch(self, session: AsyncSession) -> dict[int, dict[str, int]]:
        """Verified share rows for this chain, grouped epoch -> miner -> shares.

        Only ``verified=True`` rows count — the in-memory RewardPolicy
        ledger feeds nothing here. One query per distribution run; epochs
        that are not yet finalized are filtered by the caller.
        """
        rows = (
            (
                await session.execute(
                    select(RewardShare).where(
                        RewardShare.chain_id == self._chain_id,
                        RewardShare.verified.is_(True),
                        # Payout-side source allowlist (#3058 respin): only
                        # shares written by the verified-chain feed count.
                        # record_verified_share accepts a caller-chosen
                        # ``source`` tag; without this filter a feed bug
                        # (or a future caller) could mint payout-eligible
                        # rows under an unvetted source.
                        RewardShare.source == VERIFIED_CHAIN_SOURCE,
                    )
                )
            )
            .scalars()
            .all()
        )
        by_epoch: dict[int, dict[str, int]] = {}
        for row in rows:
            # Belt and braces: the SQL filter is the guarantee, this guards
            # against a driver/dialect quirk ever returning unverified rows.
            if not row.verified:
                continue
            epoch = by_epoch.setdefault(int(row.epoch_number), {})
            epoch[row.miner_id] = epoch.get(row.miner_id, 0) + int(row.shares)
        return by_epoch

    async def _pay_claim(
        self,
        session: AsyncSession,
        claim: RewardPayout,
        wallet_address: str,
        job_id: str,
        nonce: int,
    ) -> dict[str, Any]:
        """Submit the chain tx for a claimed payout row and record the outcome.

        Shared by :meth:`distribute_rewards` and the reconciliation sweep so
        both write paid/failed identically. Returns the payout result dict.
        """
        try:
            tx_data = await self._build_reward_tx(wallet_address, claim.amount, job_id, nonce)
            # Persist the deterministic tx hash and payout recipient BEFORE
            # the chain submit (#3058 respin): tx_hash is content-derived, so
            # it is knowable pre-submit; if the response is lost, the row
            # still carries the exact lookup key reconciliation needs, and
            # ``recipient`` pins WHERE this attempt paid even if the miner
            # later rotates wallets (sealed-tx matching uses it, so a
            # rotation can never turn a landed payout into a "proven absent"
            # resubmit = double payment). Committed for the same #2863
            # reason as the claim itself: durable before money moves.
            claim.tx_hash = self._expected_tx_hash(tx_data)
            claim.recipient = wallet_address
            await session.commit()
            result = await self._submit_signed_tx(tx_data, miner_address=wallet_address, amount=claim.amount, job_id=job_id)
            if not isinstance(result, dict) or result.get("success") is False:
                raise ValueError(f"blockchain rejected reward transaction: {result!r}")
            # The node answers POST /rpc/transaction with
            # {"success": true, "transaction_hash": ...} — "tx_hash" is the
            # legacy/test alias. Reading only "tx_hash" recorded every
            # payout as paid with an empty hash (#1570 residual).
            # Canonical key first: if a response ever carries both with
            # different values, the node's own field name wins over the
            # alias. A non-string or empty hash is not a hash — skip it
            # and route through the failure path like a missing one.
            tx_hash = next(
                (c for c in (result.get("transaction_hash"), result.get("tx_hash")) if isinstance(c, str) and c),
                "",
            )
            if not tx_hash:
                # A success response without any transaction hash is
                # ambiguous — the tx may or may not have reached the
                # mempool. Never mark it paid: an empty-hash "paid" row
                # wedges the (miner, chain, epoch) UNIQUE slot forever
                # while the miner was never provably paid. Route it
                # through the failure path so reconciliation resolves the
                # claim against the chain, exactly like a network error.
                raise ValueError(f"reward transaction response carried no tx hash: {result!r}")
            if tx_hash != claim.tx_hash:
                # The hash is content-deterministic; a mismatch means the
                # node's normalization drifted from _expected_tx_hash.
                # The response hash is authoritative — record it, but say
                # so: reconciliation's exact-hash lookup now depends on
                # the job_id sweep.
                logger.warning(
                    "Reward tx hash mismatch for %s: predicted %s, node returned %s",
                    claim.miner_id,
                    claim.tx_hash,
                    tx_hash,
                )
            claim.status = "paid"
            claim.tx_hash = tx_hash
            claim.paid_at = datetime.now(UTC)
            await session.commit()
            return {
                "miner_id": claim.miner_id,
                "amount": claim.amount,
                "tx_hash": tx_hash,
                "epoch": claim.epoch_number,
                "status": "paid",
            }
        except _OPS_ERRORS as e:
            logger.error("Failed to distribute reward to %s: %s", claim.miner_id, e)
            # Leave the claim in place: the miner may or may not have been paid on
            # chain, and re-attempting blindly is how double payments happen.
            # The reconciliation sweep resolves the row against the chain.
            claim.status = "failed"
            await session.commit()
            return {
                "miner_id": claim.miner_id,
                "amount": claim.amount,
                "error": str(e),
                "epoch": claim.epoch_number,
                "status": "failed",
            }

    async def _mempool_occupied_nonces(self, sender: str) -> frozenset[int] | None:
        """Nonces ``sender`` has pending in the mempool; None when the probe failed.

        Port of the settlement path's mempool nonce probe
        (apps/blockchain-node ``escrow_routes_helpers``) to the reward
        signer (#3058): without it every payout in a batch signs the same
        sealed nonce because no block seals between loop iterations.

        Returns None (distinct from an empty set) when the probe itself
        fails — callers degrade to ``sealed`` exactly like settlement,
        where the node's nonce-slot refusal is the backstop. The ordinary
        mempool listing is used deliberately: it counts EVERY occupant,
        including entries a rejection-aware view would exclude, so it can
        only over-occupy (skip a nonce), never under-occupy (collide).
        """
        try:
            data = await self._rpc.get_mempool(chain_id=self._chain_id, limit=_MEMPOOL_PROBE_LIMIT)
        except _OPS_ERRORS as e:
            logger.warning("mempool nonce probe failed for %s: %s", sender, e)
            return None
        occupied: set[int] = set()
        for tx in data.get("transactions") or []:
            if not isinstance(tx, dict):
                continue
            if str(tx.get("from") or tx.get("sender") or "").lower() != sender.lower():
                continue
            nonce = tx.get("nonce")
            if isinstance(nonce, int) and not isinstance(nonce, bool) and nonce >= 0:
                occupied.add(nonce)
        return frozenset(occupied)

    async def _probe_reward_nonce_state(self) -> tuple[int, frozenset[int]]:
        """(sealed nonce, mempool-occupied nonces) for the reward signer."""
        if not self._signer_address:
            raise ValueError("Reward signer not configured; set POOL_REWARD_ADDRESS")
        sealed = await self._rpc.get_nonce(self._signer_address, self._chain_id)
        occupied = await self._mempool_occupied_nonces(self._signer_address)
        # Probe failure degrades to "nothing pending" — same fail-open-to-
        # sealed posture as settlement; local batch allocation still
        # increments, so the only exposure is a same-nonce refusal, never a
        # silent double-sign of identical content (tx hash is deterministic).
        return sealed, occupied if occupied is not None else frozenset()

    async def _probe_reward_nonce(self) -> int:
        """Lowest free nonce for the reward signer (single-shot probe)."""
        sealed, occupied = await self._probe_reward_nonce_state()
        return _lowest_free_nonce(sealed, occupied)

    async def _claim_payout(
        self,
        session: AsyncSession,
        miner_id: str,
        epoch_number: int,
        amount: int,
    ) -> RewardPayout | None:
        """Reserve the right to pay one miner for one epoch.

        Returns the claimed row, or None if this (miner, chain, epoch) is already claimed.
        The unique constraint does the arbitration, so two replicas racing on the same
        payout produce exactly one winner.
        """
        payout = RewardPayout(
            miner_id=miner_id,
            chain_id=self._chain_id,
            epoch_number=epoch_number,
            amount=amount,
            status="pending",
        )
        session.add(payout)
        try:
            await session.flush()
            # #2863: the 'pending' claim must be COMMITTED before the chain
            # submit — a crash between an uncommitted flush and the
            # paid/failed commit rolls the claim back, and the next run
            # pays the same miner+epoch twice. This commits whatever else
            # is pending on the session too; distribute_rewards only reads
            # before this point, so the claim is the sole write.
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # #3058: a 'retry' row is a payout the reconciliation sweep
            # proved never reached the chain — the (miner, chain, epoch)
            # slot is occupied but payable again. Reuse the row instead of
            # inserting a duplicate; 'pending'/'paid'/'failed'/'exhausted'
            # rows still refuse, which is what makes the constraint the
            # guarantee.
            existing = (
                await session.execute(
                    select(RewardPayout).where(
                        RewardPayout.miner_id == miner_id,
                        RewardPayout.chain_id == self._chain_id,
                        RewardPayout.epoch_number == epoch_number,
                    )
                )
            ).scalar_one_or_none()
            # Respin fix: the reclaim IS a resubmission attempt — it must
            # consume the same bounded budget the sweep uses, and a row at
            # or over the cap is operator-only ('exhausted' or a 'retry'
            # row that already spent its attempts). Without the guard a
            # parked row was resurrected and paid in the same scheduler
            # cycle, making the cap ineffective.
            if (
                existing is None
                or existing.status != "retry"
                or (existing.reconcile_attempts or 0) >= self._max_reconcile_attempts
            ):
                return None
            existing.status = "pending"
            # The stored ``amount`` stays authoritative: payout sizing is
            # locked at first compute, matching the bridge-monitor
            # convention ("a retry pays exactly that amount") — shares can
            # grow for LATER epochs but this epoch's obligation is fixed.
            # tx_hash/recipient reset: _pay_claim re-derives both for the
            # new nonce before submit.
            existing.tx_hash = None
            existing.recipient = None
            existing.paid_at = None
            existing.reconcile_attempts = (existing.reconcile_attempts or 0) + 1
            await session.flush()
            await session.commit()
            return existing
        return payout

    # ------------------------------------------------------------------
    # Reconciliation sweep (#3058)
    # ------------------------------------------------------------------

    async def reconcile_payouts(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        min_age_seconds: float | None = None,
    ) -> dict[str, int]:
        """Resolve ambiguous payout rows against the chain (#3058).

        The failure paths promise a reconciliation that never existed: a
        lost post-submit response or a crash between claim-commit and
        submit-resolution leaves a ``pending``/``failed`` row whose UNIQUE
        (miner, chain, epoch) slot would otherwise wedge forever.

        For every ``pending``/``failed``/``retry`` row older than
        ``min_age_seconds`` (so in-flight submits are never raced):

        - a sealed chain tx matching the payout's unique job_id marks the
          row ``paid`` with its tx_hash;
        - a matching mempool entry means the tx is still in flight — the
          row is left alone;
        - neither means the payout provably never landed: the row becomes
          ``retry`` and, while ``reconcile_attempts`` is below the cap, is
          resubmitted immediately through :meth:`_pay_claim`. At the cap
          the row stays ``retry`` for operator attention — it is never
          silently dropped and never paid twice.

        Returns a per-outcome summary dict.
        """
        min_age = self._reconcile_min_age_seconds if min_age_seconds is None else min_age_seconds
        cutoff = (now or datetime.now(UTC)) - timedelta(seconds=min_age)
        rows = (
            (
                await session.execute(
                    select(RewardPayout).where(
                        RewardPayout.chain_id == self._chain_id,
                        RewardPayout.status.in_(("pending", "failed", "retry")),
                        RewardPayout.created_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        summary = {
            "checked": 0,
            "paid": 0,
            "still_pending": 0,
            "retry": 0,
            "exhausted": 0,
            "unknown": 0,
            "deferred": 0,
            "errors": 0,
        }
        # Resubmits share the distribute run's submission budget: the node's
        # mempool_nonce_lookahead refuses nonces too far ahead, so a sweep
        # must not fire an unbounded batch of proven-absent resubmits either.
        resubmits = 0
        for row in rows:
            summary["checked"] += 1
            try:
                outcome, submitted = await self._reconcile_row(
                    session,
                    row,
                    resubmit_allowed=resubmits < self._max_submissions_per_cycle,
                )
            except _OPS_ERRORS as e:
                summary["errors"] += 1
                logger.warning("Reward payout reconciliation failed for %s epoch %s: %s", row.miner_id, row.epoch_number, e)
                continue
            if submitted:
                resubmits += 1
            if outcome in summary:
                summary[outcome] += 1
        if summary["checked"]:
            logger.info("Reward payout reconciliation: %s", summary)
        return summary

    async def _reconcile_row(
        self,
        session: AsyncSession,
        row: RewardPayout,
        *,
        resubmit_allowed: bool = True,
    ) -> tuple[str, bool]:
        """Resolve one ambiguous payout row.

        Returns ``(summary_bucket, submitted)`` — ``submitted`` is True only
        when this call actually fired a chain submit (the resubmit path),
        so the caller can meter the batch against the nonce-lookahead cap.
        """
        job_id = f"epoch-{row.epoch_number}-{row.miner_id}"
        expected_to = await self._miner_wallet_address(session, row.miner_id)
        # The recipient persisted at submit time is authoritative for
        # matching: if the miner rotated wallets after the payout was
        # attempted, the landed tx went to the OLD address and must still
        # match — otherwise a proven-landed payout reads as absent and
        # gets resubmitted (double payment).
        match_to = row.recipient or expected_to
        sealed_tx_hash = await self._find_sealed_reward_tx(row, job_id, match_to)
        if isinstance(sealed_tx_hash, _LookupUnknown):
            return "unknown", False
        if sealed_tx_hash:
            row.status = "paid"
            row.tx_hash = sealed_tx_hash
            row.paid_at = datetime.now(UTC)
            await session.commit()
            return "paid", False
        pending = await self._find_pending_reward_tx(row, job_id, match_to)
        if pending is None:
            return "unknown", False
        if pending:
            return "still_pending", False
        # Provably absent from both the chain and the mempool: the payout
        # never landed. Bound the automatic retries; an exhausted row
        # becomes 'exhausted' — a terminal operator-only state the sweep
        # no longer probes and _claim_payout refuses to resurrect.
        if row.reconcile_attempts >= self._max_reconcile_attempts:
            if row.status != "exhausted":
                row.status = "exhausted"
                await session.commit()
            return "exhausted", False
        wallet_address = expected_to
        if not wallet_address:
            # No payable destination — resubmitting cannot succeed. Park the
            # row as 'retry' (NOT exhausted): it stays reclaimable so a
            # miner that re-registers a wallet still gets paid, and the
            # sweep keeps proving absence until then. Do not burn an
            # attempt — nothing was submitted.
            if row.status != "retry":
                row.status = "retry"
                await session.commit()
            return "exhausted", False
        if not resubmit_allowed:
            return "deferred", False
        row.status = "pending"
        row.reconcile_attempts = (row.reconcile_attempts or 0) + 1
        await session.commit()  # durable before the chain submit (#2863)
        nonce = await self._probe_reward_nonce()
        outcome = await self._pay_claim(
            session=session,
            claim=row,
            wallet_address=wallet_address,
            job_id=job_id,
            nonce=nonce,
        )
        return ("retry" if outcome["status"] == "failed" else "paid"), True

    async def _find_sealed_reward_tx(
        self, row: RewardPayout, job_id: str, expected_to: str | None = None
    ) -> str | _LookupUnknown | None:
        """Return the tx_hash of THIS payout's sealed reward tx, if provably present.

        Three-state result (#3058 respin): a hash string = found; None =
        provably absent (every lookup succeeded and nothing matched);
        ``_LOOKUP_UNKNOWN`` = at least one lookup failed, so absence is NOT
        proven and the row must be skipped this cycle — never resubmitted.
        """
        exact_error = False
        if row.tx_hash:
            # The deterministic hash persisted at submit time is the exact
            # lookup key: content-addressed, so a hit IS this payout's tx.
            try:
                tx = await self._rpc.get_transaction(row.tx_hash, chain_id=self._chain_id)
            except _OPS_ERRORS as e:
                logger.warning("exact reward-tx lookup failed for %s: %s", row.tx_hash, e)
                exact_error = True
                tx = None
            if isinstance(tx, dict) and tx and self._tx_matches_payout(tx, row, expected_to, sealed=True):
                return str(tx.get("tx_hash") or tx.get("transaction_hash") or row.tx_hash)
        try:
            txs = await self._rpc.query_transactions(
                transaction_type="TRANSFER",
                job_id=job_id,
                chain_id=self._chain_id,
                limit=10,
            )
        except _OPS_ERRORS as e:
            logger.warning("sealed reward-tx lookup failed for %s: %s", job_id, e)
            # The job_id sweep is the authoritative absence proof — its
            # failure alone makes the row unknown.
            return _LOOKUP_UNKNOWN
        for tx in txs:
            if not self._tx_matches_payout(tx, row, expected_to, sealed=True):
                continue
            tx_hash = tx.get("tx_hash") or tx.get("transaction_hash")
            if isinstance(tx_hash, str) and tx_hash:
                return tx_hash
        if exact_error:
            # The sweep found nothing, but the exact-hash lookup never
            # answered — the tx could be sealed under that hash with a
            # payload the server-side job_id filter did not surface.
            return _LOOKUP_UNKNOWN
        return None

    async def _find_pending_reward_tx(self, row: RewardPayout, job_id: str, expected_to: str | None = None) -> bool | None:
        """Mempool state for this payout: True = in flight, False = absent, None = unknown."""
        if not self._signer_address:
            # Without the signer address no mempool entry can be proven to
            # be ours — and none can be proven absent either.
            return None
        try:
            data = await self._rpc.get_mempool(chain_id=self._chain_id, limit=_MEMPOOL_PROBE_LIMIT)
        except _OPS_ERRORS as e:
            logger.warning("mempool lookup failed for %s: %s", job_id, e)
            return None
        for tx in data.get("transactions") or []:
            if not isinstance(tx, dict) or not self._tx_matches_payout(tx, row, expected_to, sealed=False):
                continue
            return True
        return False

    @staticmethod
    def _tx_amount(tx: dict[str, Any]) -> int | None:
        """Transaction amount: ``value`` is the sealed-row field, ``amount``
        the mempool/submission field — accept either, ``value`` first."""
        raw = tx.get("value")
        if raw is None:
            raw = tx.get("amount")
        if raw is None or isinstance(raw, bool):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _tx_matches_payout(
        self,
        tx: dict[str, Any],
        row: RewardPayout,
        expected_to: str | None = None,
        *,
        sealed: bool,
    ) -> bool:
        """Match a chain/mempool tx to a payout row (#3058 respin).

        Real RPC shapes differ between the two lookups and BOTH are handled:

        - Sealed rows (``/rpc/transactions``, ``/rpc/transaction/{hash}`` —
          ``aitbc_chain.rpc.transactions._tx_result_row``) carry
          ``sender``/``recipient``/``value``/``nonce``/``fee``/``status``/
          ``block_height`` — NOT ``from``/``to``/``amount``.
        - Mempool entries are the normalized admitted body: ``from``/``to``/
          ``amount`` AND ``value`` (utils.normalize_transaction_data sets
          both), no status/block_height.

        Requires, for a sealed match: ``status == "confirmed"`` AND a
        non-null integer ``block_height`` — an unconfirmed or rejected row
        must never mark a payout paid. Both shapes require the unique
        payload job_id (``epoch-<n>-<miner_id>``), the ``mining_reward``
        purpose, the exact amount, the reward signer as sender, and — when
        the payout recipient is known — the exact recipient.
        """
        if not self._payload_matches_payout(tx, row):
            return False
        if sealed and not self._sealed_fields_present(tx):
            return False
        if self._tx_amount(tx) != row.amount:
            return False
        return self._tx_sender_recipient_match(tx, expected_to)

    @staticmethod
    def _payload_matches_payout(tx: dict[str, Any], row: RewardPayout) -> bool:
        """The unique payload job_id + mining_reward purpose must match."""
        payload = tx.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}
        if not isinstance(payload, dict):
            return False
        expected_job_id = f"epoch-{row.epoch_number}-{row.miner_id}"
        return payload.get("job_id") == expected_job_id and payload.get("purpose") == "mining_reward"

    @staticmethod
    def _sealed_fields_present(tx: dict[str, Any]) -> bool:
        """A sealed match requires a confirmed, block-sealed tx — rejected
        or unsealed rows in the transactions table are dead letters, not
        payments."""
        if tx.get("status") != "confirmed":
            return False
        block_height = tx.get("block_height")
        return isinstance(block_height, int) and not isinstance(block_height, bool) and block_height >= 0

    def _tx_sender_recipient_match(self, tx: dict[str, Any], expected_to: str | None) -> bool:
        """Sender must be the reward signer (the only account issuing
        mining_reward txs) and, when the payout recipient is known, the
        recipient must match exactly."""
        sender = tx.get("sender") or tx.get("from")
        if not self._signer_address or not isinstance(sender, str):
            return False
        if sender.lower() != self._signer_address.lower():
            return False
        if expected_to is None:
            return True
        recipient = tx.get("recipient") or tx.get("to")
        return isinstance(recipient, str) and recipient.lower() == expected_to.lower()

    async def _miner_wallet_address(self, session: AsyncSession, miner_id: str) -> str | None:
        miner = (
            await session.execute(select(Miner).where(Miner.miner_id == miner_id, Miner.chain_id == self._chain_id))
        ).scalar_one_or_none()
        return miner.wallet_address if miner else None

    async def has_been_paid(self, session: AsyncSession, miner_id: str, epoch_number: int) -> bool:
        """Return True if this miner already has a payout row for this epoch."""
        result = await session.execute(
            select(RewardPayout).where(
                RewardPayout.miner_id == miner_id,
                RewardPayout.chain_id == self._chain_id,
                RewardPayout.epoch_number == epoch_number,
            )
        )
        return result.scalar_one_or_none() is not None

    def record_contribution(self, miner_id: str, score: float, shares: int | None = None) -> None:
        """Record a miner's contribution in the in-memory RewardPolicy ledger.

        #3058: this is bookkeeping ONLY — it feeds no payout. Payout shares
        come exclusively from the persistent, evidence-backed ``reward_shares``
        table via ``record_verified_share``. Kept for API compatibility and
        scoring consumers; caller-asserted shares here can never move money.

        Args:
            miner_id: Miner ID
            score: Contribution score (0-100)
            shares: Compute-seconds contributed (defaults to REWARD_PER_SHARE)
        """
        self._reward_policy.record_contribution(
            miner_id=miner_id,
            score=score,
            shares=shares if shares is not None else REWARD_PER_SHARE,
        )
