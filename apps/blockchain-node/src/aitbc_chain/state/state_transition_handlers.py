"""Post-apply effect handlers (escrow/governance/bond/GPU/deactivation) for ``StateTransition`` (#1867 pure-move split).

Import ``aitbc_chain.state.state_transition`` first (it wires these
mixins into ``StateTransition``); this module is not meant to be imported
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import json
from ..base_models import (
    Block,
    Bond,
    ChainParameter,
    IPFSSubscription,
    ValidatorDeactivation,
    _to_ait_address,
    record_chain_parameter_history,
)
from .gpu_resources import GPUAllocation, GPURegistration, GPU_STATUS_DEACTIVATED
from aitbc.crypto.signature_recovery import canonical_address
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
from sqlmodel import Session, select
from typing import Any
from .state_transition import (
    PROTOCOL_MAX_LOCK_DURATION,
    _bond_slash_authority,
    _governance_execute_payload,
    _gpu_price_per_hour_in_range,
    _is_bond_burn,
    _is_bond_escrow,
    _parse_validator_deactivation_payload,
    _sealed_execute_exists,
    _sealed_propose_execution_payload,
    _validator_deactivation_authority,
    logger,
)


class _HandlerMixin:
    if TYPE_CHECKING:

        def _bond_release_payout(
            self, session: Session, chain_id: str, sender_addr: str, release_amount: int, tx_hash: str
        ) -> str | None: ...
        def _bond_slash_move(self, session: Session, chain_id: str, slash_amount: int, tx_hash: str) -> str | None: ...

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
        block_height: int | None = None,
        block_version: int = 2,
    ) -> None:
        """Apply a GOVERNANCE_EXECUTE transaction payload to chain parameters.

        The transaction payload must contain:
        - proposal_id: the on-chain governance proposal being executed
        - execution_payload: the payload stored in the proposal (or an override)

        For a parameter_change action, the execution payload should contain:
        - parameter: the parameter name
        - value: the new string value

        ``block_height`` records the height the change took effect: the
        current row gets ``applied_height`` and a ``chain_parameter_history``
        entry, so resolvers answer with the value in force at the block
        being validated rather than the latest value. Without it a parameter
        set mid-history wrongly governs earlier blocks during replay — the
        GOVERNANCE_EXECUTE sender gate applies at every version once set.
        """
        from ..base_models import GovernanceProposal

        payload = _governance_execute_payload(tx_data, tx_hash)
        if payload is None:
            return

        proposal_id = payload.get("proposal_id") or tx_data.get("proposal_id")
        execution_payload = payload.get("execution_payload", {}) or {}
        action = execution_payload.get("action", "parameter_change")

        if not proposal_id:
            logger.warning("GOVERNANCE_EXECUTE tx %s missing proposal_id", tx_hash)
            return

        if block_version >= 13 and block_height is not None:
            # v13: apply the sealed PROPOSE's stored payload, not the one the
            # transaction carries. validate_transaction already proved them
            # equal, so this can only differ if a code path ever bypassed
            # validation — in which case the stored payload is the safe choice.
            found, stored_payload = _sealed_propose_execution_payload(session, chain_id, str(proposal_id), block_height)
            if not found:
                logger.warning("GOVERNANCE_EXECUTE tx %s proposal %s not sealed in an earlier block", tx_hash, proposal_id)
                return
            if _sealed_execute_exists(session, chain_id, str(proposal_id), block_height):
                logger.warning("GOVERNANCE_EXECUTE tx %s proposal %s already executed", tx_hash, proposal_id)
                return
            execution_payload = stored_payload or {}
            action = execution_payload.get("action", "parameter_change")

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
            self._apply_parameter_change(session, chain_id, execution_payload, proposal_id, tx_hash, block_height)
        elif action == "set_governance_address":
            # Reserved for adding/removing governance signing addresses
            logger.info("GOVERNANCE_EXECUTE set_governance_address not implemented: %s", execution_payload)
        else:
            logger.info("GOVERNANCE_EXECUTE unknown action %s: %s", action, execution_payload)

    @staticmethod
    def _apply_parameter_change(
        session: Session,
        chain_id: str,
        execution_payload: dict[str, Any],
        proposal_id: Any,
        tx_hash: str,
        block_height: int | None,
    ) -> None:
        parameter = execution_payload.get("parameter")
        value = execution_payload.get("value")
        if not parameter:
            logger.warning("GOVERNANCE_EXECUTE tx %s parameter_change missing parameter name", tx_hash)
            return
        # ``value: null`` records a deliberate clear ("") — storing
        # str(None) would write the literal "None", which resolvers feed
        # to canonical_address as a nonsense address.
        stored_value = "" if value is None else str(value)
        existing = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == parameter,
            )
        ).first()
        if existing:
            existing.value = stored_value
            existing.proposal_id = proposal_id
            if block_height is not None:
                existing.applied_height = block_height
            existing.updated_at = datetime.now(UTC)
        else:
            session.add(
                ChainParameter(
                    chain_id=chain_id,
                    parameter=parameter,
                    value=stored_value,
                    proposal_id=proposal_id,
                    applied_height=block_height,
                )
            )
        if block_height is not None:
            record_chain_parameter_history(
                session, chain_id, parameter, stored_value, proposal_id, block_height, overwrite=True
            )
        # autoflush is off on these sessions — flush so a later tx in the
        # same block sees the new parameter value in resolver queries.
        session.flush()
        logger.info(
            "Chain parameter %s updated to %s by proposal %s (tx %s)",
            parameter,
            value,
            proposal_id,
            tx_hash,
        )

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
        block_height: int | None = None,
        *,
        block_version: int | None = None,
        block_time: datetime | None = None,
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

        # v18 (deterministic committed apply): the sealed header timestamp
        # replaces wall-clock ``datetime.now(UTC)`` for every committed value
        # — locked_until, created_at/updated_at and the release verdict all
        # become pure functions of (transaction, prior state, block header).
        # Below v18 (or with no block_time) the volatile path stays for
        # replay of the pre-v18 era.
        now = (
            block_time if (block_version is not None and block_version >= 18 and block_time is not None) else datetime.now(UTC)
        )
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        if tx_type == "BOND_LOCK":
            return self._bond_lock_effect(
                session,
                chain_id,
                payload,
                tx_hash,
                sender_addr,
                recipient_addr,
                value,
                provider,
                bond_id,
                now,
                block_height,
                block_version,
            )
        if tx_type == "BOND_RELEASE":
            return self._bond_release_effect(
                session,
                chain_id,
                payload,
                tx_hash,
                sender_addr,
                recipient_addr,
                value,
                provider,
                bond_id,
                now,
                block_height,
                block_version,
            )
        if tx_type == "BOND_SLASH":
            return self._bond_slash_effect(
                session,
                chain_id,
                payload,
                tx_hash,
                sender_addr,
                recipient_addr,
                value,
                provider,
                bond_id,
                now,
                block_height,
                block_version,
            )
        return None

    def _bond_lock_effect(
        self,
        session: Session,
        chain_id: str,
        payload: dict[str, Any],
        tx_hash: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        provider: str,
        bond_id: str,
        now: datetime,
        block_height: int | None,
        block_version: int | None,
    ) -> str | None:
        if not _is_bond_escrow(recipient_addr):
            return "recipient is not the bond escrow address"
        if value <= 0:
            return "non-positive lock value"
        lock_days = int(payload.get("lock_days", 30))
        # Reuse an existing active bond with the same id if it exists (top-up).
        existing = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id)).first()
        horizon_error, locked_until = self._bond_lock_horizon(existing, now, lock_days, block_version)
        if horizon_error is not None:
            return horizon_error
        if existing:
            topup_error = self._bond_topup_error(existing, sender_addr, payload, value, bond_id, block_version)
            if topup_error is not None:
                return topup_error
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
        return None

    def _bond_lock_horizon(
        self, existing: Bond | None, now: datetime, lock_days: int, block_version: int | None
    ) -> tuple[str | None, datetime]:
        """v22 lock horizon: ``min(now + lock_days, created_at +
        PROTOCOL_MAX_LOCK_DURATION)`` — the absolute ceiling anchored on the
        immutable created_at; post-ceiling top-ups refused. Below v22 (or for
        non-consensus callers) the plain ``now + lock_days`` applies.
        Unreachable for consensus transactions (validate rejects first);
        defense for non-consensus callers of this handler."""
        if block_version is None or block_version < 22:
            return None, now + timedelta(days=lock_days)
        # v22: absolute ceiling anchored on the immutable created_at —
        # min(now + lock_days, created_at + PROTOCOL_MAX_LOCK_DURATION).
        created = (existing.created_at if existing is not None else now) or now
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        ceiling = created + PROTOCOL_MAX_LOCK_DURATION
        if existing is not None and now >= ceiling:
            return "bond lock horizon exhausted", now
        return None, min(now + timedelta(days=lock_days), ceiling)

    def _bond_topup_error(
        self,
        existing: Bond,
        sender_addr: str,
        payload: dict[str, Any],
        value: int,
        bond_id: str,
        block_version: int | None,
    ) -> str | None:
        """v22 defense-in-depth top-up guards: the shared verdict already
        refused these for consensus txs; keep apply honest for callers that
        bypass validate. Below v22 there are no extra guards."""
        if block_version is None or block_version < 22:
            return None
        if existing.status != "active":
            return f"BOND_LOCK top-up refused: bond {bond_id} is {existing.status}, not active"
        if sender_addr != _to_ait_address(existing.provider or ""):
            return "top-up signer is not the bond provider"
        if _to_ait_address(payload.get("provider") or "") != _to_ait_address(existing.provider or ""):
            return "top-up provider does not match bond provider"
        if existing.amount + value > 2**63 - 1:
            return "BOND_LOCK refused: bond amount overflow"
        return None

    def _bond_release_effect(
        self,
        session: Session,
        chain_id: str,
        payload: dict[str, Any],
        tx_hash: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        provider: str,
        bond_id: str,
        now: datetime,
        block_height: int | None,
        block_version: int | None,
    ) -> str | None:
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
        if block_version is not None and block_version >= 22:
            # v22: the persisted provider is authoritative — matching
            # payload.provider proved nothing (BOND-RELEASE-001).
            if sender_addr != _to_ait_address(bond.provider or ""):
                return "not signed by the bond provider"
        lock_error = self._bond_release_lock_error(bond, now, bond_id, block_version)
        if lock_error is not None:
            return lock_error
        release_amount = bond.amount
        if release_amount <= 0:
            return "bond has nothing to release"
        payout_error = self._bond_release_payout(session, chain_id, sender_addr, release_amount, tx_hash)
        if payout_error is not None:
            return payout_error
        bond.amount = 0
        bond.released_tx_hash = tx_hash
        bond.status = "released"
        bond.updated_at = now
        logger.info("Bond released: %s amount=%s", bond_id, release_amount)
        return None

    def _bond_release_lock_error(self, bond: Bond, now: datetime, bond_id: str, block_version: int | None) -> str | None:
        if bond.locked_until:
            locked_until = bond.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if now < locked_until:
                return f"lock period for {bond_id} has not expired"
        elif block_version is not None and block_version >= 22:
            # v22: NULL expiry fails closed; pre-v22 NULL rows stayed
            # immediately releasable for replay compatibility.
            return "no lock expiry recorded"
        return None

    def _bond_slash_effect(
        self,
        session: Session,
        chain_id: str,
        payload: dict[str, Any],
        tx_hash: str,
        sender_addr: str,
        recipient_addr: str,
        value: int,
        provider: str,
        bond_id: str,
        now: datetime,
        block_height: int | None,
        block_version: int | None,
    ) -> str | None:
        slash_authority = _bond_slash_authority(session, chain_id, block_height)
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
        move_error = self._bond_slash_move(session, chain_id, slash_amount, tx_hash)
        if move_error is not None:
            return move_error
        bond.amount -= slash_amount
        bond.slashed_tx_hash = tx_hash
        bond.status = "slashed" if bond.amount <= 0 else "active"
        bond.updated_at = now
        logger.info("Bond slashed: %s amount=%s remaining=%s", bond_id, slash_amount, bond.amount)
        return None

    def _handle_validator_deactivation(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        sender_addr: str,
        value: int,
        block_height: int | None = None,
        block_time: datetime | None = None,
    ) -> str | None:
        """Apply a ``VALIDATOR_DEACTIVATE`` marker (#1198, spec v2).

        Activation-only: moves no funds (``BOND_SLASH`` keeps the economic
        penalty). Gates, all pure functions of chain state so replay and
        reorg are identical on every node:

        - sender must be the ``validator_deactivation_authority`` (dedicated
          param — not ``bond_slash_authority``);
        - ``payload.validator_address`` must be strict ``0x``+40hex
          (``canonical_address(strict=True)``);
        - ``payload.bond_id`` must name an ``active`` bond whose provider
          canonicalizes to the validator — bond-less validators cannot be
          deactivated on-chain (Q2 ruling; env removal remains their recourse);
        - ``payload.evidence_hash`` is required audit data (v1 does not verify
          it on-chain);
        - ``value`` must be 0 (also enforced at validate via the zero-value set).

        Returns None when the marker was written, or a skip reason — the
        caller still applies fee/nonce, matching the bond handlers' contract.
        """
        authority = _validator_deactivation_authority(session, chain_id, block_height)
        if not authority:
            return (
                "no validator-deactivation authority configured (chain parameter or VALIDATOR_DEACTIVATION_AUTHORITY_ADDRESS)"
            )
        if sender_addr != authority:
            return "not signed by the configured validator-deactivation authority"
        if value != 0:
            return "must have value=0"
        parsed = _parse_validator_deactivation_payload(tx_data.get("payload", {}) or {})
        if isinstance(parsed, str):
            return parsed
        validator_addr, evidence_hash, bond_id = parsed
        bond = session.exec(
            select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
        ).first()
        if bond is None:
            return f"unknown or inactive bond {bond_id}"
        if canonical_address(bond.provider) != validator_addr:
            return "bond provider does not match validator_address"
        # #1263: when the evidence gate is armed at this height, the payload
        # must carry a verifiable evidence bundle — audit-only v1 markers are
        # rejected. Disarmed resolves byte-identical legacy behavior.
        from .deactivation_evidence import _evidence_required, verify_deactivation_evidence

        if _evidence_required(session, chain_id, block_height):
            reason = verify_deactivation_evidence(
                tx_data.get("payload", {}) or {},
                chain_id=chain_id,
                validator_addr=validator_addr,
                evidence_hash=evidence_hash,
                session=session,
                block_height=block_height,
                block_time=block_time,
            )
            if reason is not None:
                return reason
        existing = session.exec(
            select(ValidatorDeactivation).where(
                ValidatorDeactivation.chain_id == chain_id,
                ValidatorDeactivation.validator_address == validator_addr,
            )
        ).first()
        if existing is not None:
            return "validator already deactivated"
        session.add(
            ValidatorDeactivation(
                chain_id=chain_id,
                validator_address=validator_addr,
                evidence_hash=evidence_hash,
                deactivation_tx_hash=tx_hash,
                block_height=block_height,
            )
        )
        logger.info(
            "Validator deactivated on-chain: %s (bond=%s evidence=%s tx=%s height=%s)",
            validator_addr,
            bond_id,
            evidence_hash[:18],
            tx_hash[:18],
            block_height,
        )
        return None

    def handle_gpu_registration(
        self,
        session: Session,
        chain_id: str,
        gpu_data: dict[str, Any],
        block_version: int = 1,
    ) -> tuple[bool, str]:
        """
        Handle GPU registration state transition.

        Args:
            session: Database session
            chain_id: Chain identifier
            gpu_data: GPU registration data
            block_version: State-transition rule version of the containing
                block. v25+ bounds ``price_per_hour`` to a finite Decimal in
                [0, Numeric(20,8) max] (#1566); callers that omit it get the
                pre-gate rules so historical replay is unchanged.

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
                existing.model = str(gpu_data.get("model", existing.model))
                existing.memory_gb = int(gpu_data.get("memory_gb", existing.memory_gb))
                existing.cuda_version = str(gpu_data.get("cuda_version", existing.cuda_version))
                existing.region = str(gpu_data.get("region", existing.region))
                existing.capabilities = list(gpu_data.get("capabilities", existing.capabilities) or [])
                raw_price = gpu_data.get("price_per_hour", existing.price_per_hour)
                try:
                    new_price = Decimal(str(raw_price))
                except Exception:
                    return (False, f"Invalid price_per_hour for GPU {gpu_id}")
                if block_version >= 25 and not _gpu_price_per_hour_in_range(new_price):
                    return (False, f"price_per_hour out of range for GPU {gpu_id}")
                existing.price_per_hour = new_price
                existing.status = "active"
                existing.updated_at = datetime.now(UTC)
            else:
                price = gpu_data.get(
                    "price_per_hour", 0.0
                )  # not-money: apply-time, consensus-frozen — the float default is part of the replayed payload semantics; converting to Decimal("0") would change what missing price_per_hour yields on replay. Needs a version-height gate + own megaplan (#1033).
                try:
                    price = Decimal(str(price))
                except Exception:
                    return (False, f"Invalid price_per_hour for GPU {gpu_id}")
                if block_version >= 25 and not _gpu_price_per_hour_in_range(price):
                    return (False, f"price_per_hour out of range for GPU {gpu_id}")
                try:
                    memory_gb = int(gpu_data.get("memory_gb", 0))
                except Exception:
                    return (False, f"Invalid memory_gb for GPU {gpu_id}")
                registration = GPURegistration(
                    chain_id=chain_id,
                    gpu_id=gpu_id,
                    miner_id=str(gpu_data.get("miner_id", "")),
                    model=str(gpu_data.get("model", "")),
                    memory_gb=memory_gb,
                    cuda_version=str(gpu_data.get("cuda_version", "")),
                    region=str(gpu_data.get("region", "")),
                    capabilities=list(gpu_data.get("capabilities", []) or []),
                    price_per_hour=price,
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

    def handle_gpu_deregistration(self, session: Session, chain_id: str, gpu_data: dict[str, Any]) -> tuple[bool, str]:
        """Handle the v10 GPU_DEREGISTER state transition: mark the row ``deactivated``, keep it.

        Ownership and existence are checked by ``validate_transaction`` (``gpu_deregister_error``); this only
        writes. Allocations are left untouched: nothing completes them, so they cannot be a precondition.
        """
        try:
            gpu_id = gpu_data.get("gpu_id")
            if not gpu_id:
                return (False, "GPU ID is required")
            existing = session.exec(
                select(GPURegistration).where(GPURegistration.chain_id == chain_id, GPURegistration.gpu_id == str(gpu_id))
            ).first()
            if existing is None:
                return (False, f"GPU not found: {gpu_id}")
            existing.status = GPU_STATUS_DEACTIVATED
            existing.updated_at = datetime.now(UTC)
            logger.info("GPU deregistration handled: %s", gpu_id)
            return (True, "GPU deregistration successful")
        except Exception as e:  # noqa: BLE001 - handler boundary: any failure becomes a (False, reason) verdict
            logger.error("GPU deregistration error: %s", e)
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
            try:
                duration_hours = float(
                    allocation_data.get("duration_hours", 0.0)
                )  # not-money: apply-time, consensus-frozen — same replay-boundary as the price default above; conversion is a version-height change (#1033).
                total_cost = Decimal(
                    str(allocation_data.get("total_cost", 0.0))
                )  # not-money: apply-time, consensus-frozen — Decimal(str(0.0)) yields "0.0" while Decimal("0") yields "0"; changing the default can diverge the stored state hash on replay. Version-height gate required (#1033).
            except Exception:
                return (False, f"Invalid duration_hours or total_cost for GPU {gpu_id}")
            allocation = GPUAllocation(
                chain_id=chain_id,
                allocation_id=allocation_id,
                gpu_id=gpu_id,
                client_id=allocation_data.get("client_id", ""),
                duration_hours=duration_hours,
                total_cost=total_cost,
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
