"""
Consensus router.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/consensus", tags=["consensus"])


@router.get("/status", summary="Get consensus status")
@rate_limit(rate=100, per=60)
async def consensus_status_route(chain_id: str = "ait-hub") -> dict[str, Any]:
    """Get consensus mode, view, sequence, epoch, and fault tolerance."""
    if not settings.multi_validator_consensus_enabled:
        return {
            "mode": "PoA (single proposer)",
            "multi_validator_enabled": False,
            "chain_id": chain_id,
        }
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        participants = consensus.get_consensus_participants()
        fault_tolerance = max(1, len(participants) // 3)
        return {
            "mode": "MultiValidatorPoA + PBFT",
            "multi_validator_enabled": True,
            "chain_id": chain_id,
            "current_view": consensus._pbft_view,
            "current_sequence": consensus._pbft_sequence,
            "current_epoch": consensus._current_epoch,
            "fault_tolerance": fault_tolerance,
            "required_messages": 2 * fault_tolerance + 1,
            "active_validators": len(participants),
            "total_validators": len(consensus.validators),
        }
    except RuntimeError:
        return {
            "mode": "PoA (single proposer)",
            "multi_validator_enabled": False,
            "chain_id": chain_id,
        }
    except Exception as e:
        _logger.error("Error getting consensus status: %s", e)
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/validators", summary="List consensus validators")
@rate_limit(rate=100, per=60)
async def consensus_validators_route(chain_id: str = "ait-hub") -> dict[str, Any]:
    """List active validators (address, stake, reputation, role, last_proposed)."""
    if not settings.multi_validator_consensus_enabled:
        return {"validators": [], "chain_id": chain_id, "multi_validator_enabled": False}
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        validators = [
            {
                "address": addr,
                "stake": str(v.stake),
                "reputation": v.reputation,
                "role": v.role.value,
                "is_active": v.is_active,
                "last_proposed": v.last_proposed,
            }
            for addr, v in consensus.validators.items()
        ]
        return {"validators": validators, "chain_id": chain_id, "multi_validator_enabled": True}
    except RuntimeError:
        return {"validators": [], "chain_id": chain_id, "multi_validator_enabled": False}
    except Exception as e:
        _logger.error("Error listing consensus validators: %s", e)
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/slashing-history", summary="Get slashing history")
@rate_limit(rate=100, per=60)
async def consensus_slashing_history_route(chain_id: str = "ait-hub") -> dict[str, Any]:
    """Get slashing events (validator, condition, amount, block height)."""
    if not settings.multi_validator_consensus_enabled:
        return {"slashing_events": [], "chain_id": chain_id, "multi_validator_enabled": False}
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        events = consensus.get_slashing_history()
        slashing_events = [
            {
                "validator_address": e.validator_address,
                "condition": e.condition.value,
                "evidence": e.evidence,
                "block_height": e.block_height,
                "timestamp": e.timestamp,
                # V23-48: `slash_amount` carried the *rate* under a name that reads as a
                # quantity -- the CLI displayed it in a column headed "Amount". The rate and
                # the amount are separate fields now, and the amount is null until the
                # penalty is actually levied. Money as a decimal string: FastAPI's
                # jsonable_encoder turns a bare Decimal back into a float.
                "slash_rate": e.slash_rate,
                "stake_before": None if e.stake_before is None else str(e.stake_before),
                "slashed_amount": None if e.slashed_amount is None else str(e.slashed_amount),
            }
            for e in events
        ]
        return {"slashing_events": slashing_events, "chain_id": chain_id, "multi_validator_enabled": True}
    except RuntimeError:
        return {"slashing_events": [], "chain_id": chain_id, "multi_validator_enabled": False}
    except Exception as e:
        _logger.error("Error getting slashing history: %s", e)
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
