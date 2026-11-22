"""Operator-key auth for the agent-stake / bounty RPC surface (V23-42)."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import HTTPException
from eth_utils import keccak

from aitbc.crypto.signature_recovery import canonical_address

from ..base_models import _to_ait_address
from .utils import verify_request_signature

_OPERATOR_ENV = "AGENT_ECONOMICS_OPERATOR_ADDRESS"


def operator_address() -> str:
    raw = os.getenv(_OPERATOR_ENV, "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="agent-economics operator is not configured")
    return _to_ait_address(raw)


def signed_body(body: dict[str, Any]) -> dict[str, Any]:
    """Return the dict that must be signed: everything except ``signature``."""
    return {k: v for k, v in body.items() if k != "signature"}


def require_operator_signature(body: dict[str, Any]) -> dict[str, Any]:
    """Verify the operator signature and return the unsigned payload."""
    signature = body.get("signature")
    if not signature or not isinstance(signature, str):
        raise HTTPException(status_code=403, detail="Operator signature required")
    payload = signed_body(body)
    if not verify_request_signature(operator_address(), signature, payload):
        raise HTTPException(status_code=403, detail="Invalid operator signature")
    return payload


def require_user(payload: dict[str, Any], expected: str, field: str = "user_address") -> str:
    """Require ``payload[field]`` to name the same account as *expected*."""
    got = payload.get(field)
    if not got or not isinstance(got, str):
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if _to_ait_address(got) != _to_ait_address(expected):
        raise HTTPException(status_code=403, detail=f"{field} does not match the locked account")
    return _to_ait_address(got)


def require_int(payload: dict[str, Any], field: str, *, minimum: int = 1) -> int:
    raw = payload.get(field)
    if raw is None:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc
    if value < minimum:
        raise HTTPException(status_code=400, detail=f"{field} must be >= {minimum}")
    return value


def canonical_sign_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def payload_hash(payload: dict[str, Any]) -> bytes:
    return keccak(canonical_sign_payload(payload))


def require_signed_transfer_values(payload: dict[str, Any], *, to: str, amount: int) -> None:
    """Optional strict payee/amount binding for resolved-value transfers (#2472).

    ``BOUNTY_PAYOUT``/``BOUNTY_REFUND``/agent ``STAKE_RELEASE`` resolve the
    payee and amount server-side, so a signed body that omits them leaves
    ``payload.auth`` unable to bind those legs — the envelope then stays
    local-queue only (gossip drops it, #2457/#2472). When the caller signs
    ``to``/``amount`` — values it can learn from a ``resolve_only`` probe —
    the operator signature covers them and the transfer becomes
    gossip-admissible. Both fields must appear together and equal the
    server-resolved values; with neither present the legacy path proceeds
    unchanged.
    """
    has_to = "to" in payload
    has_amount = "amount" in payload
    if not has_to and not has_amount:
        return
    if not has_to or not has_amount:
        raise HTTPException(status_code=400, detail="signed 'to' and 'amount' must be provided together")
    try:
        signed_to = _to_ait_address(str(payload["to"]))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="signed 'to' must be a valid address") from None
    if signed_to != _to_ait_address(str(to)):
        raise HTTPException(status_code=400, detail="signed 'to' does not match the resolved payee")
    try:
        signed_amount = int(payload["amount"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="signed 'amount' must be an integer") from None
    resolved = int(amount)
    if signed_amount != resolved:
        raise HTTPException(
            status_code=400, detail=f"signed 'amount' {signed_amount} does not match resolved amount {resolved}"
        )


# keep unused import used by address equality
_ = canonical_address
