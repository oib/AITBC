from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from .deps import get_receipt_service, get_keystore, get_ledger
from .models import ReceiptVerificationModel, from_validation_result
from .keystore.service import KeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .receipts.service import ReceiptVerifierService

router = APIRouter(tags=["jsonrpc"])


def _response(result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None, *, request_id: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


@router.post("/rpc", summary="JSON-RPC endpoint")
def handle_jsonrpc(
    request: Dict[str, Any],
    service: ReceiptVerifierService = Depends(get_receipt_service),
    keystore: KeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> Dict[str, Any]:
    method = request.get("method")
    params = request.get("params") or {}
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
        password = params.get("password")
        metadata = params.get("metadata") or {}
        secret_b64 = params.get("secret_key")
        if not wallet_id or not password:
            return _response(error={"code": -32602, "message": "wallet_id and password required"}, request_id=request_id)
        secret = base64.b64decode(secret_b64) if secret_b64 else None
        record = keystore.create_wallet(wallet_id=wallet_id, password=password, secret=secret, metadata=metadata)
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
        password = params.get("password")
        if not wallet_id or not password:
            return _response(error={"code": -32602, "message": "wallet_id and password required"}, request_id=request_id)
        try:
            keystore.unlock_wallet(wallet_id, password)
            ledger.record_event(wallet_id, "unlocked", {"success": True})
            return _response(result={"wallet_id": wallet_id, "unlocked": True}, request_id=request_id)
        except (KeyError, ValueError):
            ledger.record_event(wallet_id, "unlocked", {"success": False})
            return _response(error={"code": -32001, "message": "invalid credentials"}, request_id=request_id)

    if method == "wallet.sign":
        wallet_id = params.get("wallet_id")
        password = params.get("password")
        message_b64 = params.get("message")
        if not wallet_id or not password or not message_b64:
            return _response(error={"code": -32602, "message": "wallet_id, password, message required"}, request_id=request_id)
        try:
            message = base64.b64decode(message_b64)
        except Exception:
            return _response(error={"code": -32602, "message": "invalid base64 message"}, request_id=request_id)

        try:
            signature = keystore.sign_message(wallet_id, password, message)
            ledger.record_event(wallet_id, "sign", {"success": True})
        except (KeyError, ValueError):
            ledger.record_event(wallet_id, "sign", {"success": False})
            return _response(error={"code": -32001, "message": "invalid credentials"}, request_id=request_id)

        signature_b64 = base64.b64encode(signature).decode()
        return _response(result={"wallet_id": wallet_id, "signature": signature_b64}, request_id=request_id)

    return _response(error={"code": -32601, "message": "Method not found"}, request_id=request_id)
