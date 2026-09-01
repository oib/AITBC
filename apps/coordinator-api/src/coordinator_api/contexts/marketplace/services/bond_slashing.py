"""Automatic provider-bond slashing (G5).

The on-chain `BOND_SLASH` transaction is already implemented in the blockchain node,
but the coordinator could only trigger it through the manual
`/marketplace/providers/{provider_id}/bonds/slash` admin endpoint. This service
watches for the three conditions named in the architecture review and submits the
slash itself, with a deterministic rule and an auditable record.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from enum import StrEnum
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.utils.units import ait_to_units
from sqlmodel import Session, select

from ....config import settings
from ...infrastructure.domain import Job, Miner
from ...payments.provider_binding import miner_wallet_address
from ..domain.provider_bond import ProviderBond, ProviderBondStatus, _default_bond_min_amount, set_provider_bond_status

logger = get_logger(__name__)


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


def _miner_wallet(miner: Miner) -> str | None:
    return miner_wallet_address(miner)


class BondSlashingService:
    """Submit BOND_SLASH transactions when a provider violates its bond terms."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.blockchain_rpc_url = settings.blockchain_rpc_url
        self.slash_authority = os.getenv("BOND_SLASH_AUTHORITY_ADDRESS", "")
        self.slash_private_key = os.getenv("BOND_SLASH_PRIVATE_KEY", "")
        self.bond_burn_address = os.getenv("BOND_BURN_ADDRESS", "")
        self.chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
        self.tx_fee = int(os.getenv("BOND_SLASH_TX_FEE", "36"))

    def _bond_for_job(self, job: Job) -> ProviderBond | None:
        """Return the active/locked bond backing a job, if any."""
        if not (job.assigned_miner_id and job.payment_id):
            return None
        miner = self.session.get(Miner, job.assigned_miner_id)
        if not miner:
            return None
        wallet = _miner_wallet(miner)
        if not wallet:
            return None

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

        # Fall back to the miner's active bond.
        return self.session.exec(base_stmt.where(ProviderBond.provider_id == miner.id)).first()

    def _compute_slash_amount(self, bond: ProviderBond, condition: SlashingCondition) -> int:
        return _compute_slash_amount(bond, condition)

    async def slash(self, job: Job, condition: SlashingCondition, evidence: str) -> dict[str, Any]:
        """Detect the condition and submit a BOND_SLASH transaction if configured."""
        if not self.slash_authority or not self.slash_private_key or not self.bond_burn_address:
            logger.warning("Bond slashing is not configured; skipping slash for job %s", job.id)
            return {"slashed": False, "reason": "slashing not configured"}

        if not _job_bond_required(job):
            return {"slashed": False, "reason": "job does not require a bond"}

        bond = self._bond_for_job(job)
        if not bond:
            logger.info("No active bond for job %s; nothing to slash", job.id)
            return {"slashed": False, "reason": "no active bond"}

        slash_amount = self._compute_slash_amount(bond, condition)
        if slash_amount <= 0:
            return {"slashed": False, "reason": "computed slash amount is zero"}

        miner = self.session.get(Miner, job.assigned_miner_id)
        provider = _miner_wallet(miner) if miner else ""
        if not provider:
            return {"slashed": False, "reason": "miner has no wallet"}

        bond_id = bond.bond_id or f"bond-{provider}"

        tx = self._build_slash_tx(bond_id, provider, slash_amount)
        try:
            tx["nonce"] = await self._get_nonce(self.slash_authority)
            signed = self._sign_tx(tx)
            result = await self._submit_tx(tx, signed)
        except NetworkError as e:
            logger.error("Network error submitting BOND_SLASH for job %s: %s", job.id, e)
            return {"slashed": False, "reason": "network error", "error": str(e)}
        except Exception as e:
            logger.error("Failed to submit BOND_SLASH for job %s: %s", job.id, e)
            return {"slashed": False, "reason": "transaction error", "error": str(e)}

        tx_hash = result.get("transaction_hash") or result.get("tx_hash") or "unknown"
        new_amount = bond.amount - Decimal(slash_amount)
        if new_amount <= 0:
            status = ProviderBondStatus.LIQUIDATED
        else:
            floor = _default_bond_min_amount()
            required = bond.required_amount if bond.required_amount and bond.required_amount > 0 else floor
            status = ProviderBondStatus.ACTIVE if new_amount >= required else ProviderBondStatus.SHORTFALL

        bond.meta = {
            **(bond.meta or {}),
            "slash_condition": condition.value,
            "slash_evidence": evidence,
            "slash_amount": str(slash_amount),
            "slash_tx_hash": tx_hash,
            "slash_job_id": job.id,
            "slashed_at": datetime.now(UTC).isoformat(),
        }

        bond = set_provider_bond_status(
            self.session,
            bond.provider_id,
            status,
            amount=new_amount,
            bond_id=bond.bond_id,
        )
        logger.info(
            "Bond %s slashed for %s: amount=%s tx=%s job=%s",
            bond_id,
            condition,
            slash_amount,
            tx_hash,
            job.id,
        )
        return {
            "slashed": True,
            "bond_id": bond_id,
            "amount": slash_amount,
            "tx_hash": tx_hash,
            "status": status.value,
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
        try:
            client = AITBCHTTPClient(timeout=5.0)
            r = client.get(f"{self.blockchain_rpc_url}/rpc/account/{address}")
            if isinstance(r, dict):
                return int(r.get("nonce", 0))
            if hasattr(r, "get") and not isinstance(r, dict):  # type: ignore[unreachable]
                return int(r.get("nonce", 0))
        except Exception as e:
            logger.warning("Failed to fetch nonce for %s: %s", address, e)
        return 0

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
