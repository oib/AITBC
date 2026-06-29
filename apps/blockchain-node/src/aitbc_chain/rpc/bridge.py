"""
Bridge-related RPC endpoints.
"""

from typing import Any, cast

from fastapi import HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ..config import settings
from ..logger import get_logger
from .utils import get_chain_id, verify_request_signature

_logger = get_logger(__name__)


@rate_limit(rate=20, per=60)
async def bridge_lock(request: Request, lock_data: dict[str, Any]) -> dict[str, Any]:
    """
    Initiate a cross-chain bridge transfer by locking funds.

    This is step 1 of the atomic bridge:
    1. Lock funds on source chain (this endpoint)
    2. Generate proof
    3. Confirm on target chain
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        source_chain = lock_data.get("source_chain", get_chain_id(None))
        target_chain = lock_data.get("target_chain")
        sender = lock_data.get("sender")
        recipient = lock_data.get("recipient")
        amount = lock_data.get("amount", 0)
        asset = lock_data.get("asset", "native")
        if not all([target_chain, sender, recipient]):
            raise HTTPException(status_code=400, detail="Missing required fields: target_chain, sender, recipient")
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        # Bug 7: Verify sender signature before locking funds
        signature = lock_data.get("signature")
        if not signature:
            raise HTTPException(status_code=403, detail="Signature required for bridge lock")
        sign_data = {
            "source_chain": source_chain,
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
        }
        if not verify_request_signature(cast(str, sender), signature, sign_data):
            raise HTTPException(status_code=403, detail="Invalid sender signature")

        transfer = bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=cast(str, target_chain),
            sender=cast(str, sender).lower(),
            recipient=cast(str, recipient).lower(),
            amount=amount,
            asset=asset,
        )
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": source_chain,
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "fee": amount * 10 // 10000,
            "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
            "message": "Funds locked successfully. Use /bridge/confirm to complete.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge lock failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge lock failed: {str(e)}") from e


@rate_limit(rate=20, per=60)
async def bridge_confirm(request: Request, confirm_data: dict[str, Any]) -> dict[str, Any]:
    """
    Confirm a cross-chain bridge transfer and release funds.

    This is step 2 of the atomic bridge:
    1. Validate proof of lock
    2. Release funds on target chain
    3. Mark transfer as complete

    Bug 3 PARTIAL (v0.5.16): the release path is fenced behind
    ``BRIDGE_RELEASE_ENABLED`` (default false) because proof verification
    currently accepts any valid secp256k1 signer — full proposer-set + Merkle
    proof verification lands in v0.7.2. Do not enable on production networks.
    """
    if not getattr(settings, "bridge_release_enabled", False):
        raise HTTPException(
            status_code=503,
            detail="Bridge release path disabled (BRIDGE_RELEASE_ENABLED=false). "
            "Proof verification is PARTIAL pending v0.7.2 — enable only on isolated test nets.",
        )
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        transfer_id = confirm_data.get("transfer_id")
        proof = confirm_data.get("proof")
        if not transfer_id or not proof:
            raise HTTPException(status_code=400, detail="Missing required fields: transfer_id, proof")

        # Bug 7: Verify confirmer signature
        confirmer = confirm_data.get("confirmer") or confirm_data.get("recipient")
        signature = confirm_data.get("signature")
        if not confirmer or not signature:
            raise HTTPException(status_code=403, detail="Confirmer address and signature required")
        sign_data = {"transfer_id": transfer_id, "confirmer": confirmer}
        if not verify_request_signature(confirmer, signature, sign_data):
            raise HTTPException(status_code=403, detail="Invalid confirmer signature")

        transfer = bridge.confirm_transfer(transfer_id, proof)
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": transfer.source_chain,
            "target_chain": transfer.target_chain,
            "sender": transfer.sender,
            "recipient": transfer.recipient,
            "amount": transfer.amount,
            "target_tx_hash": transfer.target_tx_hash,
            "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None,
            "message": "Cross-chain transfer completed successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge confirm failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge confirm failed: {str(e)}") from e


@rate_limit(rate=100, per=60)
async def get_bridge_transfer(request: Request, transfer_id: str) -> dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        transfer = bridge.get_transfer(transfer_id)
        if not transfer:
            raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found")
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": transfer.source_chain,
            "target_chain": transfer.target_chain,
            "sender": transfer.sender,
            "recipient": transfer.recipient,
            "amount": transfer.amount,
            "asset": transfer.asset,
            "source_tx_hash": transfer.source_tx_hash,
            "target_tx_hash": transfer.target_tx_hash,
            "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
            "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Get bridge transfer failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get transfer: {str(e)}") from e


@rate_limit(rate=50, per=60)
async def list_pending_transfers(request: Request, chain_id: str | None = None) -> list[dict[str, Any]]:
    """List all pending cross-chain transfers"""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        chain_id = get_chain_id(chain_id)
        transfers = bridge.list_pending_transfers(chain_id)
        return [
            {
                "transfer_id": t.transfer_id,
                "source_chain": t.source_chain,
                "target_chain": t.target_chain,
                "sender": t.sender,
                "recipient": t.recipient,
                "amount": t.amount,
                "status": t.status.value,
                "lock_time": t.lock_time.isoformat() if t.lock_time else None,
            }
            for t in transfers
        ]
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("List pending transfers failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to list transfers: {str(e)}") from e


@rate_limit(rate=20, per=60)
async def bridge_unlock(request: Request, unlock_data: dict[str, Any]) -> dict[str, Any]:
    """Refund/cancel a pending bridge transfer — return locked funds to sender.

    v0.7.0 §B2: Only transfers in 'pending' or 'locked' status can be refunded.
    The sender must sign the unlock request to authorize the refund.
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        transfer_id = unlock_data.get("transfer_id")
        sender = unlock_data.get("sender")
        if not transfer_id or not sender:
            raise HTTPException(status_code=400, detail="Missing required fields: transfer_id, sender")

        # Verify sender signature
        signature = unlock_data.get("signature")
        if not signature:
            raise HTTPException(status_code=403, detail="Signature required for bridge unlock")
        sign_data = {"transfer_id": transfer_id, "sender": sender, "action": "unlock"}
        if not verify_request_signature(cast(str, sender), signature, sign_data):
            raise HTTPException(status_code=403, detail="Invalid sender signature")

        transfer = bridge.refund_transfer(transfer_id, cast(str, sender).lower())
        return {
            "success": True,
            "transfer_id": transfer.transfer_id,
            "status": transfer.status.value,
            "source_chain": transfer.source_chain,
            "sender": transfer.sender,
            "amount": transfer.amount,
            "message": "Bridge transfer refunded successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge unlock failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge unlock failed: {str(e)}") from e


@rate_limit(rate=100, per=60)
async def get_bridge_balance(request: Request, chain_id: str) -> dict[str, Any]:
    """Get the total locked balance for a chain (sum of pending/locked transfers)."""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        balances = bridge.get_bridge_balance(chain_id)
        return {
            "success": True,
            "chain_id": chain_id,
            "locked_amount": balances.get(chain_id, 0),
            "balances": balances,
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Get bridge balance failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get bridge balance: {str(e)}") from e


@rate_limit(rate=100, per=60)
async def bridge_health(request: Request) -> dict[str, Any]:
    """Get bridge health status — active transfers, pending count, configuration."""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        pending = bridge.list_pending_transfers()
        balances = bridge.get_bridge_balance()
        total_locked = sum(balances.values())
        return {
            "success": True,
            "status": "healthy",
            "bridge_initialized": True,
            "pending_transfer_count": len(pending),
            "total_locked_amount": total_locked,
            "balances_per_chain": balances,
            "release_enabled": getattr(settings, "bridge_release_enabled", False),
            "bridge_timeout": getattr(settings, "bridge_timeout", 300),
            "bridge_batch_size": getattr(settings, "bridge_batch_size", 10),
            "bridge_monitor_interval": getattr(settings, "bridge_monitor_interval", 60),
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge health check failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge health check failed: {str(e)}") from e


@rate_limit(rate=20, per=60)
async def bridge_batch_lock(request: Request, batch_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch lock multiple cross-chain transfers."""
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        transfers = batch_data.get("transfers", [])
        if not transfers:
            raise HTTPException(status_code=400, detail="Missing or empty 'transfers' list")
        max_batch = getattr(settings, "bridge_batch_size", 10)
        if len(transfers) > max_batch:
            raise HTTPException(status_code=400, detail=f"Batch size {len(transfers)} exceeds maximum {max_batch}")

        results = bridge.batch_lock(transfers)
        return [
            {
                "success": t.status.value != "failed",
                "transfer_id": t.transfer_id,
                "status": t.status.value,
                "source_chain": t.source_chain,
                "target_chain": t.target_chain,
                "sender": t.sender,
                "recipient": t.recipient,
                "amount": t.amount,
                "error": t.proof.get("error") if t.proof and isinstance(t.proof, dict) else None,
            }
            for t in results
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge batch lock failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge batch lock failed: {str(e)}") from e


@rate_limit(rate=20, per=60)
async def bridge_batch_confirm(request: Request, batch_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch confirm multiple cross-chain transfers.

    Gated by ``BRIDGE_RELEASE_ENABLED`` same as single confirm.
    """
    if not getattr(settings, "bridge_release_enabled", False):
        raise HTTPException(
            status_code=503,
            detail="Bridge release path disabled (BRIDGE_RELEASE_ENABLED=false). "
            "Proof verification is PARTIAL pending v0.7.2 — enable only on isolated test nets.",
        )
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        confirmations = batch_data.get("confirmations", [])
        if not confirmations:
            raise HTTPException(status_code=400, detail="Missing or empty 'confirmations' list")
        max_batch = getattr(settings, "bridge_batch_size", 10)
        if len(confirmations) > max_batch:
            raise HTTPException(status_code=400, detail=f"Batch size {len(confirmations)} exceeds maximum {max_batch}")

        results = bridge.batch_confirm(confirmations)
        output: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict):
                output.append({"success": False, **r})
            else:
                output.append(
                    {
                        "success": True,
                        "transfer_id": r.transfer_id,
                        "status": r.status.value,
                        "target_tx_hash": r.target_tx_hash,
                        "confirm_time": r.confirm_time.isoformat() if r.confirm_time else None,
                    }
                )
        return output
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge batch confirm failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge batch confirm failed: {str(e)}") from e


# ---------------------------------------------------------------------------
# v0.7.1: Validator set management + security status endpoints
# ---------------------------------------------------------------------------


@rate_limit(rate=20, per=60)
async def register_validator(request: Request, reg_data: dict[str, Any]) -> dict[str, Any]:
    """Register a bridge validator for a chain (v0.7.1 §B5).

    The registration must be signed by the validator's private key to prove
    ownership of the address being registered. The signature covers the
    canonical JSON of {chain_id, address, public_key, action: "register"}.
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
        chain_id = reg_data.get("chain_id")
        address = reg_data.get("address")
        public_key = reg_data.get("public_key")
        signature = reg_data.get("signature")
        epoch = reg_data.get("epoch", 0)

        if not all([chain_id, address, public_key, signature]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: chain_id, address, public_key, signature",
            )

        # Verify the signature proves ownership of the address
        sign_data = {"chain_id": chain_id, "address": address, "public_key": public_key, "action": "register"}
        if not verify_request_signature(cast(str, address), signature, sign_data):
            raise HTTPException(status_code=403, detail="Invalid validator signature")

        bridge.register_validator(
            chain_id=cast(str, chain_id),
            address=cast(str, address).lower(),
            public_key=cast(str, public_key),
            epoch=int(epoch),
        )
        return {
            "success": True,
            "status": "registered",
            "chain_id": chain_id,
            "address": address,
            "epoch": int(epoch),
            "message": "Validator registered successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Validator registration failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Validator registration failed: {str(e)}") from e


@rate_limit(rate=100, per=60)
async def get_validator_set(request: Request, chain_id: str) -> dict[str, Any]:
    """Get the validator set for a chain (v0.7.1 §B5).

    Optional query param ``epoch`` selects a specific epoch (defaults to current).
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")

        # Parse epoch from query params if provided
        epoch_str = request.query_params.get("epoch")
        epoch = int(epoch_str) if epoch_str else None

        vset = bridge.get_validator_set(chain_id, epoch)
        if vset is None:
            return {
                "success": True,
                "chain_id": chain_id,
                "epoch": 0,
                "threshold": getattr(settings, "bridge_multisig_threshold", 3),
                "total": 0,
                "validators": [],
                "message": "No validators registered for this chain",
            }
        return {
            "success": True,
            "chain_id": chain_id,
            "epoch": vset.epoch,
            "threshold": vset.threshold,
            "total": vset.total,
            "validators": [
                {
                    "address": v.address,
                    "public_key": v.public_key,
                    "is_active": v.is_active,
                    "registered_at": v.registered_at.isoformat() if v.registered_at else None,
                }
                for v in vset.validators
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Get validator set failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get validator set: {str(e)}") from e


@rate_limit(rate=100, per=60)
async def bridge_security_status(request: Request) -> dict[str, Any]:
    """Get bridge security status (v0.7.1 §B5).

    Returns the multi-sig configuration, validator count, current epoch,
    block signature requirement, and release fence status.
    """
    try:
        from ..cross_chain.bridge import get_cross_chain_bridge

        bridge = get_cross_chain_bridge()
        bridge_initialized = bridge is not None

        # Count validators across all chains
        validator_count = 0
        current_epoch = 0
        if bridge_initialized:
            from sqlmodel import select as _select

            from ..models import BridgeValidator

            with bridge._session_factory() as session:  # type: ignore[union-attr]
                validator_count = len(session.exec(_select(BridgeValidator).where(BridgeValidator.is_active)).all())
                # Get max epoch
                epochs = session.exec(_select(BridgeValidator.epoch)).all()
                current_epoch = max(epochs) if epochs else 0

        return {
            "success": True,
            "multisig_enabled": getattr(settings, "bridge_multisig_enabled", False),
            "threshold": getattr(settings, "bridge_multisig_threshold", 3),
            "validators_configured": getattr(settings, "bridge_multisig_validators", 5),
            "validator_count": validator_count,
            "current_epoch": current_epoch,
            "block_signature_required": getattr(settings, "bridge_block_signature_required", True),
            "release_enabled": getattr(settings, "bridge_release_enabled", False),
            "bridge_initialized": bridge_initialized,
            "validator_set_grace_period": getattr(settings, "bridge_validator_set_grace_period", 7200),
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Bridge security status failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bridge security status failed: {str(e)}") from e
