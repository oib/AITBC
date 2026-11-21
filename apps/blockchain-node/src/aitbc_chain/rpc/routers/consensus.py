"""
Consensus router.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/consensus", tags=["consensus"])


@router.get("/status", summary="Get consensus status")
@rate_limit(rate=100, per=60)
def consensus_status_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    """Get consensus mode, view, sequence, epoch, and fault tolerance.

    ``current_view``, ``current_sequence`` and ``current_epoch`` are only
    meaningful when PBFT is enabled.

    ``fault_tolerance`` and ``required_messages`` are standard BFT values
    derived from the active validator count (``f = floor((n-1)/3)`` and
    ``2f + 1``). ``multi_validator_min_attestations`` is the live
    crash-tolerance threshold: a block is accepted when it carries at least
    that many attestations.
    """
    chain_id = chain_id or settings.chain_id
    if not settings.multi_validator_consensus_enabled or not settings.validator_set:
        return {
            "mode": "PoA (single proposer)",
            "multi_validator_enabled": False,
            "chain_id": chain_id,
        }
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        consensus.load_state(slashing=False)
        participants = consensus.get_consensus_participants()
        if not participants and consensus.quorum_health()["configured"] > 0:
            # #2158: validators are configured but none is active — that is a
            # halt, not a single-proposer deployment.
            health = consensus.quorum_health()
            return {
                "mode": "MultiValidatorPoA (HALTED: no active validators)",
                "multi_validator_enabled": True,
                "halted": True,
                "chain_id": chain_id,
                "active_validators": 0,
                "configured_validators": health["configured"],
                "required_messages": health["required"],
                "below_quorum": True,
            }
        if not participants:
            return {
                "mode": "PoA (single proposer)",
                "multi_validator_enabled": False,
                "chain_id": chain_id,
            }

        # Standard BFT quorum values from the active validator count — same
        # formula the PBFT engine uses (#1061, one function).
        from ...consensus.pbft import pbft_required_messages

        n = len(participants)
        fault_tolerance = (n - 1) // 3
        required_messages = pbft_required_messages(n)

        # Crash-tolerance threshold actually used by the multi-validator engine.
        min_attestations = getattr(settings, "multi_validator_min_attestations", 0)

        pbft_enabled = getattr(settings, "pbft_consensus_enabled", False)
        mode = "MultiValidatorPoA + PBFT" if pbft_enabled else "MultiValidatorPoA"
        result: dict[str, Any] = {
            "mode": mode,
            "multi_validator_enabled": True,
            "chain_id": chain_id,
            "fault_tolerance": fault_tolerance,
            "required_messages": required_messages,
            "min_attestations": min_attestations,
            "active_validators": n,
            "total_validators": len(consensus.validators),
            "below_quorum": consensus.quorum_health()["below_quorum"],
        }
        if pbft_enabled:
            # #2409: the persisted ``_pbft_view``/``_pbft_sequence`` snapshots
            # are never advanced (dead since f3069a3a7) — reporting them as 0
            # fabricated a halted-looking consensus on a live chain. Derive
            # the truthful values instead: PBFT sequence IS the sealed height
            # (``sync_to_head``), and the current view is the proposer round
            # elapsed since the head block's timestamp.
            from datetime import UTC, datetime

            from sqlmodel import col, desc, select

            from ...base_models import Block
            from ...consensus.multi_validator_poa import proposer_round
            from ...database import session_scope

            with session_scope(chain_id) as session:
                head = session.exec(
                    select(Block.height, Block.timestamp)
                    .where(Block.chain_id == chain_id)
                    .order_by(desc(col(Block.height)))
                    .limit(1)
                ).first()
            if head is not None:
                head_height, head_ts = head
                result["current_sequence"] = int(head_height)
                round_seconds = int(getattr(settings, "consensus_proposer_round_seconds", 120))
                result["current_view"] = proposer_round(head_ts, datetime.now(UTC), round_seconds)
            result["current_epoch"] = consensus._current_epoch
        return result
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
def consensus_validators_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    """List active validators (address, stake, reputation, role, last_proposed)."""
    chain_id = chain_id or settings.chain_id
    if not settings.multi_validator_consensus_enabled or not settings.validator_set:
        return {"validators": [], "chain_id": chain_id, "multi_validator_enabled": False}
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        consensus.load_state(slashing=False)
        if not consensus.validators:
            return {"validators": [], "chain_id": chain_id, "multi_validator_enabled": False}
        # #2409: ``ValidatorState.last_proposed`` is never written (dead
        # since f3069a3a7) — every row read 0 while blocks had real
        # proposers. Derive it from the sealed chain instead: the highest
        # block height each validator actually proposed.
        from sqlmodel import col, func, select

        from ...base_models import Block
        from ...database import session_scope

        last_proposed: dict[str, int] = {}
        try:
            with session_scope(chain_id) as session:
                rows = session.exec(
                    select(Block.proposer, func.max(col(Block.height)))
                    .where(Block.chain_id == chain_id)
                    .group_by(Block.proposer)
                ).all()
            last_proposed = {addr: int(h) for addr, h in rows if addr}
        except Exception as e:  # noqa: BLE001 - degrade to the stored field, never 500 the list
            _logger.warning("last_proposed derivation failed for %s: %s", chain_id, e)
        validators = [
            {
                "address": addr,
                "stake": str(v.stake),
                "reputation": v.reputation,
                "role": v.role.value,
                "is_active": v.is_active,
                "last_proposed": last_proposed.get(addr, v.last_proposed),
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
def consensus_slashing_history_route(
    request: Request,  # noqa: ARG001
    chain_id: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, Any]:
    """Get slashing events (validator, condition, amount, block height)."""
    chain_id = chain_id or settings.chain_id
    if not settings.multi_validator_consensus_enabled or not settings.validator_set:
        return {"slashing_events": [], "chain_id": chain_id, "multi_validator_enabled": False}
    try:
        from ...consensus.multi_validator_poa import get_consensus

        consensus = get_consensus(chain_id)
        consensus.load_state()
        if not consensus.validators:
            return {"slashing_events": [], "chain_id": chain_id, "multi_validator_enabled": False}
        all_events = consensus.get_slashing_history()
        events = all_events[-limit:]  # #2118: newest `limit`, oldest first
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
        return {
            "slashing_events": slashing_events,
            "total": len(all_events),
            "truncated": len(all_events) > len(events),
            "pruned_count": sum(
                int(v.get("count", 0))
                for v in getattr(getattr(consensus, "_slashing_manager", None), "pruned_summary", {}).values()
            ),
            "chain_id": chain_id,
            "multi_validator_enabled": True,
        }
    except RuntimeError:
        return {"slashing_events": [], "chain_id": chain_id, "multi_validator_enabled": False}
    except Exception as e:
        _logger.error("Error getting slashing history: %s", e)
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
