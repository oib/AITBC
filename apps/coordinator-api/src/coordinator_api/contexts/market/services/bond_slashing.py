"""Automatic provider-bond slashing (G5).

The on-chain `BOND_SLASH` transaction is already implemented in the blockchain node,
but the coordinator could only trigger it through the manual
`/market/providers/{provider_id}/bonds/slash` admin endpoint. This service
watches for the three conditions named in the architecture review and submits the
slash itself, with a deterministic rule and an auditable record.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_UP
from enum import StrEnum
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.exceptions import AITBCError, NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.utils.chain_id import resolve_chain_id
from aitbc.utils.units import ait_to_units
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from ....config import settings
from ...infrastructure.domain import Job, Miner
from ...payments.provider_binding import miner_wallet_address
from ..domain.pending_bond_slash import (
    PendingBondSlash,
    PendingBondSlashStatus,
    utcnow,
)
from ....utils.rpc_parse import parse_account_nonce as _parse_account_nonce
from ..domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    _default_bond_min_amount,
    apply_bond_slash_cas,
    stage_bond_projection,
    suspension_event_id,
)
from starlette.concurrency import run_in_threadpool

logger = get_logger(__name__)

# Expected failure surface for the best-effort fallbacks below: aitbc helper
# errors (NetworkError & friends via AITBCError), chain-RPC response decode,
# lazy eth-account/crypto imports and signing (ValueError/ImportError),
# Decimal/unit conversion, and data-shape/runtime errors. NetworkError keeps
# its dedicated handler in slash() before this tuple is consulted.
_OPS_ERRORS: tuple[type[BaseException], ...] = (
    AITBCError,
    AttributeError,
    ImportError,
    InvalidOperation,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

# G5: track the next slash-authority nonce in-memory so multiple BOND_SLASH
# transactions submitted before the next block is mined do not reuse the same
# on-chain nonce (the blockchain RPC would return the existing hash and the
# second slash would never be included).  This is per-coordinator-process state;
# on restart the chain account nonce is the safe baseline and any pending slash
# in the mempool will be observed by the next call's account lookup.
# #779: the counter is per process but hub runs two coordinator workers that
# sign from the same slash authority — the chain stays the only shared source
# of truth, so _get_nonce also reads the signer's pending mempool entries and
# _submit_slash_tx retries once on a nonce refusal.
_slash_nonce: int | None = None
_slash_nonce_lock = asyncio.Lock()
_MEMPOOL_PROBE_LIMIT = 100


def _is_nonce_refusal(exc: Exception) -> bool:
    """The rpc refused the tx on its nonce — 'nonce slot (addr, n) already
    occupied' or 'Invalid nonce', both embedded in the NetworkError detail."""
    s = str(exc).lower()
    return "nonce slot" in s or "invalid nonce" in s


class SlashNonceUnavailableError(RuntimeError):
    """#2999: neither the account nonce read nor the mempool probe produced
    chain truth, so no safe nonce exists — submitting anyway would sign a
    guaranteed on-chain refusal that burns a bounded retry attempt."""


class SlashingCondition(StrEnum):
    DOWNTIME = "downtime"
    FRAUD = "fraud"
    BAD_RESULT = "bad_result"


# Deterministic rates: small for transient unavailability, severe for deliberate fraud.
_SLASH_RATES: dict[SlashingCondition, Decimal] = {
    SlashingCondition.DOWNTIME: Decimal("0.10"),
    SlashingCondition.FRAUD: Decimal("0.50"),
    SlashingCondition.BAD_RESULT: Decimal("0.30"),
}

# #2976: pre-burn appeal window for AUTOMATIC slashes. Detection enqueues a
# durable pending_bond_slash row and freezes eligibility through the #2966
# suspension meta flag; the sweeper executes the existing submit+CAS path once
# the window expires. ``fraud`` has no window — a fraud appeal would be the
# authority appealing to itself — and BOND_SLASH_WINDOW_ENABLED=false restores
# the pre-window immediate execution for every condition.
_APPEAL_WINDOW_ENV: dict[SlashingCondition, str] = {
    SlashingCondition.DOWNTIME: "BOND_SLASH_WINDOW_DOWNTIME_SECONDS",
    SlashingCondition.BAD_RESULT: "BOND_SLASH_WINDOW_BAD_RESULT_SECONDS",
}
_APPEAL_WINDOW_DEFAULTS: dict[SlashingCondition, int] = {
    SlashingCondition.DOWNTIME: 900,
    SlashingCondition.BAD_RESULT: 3600,
}
# ``suspended_by`` value marking a suspension the slash-window detector owns —
# the executor lifts it only when the LAST open pending row for the bond
# resolves, and never touches an operator suspension.
_AUTO_SLASH_SUSPENDED_BY = "bond-slash-window"
# Executor bounds: a claimed row that never records (crash between submit and
# CAS) is reclaimed after this age via a chain point-read; a row that keeps
# failing to submit lands FAILED after this many claims.
_STALE_EXECUTING_SECONDS = 600
_MAX_PENDING_ATTEMPTS = 3
_PENDING_EXECUTE_BATCH = 50
# #2995: statuses that count as "open" for the per-(job, condition) dedup —
# mirrors the partial unique index uq_pending_bond_slash_open_job_condition.
_OPEN_PENDING_STATUSES = (
    PendingBondSlashStatus.PENDING.value,
    PendingBondSlashStatus.EXECUTING.value,
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def _appeal_window_seconds(condition: SlashingCondition) -> int | None:
    """Seconds a detected slash waits for appeal, or ``None`` for immediate.

    ``fraud`` never windows; ``BOND_SLASH_WINDOW_ENABLED=false`` windows
    nothing; a configured 0 window executes inline exactly like today.
    """
    if condition == SlashingCondition.FRAUD:
        return None
    enabled = os.getenv("BOND_SLASH_WINDOW_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return None
    env_name = _APPEAL_WINDOW_ENV.get(condition)
    if env_name is None:
        return None
    return _env_int(env_name, _APPEAL_WINDOW_DEFAULTS[condition])


@dataclass(frozen=True)
class SlashRule:
    condition: SlashingCondition
    rate: Decimal
    min_offenses: int = 1


def _job_bond_required(job: Job) -> bool:
    return bool(job.constraints and job.constraints.get("bond_required"))


def _compute_slash_amount(bond: ProviderBond, condition: SlashingCondition) -> int:
    """Deterministic integer amount to slash from the on-chain bond."""
    rate = _SLASH_RATES.get(condition, Decimal("0.10"))
    amount_decimal = (bond.amount * rate).to_integral_value(rounding=ROUND_UP)
    if amount_decimal <= 0:
        return 0
    if amount_decimal > bond.amount:
        amount_decimal = bond.amount
    return int(amount_decimal)


def _env_evm_address(name: str) -> str:
    """Read an EVM address from the environment, strictly validated.

    Empty/unset stays empty (the caller's missing-config checks handle it); a
    *malformed* value raises instead of propagating a string that can never
    compare equal to any real address.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return ""
    return canonical_address(raw, strict=True)


def _miner_wallet(miner: Miner) -> str | None:
    return miner_wallet_address(miner)


def _bond_payout_wallet(bond: ProviderBond, miner: Miner | None) -> str:
    """Wallet a slash binds/pays out under.

    The creation-verified wallet recorded on the bond (``meta.chain_provider``,
    written at bond create/top-up since #1915) is authoritative — the miner's
    live ``capabilities["wallet_address"]`` is mutable via
    ``PUT /miners/{id}/capabilities`` and may have changed since the proof, so
    it is only the fallback for bonds predating meta recording (#1995).
    """
    proven = (bond.meta or {}).get("chain_provider")
    if isinstance(proven, str) and proven:
        return proven
    if miner is None:
        return ""
    return _miner_wallet(miner) or ""


class BondSlashingService:
    """Submit BOND_SLASH transactions when a provider violates its bond terms."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.blockchain_rpc_url = settings.blockchain_rpc_url
        # Addresses come from env at a configuration boundary: strict
        # canonicalisation converts malformed values (e.g. an inline `#` comment
        # that systemd EnvironmentFile does not strip) into an immediate error
        # instead of a silent every-comparison-fails mismatch downstream.
        self.slash_authority = _env_evm_address("BOND_SLASH_AUTHORITY_ADDRESS")
        self.slash_private_key = self._validated_slash_private_key(
            os.getenv("BOND_SLASH_PRIVATE_KEY", ""), self.slash_authority
        )
        self.bond_burn_address = _env_evm_address("BOND_BURN_ADDRESS")
        self.chain_id = resolve_chain_id()
        self.tx_fee = int(os.getenv("BOND_SLASH_TX_FEE", "36"))

    @staticmethod
    def _validated_slash_private_key(private_key: str, authority: str) -> str:
        """Return the private key only if it controls the configured authority.

        A slash signed by the wrong key will be rejected on-chain. Clearing the
        key here makes every slash call fail-safe ("slashing not configured")
        and logs the mismatch so it is visible in the coordinator logs.
        """
        if not private_key or not authority:
            return private_key
        from eth_account import Account  # function-local: keeps the

        # coincurve/eth-keys chain out of the coordinator import graph
        try:
            derived = Account.from_key(private_key).address
        except (TypeError, ValueError) as exc:
            logger.error("BOND_SLASH_PRIVATE_KEY is not a valid private key: %s", exc)
            return ""
        if derived.lower() != authority.lower():
            logger.error(
                "BOND_SLASH_PRIVATE_KEY does not match BOND_SLASH_AUTHORITY_ADDRESS: derived %s, expected %s",
                derived,
                authority,
            )
            return ""
        return private_key

    def _bond_for_job(self, job: Job) -> ProviderBond | None:
        """Return the active/locked bond backing a job, if any."""
        if not (job.assigned_miner_id and job.payment_id):
            return None
        miner = self.session.get(Miner, job.assigned_miner_id)
        if not miner:
            return None
        # No wallet gate here: the payout wallet resolves from the bond's
        # proven meta at slash time (#1995), so a capabilities-wallet change
        # or removal must not hide an existing bond from this lookup.

        base_stmt = select(ProviderBond).where(
            ProviderBond.bond_id != "",
            ProviderBond.__table__.c.status.in_({ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value}),  # type: ignore[attr-defined]
        )

        # If the job named an exact bond_id, prefer it.
        if job.constraints:
            bond_id = job.constraints.get("bond_id")
            if bond_id:
                bond = self.session.exec(base_stmt.where(ProviderBond.bond_id == str(bond_id))).first()
                if bond:
                    return bond

        # Fall back only when the provider has exactly one active row — provider_id
        # is indexed but not unique, so .first() can bind the wrong bond.
        bonds = list(self.session.exec(base_stmt.where(ProviderBond.provider_id == miner.id)).all())
        if len(bonds) == 1:
            return bonds[0]
        if len(bonds) > 1:
            logger.warning(
                "Multiple active bonds for provider %s; job %s must name bond_id in constraints",
                miner.id,
                job.id,
            )
        return None

    def _compute_slash_amount(self, bond: ProviderBond, condition: SlashingCondition) -> int:
        return _compute_slash_amount(bond, condition)

    async def slash(self, job: Job, condition: SlashingCondition, evidence: str) -> dict[str, Any]:
        """Detect the condition; windowed slashes enqueue, the rest submit now."""
        if not self.slash_authority or not self.slash_private_key or not self.bond_burn_address:
            logger.warning("Bond slashing is not configured; skipping slash for job %s", job.id)
            return {"slashed": False, "reason": "slashing not configured"}

        if not _job_bond_required(job):
            return {"slashed": False, "reason": "job does not require a bond"}

        bond = await run_in_threadpool(self._bond_for_job, job)
        if not bond:
            logger.info("No active bond for job %s; nothing to slash", job.id)
            return {"slashed": False, "reason": "no active bond"}

        cooldown_skip = await self._downtime_cooldown_skip(job, bond, condition)
        if cooldown_skip is not None:
            return cooldown_skip

        # #2976: windowed conditions enqueue a pending row + eligibility
        # suspension instead of submitting inline; fraud, the kill-switch and
        # a 0-second window keep the immediate path.
        window = _appeal_window_seconds(condition)
        if window is not None and window > 0:
            return await self._enqueue_pending_slash(job, bond, condition, evidence, window)
        return await self._execute_slash_now(job, bond, condition, evidence)

    async def _execute_slash_now(
        self, job: Job, bond: ProviderBond, condition: SlashingCondition, evidence: str
    ) -> dict[str, Any]:
        """The pre-#2976 inline path: prepare, build, submit, record."""
        prepared = await self._prepare_slash(job, bond, condition)
        if isinstance(prepared, dict):
            return prepared
        slash_amount, provider, bond_id, expected_amount, expected_updated_at, bond_pk = prepared

        tx = self._build_slash_tx(bond_id, provider, slash_amount)
        try:
            result = await self._submit_slash_tx(tx, job.id)
        except NetworkError as e:
            logger.error("Network error submitting BOND_SLASH for job %s: %s", job.id, e)
            return {"slashed": False, "reason": "network error", "error": str(e)}
        except _OPS_ERRORS as e:
            logger.error("Failed to submit BOND_SLASH for job %s: %s", job.id, e)
            return {"slashed": False, "reason": "transaction error", "error": str(e)}
        if result is None:
            return {"slashed": False, "reason": "nonce refused twice"}

        return self._record_slash_result(
            job.id,
            bond,
            condition,
            evidence,
            bond_id,
            slash_amount,
            result,
            expected_amount=expected_amount,
            expected_updated_at=expected_updated_at,
            bond_pk=bond_pk,
        )

    def _open_pending_for(self, job_id: str, condition: SlashingCondition) -> PendingBondSlash | None:
        """#2995: the open (pending/executing) row for this job+condition, if any."""
        return self.session.exec(
            select(PendingBondSlash).where(
                col(PendingBondSlash.job_id) == job_id,
                col(PendingBondSlash.condition) == condition.value,
                col(PendingBondSlash.status).in_(_OPEN_PENDING_STATUSES),
            )
        ).first()

    async def _enqueue_pending_slash(
        self,
        job: Job,
        bond: ProviderBond,
        condition: SlashingCondition,
        evidence: str,
        window_seconds: int,
    ) -> dict[str, Any]:
        """#2976: record the violation and freeze eligibility — no chain tx.

        Creates the durable ``pending_bond_slash`` row with the slash amount
        snapshotted at detection, and — only when the bond is not already
        suspended — writes the #2966 suspension meta flag so
        ``is_provider_eligible`` reports False while the appeal window runs.
        ``ProviderBond.status`` is untouched: the slasher keeps selecting the
        row and compound violations add independent pending rows. An existing
        suspension (operator or an earlier pending row) is never clobbered —
        the new row just records the live ``suspension_event_id``.

        #2995: at most one OPEN row per (job, condition). The sweeper
        re-detects the same stale job every pass; without the dedup each
        pass queued another slash for the same violation and every open row
        would submit its own BOND_SLASH at window expiry.
        """
        open_row = self._open_pending_for(job.id, condition)
        if open_row is not None:
            return {
                "slashed": False,
                "reason": "slash already pending appeal window",
                "pending_id": open_row.id,
                "window_ends_at": open_row.window_ends_at.isoformat(),
            }
        prepared = await self._prepare_slash(job, bond, condition)
        if isinstance(prepared, dict):
            return prepared
        slash_amount, _provider, bond_id, _expected_amount, _expected_updated_at, bond_pk = prepared

        now = utcnow()
        existing_event = suspension_event_id(bond)
        pending = PendingBondSlash(
            job_id=job.id,
            bond_id=bond_id,
            bond_pk=bond_pk,
            provider_id=bond.provider_id,
            condition=condition.value,
            slash_rate=str(_SLASH_RATES.get(condition, Decimal("0.10"))),
            slash_amount_units=slash_amount,
            pre_slash_amount_units=ait_to_units(bond.amount),
            evidence=evidence,
            suspension_event_id=existing_event or "",
            detected_at=now,
            window_ends_at=now + timedelta(seconds=window_seconds),
        )
        self.session.add(pending)
        if existing_event is None:
            # The first pending row on an unsuspended bond owns the suspension
            # event — its own id — so a slash appeal binds
            # slash_event_id == suspension_event_id == pending.id.
            pending.suspension_event_id = pending.id
            suspended_meta = {
                **(bond.meta or {}),
                "suspension_event_id": pending.id,
                "suspended_at": datetime.now(UTC).isoformat(),
                "suspended_by": _AUTO_SLASH_SUSPENDED_BY,
                "suspension_reason": f"auto-slash-pending:{pending.id} condition={condition.value}",
            }
            if not stage_bond_projection(self.session, bond, meta=suspended_meta):
                self.session.rollback()  # noqa: unawaited-async — sync Session (sqlmodel)
                return {"slashed": False, "reason": "bond changed during slash-window enqueue"}
        try:
            self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
        except IntegrityError:
            # #2995: lost the dedup race — the partial unique index rejected
            # the second open row for this (job, condition). Roll back the
            # staged suspension write with it and report the winner.
            self.session.rollback()  # noqa: unawaited-async — sync Session (sqlmodel)
            winner = self._open_pending_for(job.id, condition)
            logger.info(
                "Bond slash enqueue for job %s lost dedup race; open row is %s",
                job.id,
                winner.id if winner else "<unknown>",
            )
            return {
                "slashed": False,
                "reason": "slash already pending appeal window",
                "pending_id": winner.id if winner else "",
            }
        logger.info(
            "Bond slash for job %s queued as %s (%s, %.0fs window)",
            job.id,
            pending.id,
            condition.value,
            window_seconds,
        )
        return {
            "slashed": False,
            "reason": "slash pending appeal window",
            "pending_id": pending.id,
            "window_ends_at": pending.window_ends_at.isoformat(),
        }

    async def _downtime_cooldown_skip(
        self, job: Job, bond: ProviderBond, condition: SlashingCondition
    ) -> dict[str, Any] | None:
        """G5 follow-up: avoid re-slashing the same continuous downtime incident
        every cycle. A new outage starts when the miner comes back online and
        then goes offline again (heartbeat newer than the last slash).

        Returns the skip result dict, or None when the slash may proceed."""
        if condition != SlashingCondition.DOWNTIME:
            return None
        try:
            cooldown_seconds = int(os.getenv("BOND_SLASH_DOWNTIME_COOLDOWN_SECONDS", "300"))
        except (TypeError, ValueError):
            cooldown_seconds = 300
        bond_meta = bond.meta or {}
        last_slash_str = bond_meta.get("last_downtime_slash_at")
        if not last_slash_str:
            return None
        last_slash = datetime.fromisoformat(str(last_slash_str))
        miner = await run_in_threadpool(self.session.get, Miner, job.assigned_miner_id)
        last_heartbeat = getattr(miner, "last_heartbeat", None)
        # A fresh heartbeat after the last slash means this is a new outage.
        if last_heartbeat and last_heartbeat > last_slash:
            return None
        if datetime.now(UTC) - last_slash < timedelta(seconds=cooldown_seconds):
            logger.info(
                "Downtime slash for job %s is within the %ss cooldown window; skipping",
                job.id,
                cooldown_seconds,
            )
            return {
                "slashed": False,
                "reason": "downtime slash within cooldown",
                "cooldown_seconds": cooldown_seconds,
            }
        return None

    async def _prepare_slash(
        self, job: Job, bond: ProviderBond, condition: SlashingCondition
    ) -> dict[str, Any] | tuple[int, str, str, Decimal, Any, Any]:
        """Compute the slash amount, resolve the provider wallet and snapshot
        the bond row for the post-submit CAS write.

        Returns an early-exit result dict, or
        ``(slash_amount, provider, bond_id, expected_amount, expected_updated_at, bond_pk)``."""
        slash_amount = self._compute_slash_amount(bond, condition)
        if slash_amount <= 0:
            return {"slashed": False, "reason": "computed slash amount is zero"}

        miner = await run_in_threadpool(self.session.get, Miner, job.assigned_miner_id)
        provider = _bond_payout_wallet(bond, miner)
        if not provider:
            return {"slashed": False, "reason": "miner has no wallet"}

        bond_id = bond.bond_id or f"bond-{provider}"

        await run_in_threadpool(self.session.refresh, bond)
        return slash_amount, provider, bond_id, bond.amount, bond.updated_at, bond.id

    def _record_slash_result(
        self,
        job_id: str,
        bond: ProviderBond,
        condition: SlashingCondition,
        evidence: str,
        bond_id: str,
        slash_amount: int,
        result: dict[str, Any],
        *,
        expected_amount: Decimal,
        expected_updated_at: Any,
        bond_pk: Any,
    ) -> dict[str, Any]:
        """Apply the confirmed on-chain slash to the bond row via CAS and build
        the audit result."""
        tx_hash = result.get("transaction_hash") or result.get("tx_hash") or "unknown"
        new_amount = bond.amount - Decimal(slash_amount)
        if new_amount <= 0:
            status = ProviderBondStatus.LIQUIDATED
        else:
            floor = _default_bond_min_amount()
            required = bond.required_amount if bond.required_amount and bond.required_amount > 0 else floor
            status = ProviderBondStatus.ACTIVE if new_amount >= required else ProviderBondStatus.SHORTFALL

        slash_meta: dict[str, Any] = {
            "slash_condition": condition.value,
            "slash_evidence": evidence,
            "slash_amount": str(slash_amount),
            "slash_tx_hash": tx_hash,
            "slash_job_id": job_id,
            "slashed_at": datetime.now(UTC).isoformat(),
        }
        if condition == SlashingCondition.DOWNTIME:
            slash_meta["last_downtime_slash_at"] = slash_meta["slashed_at"]
            slash_meta["last_downtime_slash_job_id"] = job_id
        merged_meta = {
            **(bond.meta or {}),
            **slash_meta,
        }

        applied = apply_bond_slash_cas(
            self.session,
            bond_pk,
            expected_amount=expected_amount,
            expected_updated_at=expected_updated_at,
            new_amount=new_amount,
            status=status,
            meta=merged_meta,
        )
        if applied is None:
            logger.error(
                "BOND_SLASH tx %s for job %s succeeded on chain but the bond row %s "
                "changed before the CAS write; off-chain record not updated",
                tx_hash,
                job_id,
                bond_pk,
            )
            return {
                "slashed": True,
                "bond_id": bond_id,
                "amount": slash_amount,
                "tx_hash": tx_hash,
                "status": status.value,
                "bond_record_applied": False,
                "reason": "bond snapshot stale after on-chain slash",
            }

        logger.info(
            "Bond %s slashed for %s: amount=%s tx=%s job=%s",
            bond_id,
            condition,
            slash_amount,
            tx_hash,
            job_id,
        )
        return {
            "slashed": True,
            "bond_id": bond_id,
            "amount": slash_amount,
            "tx_hash": tx_hash,
            "status": status.value,
            "bond_record_applied": True,
        }

    def _build_slash_tx(self, bond_id: str, provider: str, slash_amount: int) -> dict[str, Any]:
        return {
            "from": self.slash_authority,
            "to": self.bond_burn_address,
            "amount": 0,
            "fee": self.tx_fee,
            "nonce": 0,
            "type": "BOND_SLASH",
            "chain_id": self.chain_id,
            "payload": {
                "bond_id": bond_id,
                "provider": provider,
                "amount": ait_to_units(slash_amount),
                "to": self.bond_burn_address,
            },
        }

    async def _get_nonce(self, address: str) -> int:
        global _slash_nonce
        chain_nonce: int | None = None
        try:
            client = AITBCHTTPClient(timeout=5.0)
            r = client.get(f"{self.blockchain_rpc_url}/rpc/account/{address}")
            chain_nonce = _parse_account_nonce(r)
            if chain_nonce is None:
                # #3015: HTTP 200 with a missing/invalid nonce is a malformed
                # response, not nonce 0 — the mempool probe below is the only
                # remaining source of truth.
                logger.warning(
                    "Account nonce response for %s carried no valid nonce; degrading to mempool probe",
                    address,
                )
        except (AITBCError, TypeError, ValueError) as e:
            logger.warning("Failed to fetch nonce for %s: %s", address, e)

        pending = self._pending_mempool_nonce(address)
        if pending is not None:
            chain_nonce = pending if chain_nonce is None else max(chain_nonce, pending)

        if chain_nonce is None:
            # #2999/#3015: a failed or malformed read must not fabricate nonce
            # 0 — that submits a guaranteed-refused tx and spends one of the
            # bounded attempts on noise. Raise so the caller records a
            # truthful retryable failure.
            raise SlashNonceUnavailableError(
                f"could not establish slash-authority nonce for {address}: "
                "account nonce read and mempool probe both unavailable"
            )

        async with _slash_nonce_lock:
            if _slash_nonce is None or chain_nonce > _slash_nonce:
                _slash_nonce = chain_nonce
            else:
                _slash_nonce += 1
            return _slash_nonce

    def _pending_mempool_nonce(self, sender: str) -> int | None:
        """Highest pending-mempool nonce + 1 for the signer; None when the
        mempool holds none or the probe fails (caller degrades to the sealed
        nonce, and the submit retry covers the admitted-but-unlisted window)."""
        try:
            client = AITBCHTTPClient(timeout=5.0)
            r = client.get(f"{self.blockchain_rpc_url}/mempool?chain_id={self.chain_id}&limit={_MEMPOOL_PROBE_LIMIT}")
        except (AITBCError, AttributeError, TypeError, ValueError) as e:
            logger.warning("Mempool nonce probe failed for %s: %s", sender, e)
            return None
        pending = [
            tx["nonce"]
            for tx in r.get("transactions") or []
            if isinstance(tx, dict)
            and str(tx.get("from") or tx.get("sender") or "").lower() == sender.lower()
            and isinstance(tx.get("nonce"), int)
            and not isinstance(tx.get("nonce"), bool)
        ]
        return max(pending) + 1 if pending else None

    async def _submit_slash_tx(self, tx: dict[str, Any], job_id: str) -> dict[str, Any] | None:
        """Assign the nonce, sign and submit. On a nonce refusal — the other
        uvicorn worker took the same slot — drop the cached counter, re-read
        chain+mempool, re-sign (the nonce is inside the signature) and resubmit
        exactly once; a second refusal is logged and reported unslashed."""
        global _slash_nonce
        result: dict[str, Any] | None = None
        for attempt in (0, 1):
            tx["nonce"] = await self._get_nonce(self.slash_authority)
            signed = self._sign_tx(tx)
            try:
                result = await self._submit_tx(tx, signed)
                break
            except NetworkError as e:
                if not _is_nonce_refusal(e):
                    raise
                if attempt == 1:
                    logger.error("BOND_SLASH for job %s refused on nonce twice; slash not submitted", job_id)
                    return None
                logger.warning(
                    "BOND_SLASH nonce %s refused for job %s; re-reading chain+mempool and retrying once",
                    tx["nonce"],
                    job_id,
                )
                async with _slash_nonce_lock:
                    _slash_nonce = None
        return result

    def _sign_tx(self, tx: dict[str, Any]) -> str:
        from aitbc.crypto.crypto import sign_transaction_hash
        from eth_utils import keccak

        has_amount = "amount" in tx
        tx_for_sign = {k: v for k, v in tx.items() if k != "signature" and not (has_amount and k == "value")}
        canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
        signing_hash = "0x" + keccak(canonical).hex()
        return sign_transaction_hash(signing_hash, self.slash_private_key)

    async def _submit_tx(self, tx: dict[str, Any], signature: str) -> dict[str, Any]:
        client = AITBCHTTPClient(timeout=10.0)
        body = {**tx, "signature": signature}
        return client.post(f"{self.blockchain_rpc_url}/rpc/transaction", json=body)

    # ------------------------------------------------------------------
    # #2976: appeal-window executor — the only path that submits BOND_SLASH
    # for windowed conditions. Driven by BondSlashSweeper.run_once.
    # ------------------------------------------------------------------

    async def execute_due_pending(self) -> dict[str, int]:
        """One executor pass: reclaim stale claims, then run due rows.

        Returns outcome counts for logging/tests. Detection never submits a
        chain transaction, so every windowed slash reaches the chain here.
        """
        counts = {"reconciled": 0, "executed": 0, "retried": 0, "failed": 0, "moot": 0, "skipped": 0}
        if not (self.slash_authority and self.slash_private_key and self.bond_burn_address):
            return counts
        now = utcnow()
        stale_cutoff = now - timedelta(seconds=_STALE_EXECUTING_SECONDS)
        stale_rows = list(
            self.session.exec(
                select(PendingBondSlash)
                .where(col(PendingBondSlash.status) == PendingBondSlashStatus.EXECUTING.value)
                .where(col(PendingBondSlash.claimed_at).is_not(None))
                .where(col(PendingBondSlash.claimed_at) < stale_cutoff)
            ).all()
        )
        for row in stale_rows:
            counts[await self._reclaim_stale_executing(row)] += 1
        due_rows = list(
            self.session.exec(
                select(PendingBondSlash)
                .where(col(PendingBondSlash.status) == PendingBondSlashStatus.PENDING.value)
                .where(col(PendingBondSlash.window_ends_at) <= now)
                .order_by(col(PendingBondSlash.window_ends_at))
                .limit(_PENDING_EXECUTE_BATCH)
            ).all()
        )
        for row in due_rows:
            counts[await self._execute_pending_row(row)] += 1
        return counts

    def _claim_pending(self, row: PendingBondSlash) -> bool:
        """CAS-claim pending->executing; only the winner submits."""
        now = utcnow()
        result = self.session.execute(
            sa_update(PendingBondSlash)
            .where(col(PendingBondSlash.id) == row.id)
            .where(col(PendingBondSlash.status) == PendingBondSlashStatus.PENDING.value)
            .values(
                status=PendingBondSlashStatus.EXECUTING.value,
                claimed_at=now,
                attempts=PendingBondSlash.attempts + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            return False
        self.session.refresh(row)
        return True

    def _bond_for_pending(self, row: PendingBondSlash) -> ProviderBond | None:
        """Resolve the bond row the pending slash targets.

        Prefers the primary key pinned at detection; falls back to the
        (provider_id, bond_id) pair — the same lookup slash-appeal review uses.
        """
        if row.bond_pk:
            bond = self.session.get(ProviderBond, row.bond_pk)
            if bond is not None and bond.bond_id == row.bond_id:
                return bond
        return self.session.exec(
            select(ProviderBond).where(
                ProviderBond.provider_id == row.provider_id,
                ProviderBond.bond_id == row.bond_id,
            )
        ).first()

    async def _execute_pending_row(self, row: PendingBondSlash) -> str:
        """Claim and execute one due row; returns the outcome bucket."""
        if not self._claim_pending(row):
            return "skipped"
        try:
            return await self._run_claimed_pending(row)
        except NetworkError as e:
            logger.error("Network error executing pending bond slash %s: %s", row.id, e)
            return self._record_attempt_failure(row, e)
        except _OPS_ERRORS as e:
            logger.error("Failed to execute pending bond slash %s: %s", row.id, e)
            return self._record_attempt_failure(row, e)

    async def _run_claimed_pending(self, row: PendingBondSlash) -> str:
        """Submit+record body for a claimed row — mirrors _execute_slash_now
        but takes the detection-time amount snapshot off the row."""
        bond = self._bond_for_pending(row)
        slashable = {
            ProviderBondStatus.ACTIVE.value,
            ProviderBondStatus.LOCKED.value,
            ProviderBondStatus.SHORTFALL.value,
        }
        if bond is None or bond.status not in slashable or bond.bond_id != row.bond_id:
            self._finish_pending(row, PendingBondSlashStatus.CANCELLED, last_error="bond no longer slashable")
            self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
            return "moot"
        await run_in_threadpool(self.session.refresh, bond)
        slash_amount = min(row.slash_amount_units, int(bond.amount))
        if slash_amount <= 0:
            self._finish_pending(row, PendingBondSlashStatus.CANCELLED, last_error="bond amount exhausted")
            self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
            return "moot"
        miner = self.session.get(Miner, row.provider_id)
        provider = _bond_payout_wallet(bond, miner)
        if not provider:
            return self._record_attempt_failure(row, RuntimeError("miner has no wallet"))

        expected_amount, expected_updated_at, bond_pk = bond.amount, bond.updated_at, bond.id
        bond_id = bond.bond_id or row.bond_id
        condition = SlashingCondition(row.condition)

        tx = self._build_slash_tx(bond_id, provider, slash_amount)
        result = await self._submit_slash_tx(tx, row.job_id or row.id)
        if result is None:
            return self._record_attempt_failure(row, RuntimeError("nonce refused twice"))

        recorded = self._record_slash_result(
            row.job_id,
            bond,
            condition,
            row.evidence,
            bond_id,
            slash_amount,
            result,
            expected_amount=expected_amount,
            expected_updated_at=expected_updated_at,
            bond_pk=bond_pk,
        )
        tx_hash = recorded.get("tx_hash") or ""
        self._finish_pending(row, PendingBondSlashStatus.EXECUTED, submitted_tx_hash=tx_hash)
        self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
        self._post_execute_pending(row)
        return "executed"

    def _finish_pending(
        self,
        row: PendingBondSlash,
        status: PendingBondSlashStatus,
        *,
        submitted_tx_hash: str = "",
        last_error: str = "",
    ) -> None:
        """Terminal/stage transition on the row; caller owns the commit."""
        row.status = status.value
        if submitted_tx_hash:
            row.submitted_tx_hash = submitted_tx_hash
        row.claimed_at = None
        row.last_error = last_error[:500]
        row.updated_at = utcnow()
        self.session.add(row)

    def _record_attempt_failure(self, row: PendingBondSlash, exc: BaseException) -> str:
        """Bounded retry: back to pending until _MAX_PENDING_ATTEMPTS, then FAILED.

        ``window_ends_at`` stays in the past so the next sweep retries
        immediately; the attempt counter (incremented at claim) bounds the
        loop. FAILED rows need operator attention — the violation was real but
        the slash could not be submitted.
        """
        if row.attempts >= _MAX_PENDING_ATTEMPTS:
            self._finish_pending(row, PendingBondSlashStatus.FAILED, last_error=str(exc))
            self.session.commit()
            logger.error(
                "Pending bond slash %s (bond %s, job %s) FAILED after %s attempts: %s",
                row.id,
                row.bond_id,
                row.job_id,
                row.attempts,
                exc,
            )
            return "failed"
        self._finish_pending(row, PendingBondSlashStatus.PENDING, last_error=str(exc))
        self.session.commit()
        return "retried"

    def _post_execute_pending(self, row: PendingBondSlash) -> None:
        """Post-execution bookkeeping once a pending row lands EXECUTED.

        Suspension lift rule: the auto-slash suspension covers ALL pending rows
        detected under one ``suspension_event_id`` (compound violations), so it
        is lifted only when no pending/executing rows remain for the bond AND
        the live suspension is still the one the detector wrote
        (``suspended_by == _AUTO_SLASH_SUSPENDED_BY``). An operator suspension
        is never lifted here. In the same commit, open slash appeals bound to
        the lifted event close as rejected — the window expired and the slash
        executed, so the appeal is moot.
        """
        open_rows = list(
            self.session.exec(
                select(PendingBondSlash).where(
                    col(PendingBondSlash.bond_id) == row.bond_id,
                    col(PendingBondSlash.status).in_(
                        [PendingBondSlashStatus.PENDING.value, PendingBondSlashStatus.EXECUTING.value]
                    ),
                )
            ).all()
        )
        if open_rows:
            return
        bond = self._bond_for_pending(row)
        if bond is None:
            return
        meta = bond.meta or {}
        event_id = meta.get("suspension_event_id")
        if meta.get("suspended_by") != _AUTO_SLASH_SUSPENDED_BY or not event_id:
            return
        resolved_meta = {key: value for key, value in meta.items() if key != "suspension_event_id"}
        if not stage_bond_projection(self.session, bond, meta=resolved_meta):
            self.session.rollback()
            logger.error(
                "Pending slash %s executed but the suspension lift CAS failed for bond %s; retry manually",
                row.id,
                row.bond_id,
            )
            return
        from ...governance.domain.slash_appeal import SlashAppeal, SlashAppealStatus

        self.session.execute(
            sa_update(SlashAppeal)
            .where(col(SlashAppeal.bond_id) == row.bond_id)
            .where(col(SlashAppeal.slash_event_id) == event_id)
            .where(col(SlashAppeal.status).in_([SlashAppealStatus.SUBMITTED.value, SlashAppealStatus.UNDER_REVIEW.value]))
            .values(
                status=SlashAppealStatus.REJECTED.value,
                reviewer_notes="window expired; slash executed",
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        self.session.commit()
        logger.info(
            "Pending slash %s executed; lifted auto-slash suspension %s on bond %s and closed bound appeals",
            row.id,
            event_id,
            row.bond_id,
        )

    async def _reclaim_stale_executing(self, row: PendingBondSlash) -> str:
        """Recover a row claimed >_STALE_EXECUTING_SECONDS ago (crash between
        submit and record). Point-reads the chain: if the slash landed, mark
        EXECUTED with the observed hash and run post-steps; otherwise return
        the row to PENDING for a fresh submit."""
        from ...blockchain.services.blockchain import BlockchainService

        try:
            chain = await run_in_threadpool(BlockchainService().get_bond, row.bond_id)
        except _OPS_ERRORS as e:
            logger.warning("Chain point-read failed reconciling pending slash %s: %s", row.id, e)
            return "skipped"
        if self._chain_shows_slash(chain, row):
            observed = ""
            if isinstance(chain, dict):
                observed = str(chain.get("slashed_tx_hash") or "")
            now = utcnow()
            result = self.session.execute(
                sa_update(PendingBondSlash)
                .where(col(PendingBondSlash.id) == row.id)
                .where(col(PendingBondSlash.status) == PendingBondSlashStatus.EXECUTING.value)
                .values(
                    status=PendingBondSlashStatus.EXECUTED.value,
                    submitted_tx_hash=observed or row.submitted_tx_hash,
                    claimed_at=None,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                return "skipped"
            self.session.refresh(row)  # noqa: unawaited-async — sync Session (sqlmodel)
            self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
            self._post_execute_pending(row)
            logger.info("Pending slash %s reconciled as executed from chain state (tx %s)", row.id, observed)
            return "reconciled"
        # The submit never landed — safe to resubmit.
        now = utcnow()
        result = self.session.execute(
            sa_update(PendingBondSlash)
            .where(col(PendingBondSlash.id) == row.id)
            .where(col(PendingBondSlash.status) == PendingBondSlashStatus.EXECUTING.value)
            .values(status=PendingBondSlashStatus.PENDING.value, claimed_at=None, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) == 1:
            self.session.commit()  # noqa: unawaited-async — sync Session (sqlmodel)
            return "retried"
        return "skipped"

    @staticmethod
    def _chain_shows_slash(chain: Any, row: PendingBondSlash) -> bool:
        """Heuristic: did THIS bond's slash land on-chain?

        ``status == "slashed"`` is definitive; otherwise a recorded
        ``slashed_tx_hash`` or a chain amount below the detection snapshot
        counts. Compound rows share a bond, so a sibling's slash can satisfy
        this — acceptable per the ratified design (the bond was slashed; the
        row's own submit is then moot) and documented here.
        """
        if not isinstance(chain, dict) or chain.get("success") is not True:
            return False
        if chain.get("status") == "slashed":
            return True
        amount = chain.get("amount")
        amount_units = amount if isinstance(amount, int) and not isinstance(amount, bool) else None
        dropped = amount_units is not None and row.pre_slash_amount_units > 0 and amount_units < row.pre_slash_amount_units
        if dropped:
            return True
        # A recorded slash hash with an unreadable amount still counts as
        # landed; with a readable amount it must accompany the drop above.
        return bool(chain.get("slashed_tx_hash")) and amount_units is None
