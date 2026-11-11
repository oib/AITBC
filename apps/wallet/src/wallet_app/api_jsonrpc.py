from __future__ import annotations

import base64
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from .deps import get_keystore, get_ledger, get_receipt_service, require_admin_api_key
from .keystore.persistent_service import PersistentKeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .models import (
    _MAX_METADATA_BYTES,
    _MAX_MESSAGE_B64_LEN,
    _MAX_PASSWORD_LEN,
    _MAX_SECRET_KEY_B64_LEN,
    from_validation_result,
)
from .receipts.service import ReceiptVerifierService
from .security import wipe_buffer

router = APIRouter(tags=["jsonrpc"])


def _bounded_str(params: dict[str, Any], key: str, max_len: int) -> str | None:
    """Return params[key] when it is a str within max_len, else None."""
    value = params.get(key)
    if not isinstance(value, str) or not value or len(value) > max_len:
        return None
    return value


def _bounded_metadata(params: dict[str, Any]) -> dict[str, Any] | None:
    """params['metadata'] as a dict whose JSON form fits the REST bound."""
    import json

    value = params.get("metadata") or {}
    if not isinstance(value, dict):
        return None
    try:
        if len(json.dumps(value, default=str)) > _MAX_METADATA_BYTES:
            return None
    except (TypeError, ValueError):
        return None
    return value


def _response(
    result: dict[str, Any] | None = None, error: dict[str, Any] | None = None, *, request_id: Any = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


@router.post("/rpc", summary="JSON-RPC endpoint")
def handle_jsonrpc(
    request: dict[str, Any],
    _admin: Annotated[None, Depends(require_admin_api_key)],
    service: Annotated[ReceiptVerifierService, Depends(get_receipt_service)],
    keystore: Annotated[PersistentKeystoreService, Depends(get_keystore)],
    ledger: Annotated[SQLiteLedgerAdapter, Depends(get_ledger)],
) -> dict[str, Any]:
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        # params must be an object; list/scalar params would AttributeError
        # on .get below and surface as a 500 instead of a JSON-RPC error.
        return _response(error={"code": -32602, "message": "params must be an object"}, request_id=request.get("id"))
    request_id = request.get("id")

    if method == "receipts.verify_latest":
        job_id = params.get("job_id")
        if not job_id:
            return _response(error={"code": -32602, "message": "job_id required"}, request_id=request_id)
        result = service.verify_latest(str(job_id))
        if result is None:
            return _response(error={"code": -32004, "message": "receipt not found"}, request_id=request_id)
        model = from_validation_result(result)
        return _response(result=model.model_dump(), request_id=request_id)

    if method == "receipts.verify_history":
        job_id = params.get("job_id")
        if not job_id:
            return _response(error={"code": -32602, "message": "job_id required"}, request_id=request_id)
        results = [from_validation_result(item).model_dump() for item in service.verify_history(str(job_id))]
        return _response(result={"items": results}, request_id=request_id)

    if method == "wallet.list":
        items = []
        for record in keystore.list_records():
            ledger_record = ledger.get_wallet(record.wallet_id)
            metadata = ledger_record.metadata if ledger_record else record.metadata
            items.append({"wallet_id": record.wallet_id, "public_key": record.public_key, "metadata": metadata})
        return _response(result={"items": items}, request_id=request_id)

    if method == "wallet.create":
        wallet_id = params.get("wallet_id")
        password = _bounded_str(params, "password", _MAX_PASSWORD_LEN)
        create_metadata = _bounded_metadata(params)
        secret_b64 = params.get("secret_key")
        if not wallet_id or password is None:
            return _response(error={"code": -32602, "message": "wallet_id and password required"}, request_id=request_id)
        if create_metadata is None:
            return _response(error={"code": -32602, "message": "metadata must be a bounded object"}, request_id=request_id)
        if secret_b64 is not None and (not isinstance(secret_b64, str) or len(secret_b64) > _MAX_SECRET_KEY_B64_LEN):
            return _response(error={"code": -32602, "message": "secret_key too large"}, request_id=request_id)
        try:
            secret = base64.b64decode(secret_b64) if secret_b64 else None
        except Exception:
            return _response(error={"code": -32602, "message": "invalid base64 secret_key"}, request_id=request_id)
        try:
            record = keystore.create_wallet(
                wallet_id=str(wallet_id), password=password, secret=secret, metadata=create_metadata
            )
        except ValueError as e:
            return _response(error={"code": -32602, "message": str(e)}, request_id=request_id)
        ledger.upsert_wallet(record.wallet_id, record.public_key, record.metadata)
        ledger.record_event(record.wallet_id, "created", {"metadata": record.metadata})
        return _response(
            result={
                "wallet": {
                    "wallet_id": record.wallet_id,
                    "public_key": record.public_key,
                    "metadata": record.metadata,
                }
            },
            request_id=request_id,
        )

    if method == "wallet.unlock":
        wallet_id = params.get("wallet_id")
        password = _bounded_str(params, "password", _MAX_PASSWORD_LEN)
        if not wallet_id or password is None:
            return _response(error={"code": -32602, "message": "wallet_id and password required"}, request_id=request_id)
        try:
            unlocked_secret = keystore.unlock_wallet(str(wallet_id), password)
            wipe_buffer(unlocked_secret)
            ledger.record_event(wallet_id, "unlocked", {"success": True})
            return _response(result={"wallet_id": wallet_id, "unlocked": True}, request_id=request_id)
        except (KeyError, ValueError):
            ledger.record_event(wallet_id, "unlocked", {"success": False})
            return _response(error={"code": -32001, "message": "invalid credentials"}, request_id=request_id)

    if method == "wallet.sign":
        wallet_id = params.get("wallet_id")
        password = _bounded_str(params, "password", _MAX_PASSWORD_LEN)
        message_b64 = params.get("message")
        if not wallet_id or password is None or not message_b64:
            return _response(error={"code": -32602, "message": "wallet_id, password, message required"}, request_id=request_id)
        if not isinstance(message_b64, str) or len(message_b64) > _MAX_MESSAGE_B64_LEN:
            return _response(error={"code": -32602, "message": "message too large"}, request_id=request_id)
        try:
            message = base64.b64decode(message_b64)
        except Exception:
            return _response(error={"code": -32602, "message": "invalid base64 message"}, request_id=request_id)

        try:
            signature = keystore.sign_message(str(wallet_id), password, message)
            ledger.record_event(wallet_id, "sign", {"success": True})
        except (KeyError, ValueError):
            ledger.record_event(wallet_id, "sign", {"success": False})
            return _response(error={"code": -32001, "message": "invalid credentials"}, request_id=request_id)

        signature_b64 = base64.b64encode(signature).decode()
        return _response(result={"wallet_id": wallet_id, "signature": signature_b64}, request_id=request_id)

    return _response(error={"code": -32601, "message": "Method not found"}, request_id=request_id)
