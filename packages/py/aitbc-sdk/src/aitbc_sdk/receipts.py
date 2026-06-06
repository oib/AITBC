from __future__ import annotations

import base64
import httpx
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, cast

from aitbc_crypto.signing import ReceiptVerifier

from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AITBCHTTPClient


@dataclass
class SignatureValidation:
    key_id: str
    valid: bool
    algorithm: str = "Ed25519"
    reason: str | None = None


@dataclass
class ReceiptVerification:
    receipt: dict[str, Any]
    miner_signature: SignatureValidation
    coordinator_attestations: list[SignatureValidation]

    @property
    def verified(self) -> bool:
        if not self.miner_signature.valid:
            return False
        return all(att.valid for att in self.coordinator_attestations)

    def failure_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.miner_signature.valid:
            key_part = self.miner_signature.key_id or "unknown"
            reasons.append(f"miner_signature_invalid:{key_part}")
        for att in self.coordinator_attestations:
            if not att.valid:
                key_part = att.key_id or "unknown"
                reasons.append(f"coordinator_attestation_invalid:{key_part}")
        return reasons


@dataclass
class ReceiptFailure:
    receipt_id: str
    reasons: list[str]
    verification: ReceiptVerification


@dataclass
class ReceiptStatus:
    job_id: str
    total: int
    verified_count: int
    failed: list[ReceiptVerification] = field(default_factory=list)
    latest_verified: ReceiptVerification | None = None
    failure_reasons: dict[str, int] = field(default_factory=dict)
    failures: list[ReceiptFailure] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        return self.total > 0 and self.verified_count == self.total

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)


class CoordinatorReceiptClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _client(self) -> AITBCHTTPClient:
        return AITBCHTTPClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"X-Api-Key": self.api_key},
        )

    def fetch_latest(self, job_id: str) -> dict[str, Any] | None:
        resp = self._request("GET", f"/v1/jobs/{job_id}/receipt", allow_404=True)
        if resp is None:
            return None
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected receipt payload to be a JSON object")
        return cast(dict[str, Any], payload)

    def fetch_history(self, job_id: str) -> list[dict[str, Any]]:
        return list(self.iter_receipts(job_id=job_id))

    def iter_receipts(self, job_id: str, page_size: int = 100) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            page = self.fetch_receipts_page(job_id=job_id, cursor=cursor, limit=page_size)
            for item in page.items:
                yield item

            if not page.next_cursor:
                break
            cursor = page.next_cursor

    def fetch_receipts_page(
        self,
        *,
        job_id: str,
        cursor: str | None = None,
        limit: int | None = 100,
    ) -> ReceiptPage:
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        response = self._request("GET", f"/v1/jobs/{job_id}/receipts", params=params)
        if response is None:
            raise ValueError("Response should not be None")
        payload = response.json()

        if isinstance(payload, list):
            items = payload
            next_cursor: str | None = None
            raw: dict[str, Any] = {"items": items}
        else:
            items = list(payload.get("items") or [])
            next_cursor = payload.get("next_cursor") or payload.get("next") or payload.get("cursor")
            raw = payload

        return ReceiptPage(items=items, next_cursor=next_cursor, raw=raw)

    def summarize_receipts(self, job_id: str, page_size: int = 100) -> ReceiptStatus:
        receipts = list(self.iter_receipts(job_id=job_id, page_size=page_size))
        if not receipts:
            return ReceiptStatus(job_id=job_id, total=0, verified_count=0, failed=[], latest_verified=None)

        verifications = verify_receipts(receipts)
        verified = [v for v in verifications if v.verified]
        failed = [v for v in verifications if not v.verified]
        failures: list[ReceiptFailure] = []
        reason_counts: dict[str, int] = {}

        for verification in failed:
            reasons = verification.failure_reasons()
            receipt_id = str(
                verification.receipt.get("receipt_id")
                or verification.receipt.get("id")
                or verification.receipt.get("uuid")
                or ""
            )
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            failures.append(ReceiptFailure(receipt_id=receipt_id, reasons=reasons, verification=verification))

        latest_verified = verified[-1] if verified else None
        return ReceiptStatus(
            job_id=job_id,
            total=len(verifications),
            verified_count=len(verified),
            failed=failed,
            latest_verified=latest_verified,
            failure_reasons=reason_counts,
            failures=failures,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> httpx.Response | None:
        attempt = 0
        while True:
            try:
                client = self._client()
                response = client.request(method=method, url=url, params=params)
            except NetworkError:
                if attempt >= self.max_retries:
                    raise
                attempt += 1
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
                continue

            if response.status_code == 404 and allow_404:
                return None

            if response.status_code in {429} or response.status_code >= 500:
                if attempt >= self.max_retries:
                    response.raise_for_status()
                else:
                    attempt += 1
                    time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
                    continue

            response.raise_for_status()
            return response


@dataclass
class ReceiptPage:
    items: list[dict[str, Any]]
    next_cursor: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _verify_signature(payload: dict[str, Any], signature: dict[str, Any]) -> SignatureValidation:
    key_id = signature.get("key_id", "")
    verifier = ReceiptVerifier(_decode_key(key_id))
    try:
        valid = verifier.verify(payload, signature)
        reason: str | None = None if valid else "signature mismatch"
    except Exception as exc:  # pragma: no cover - verifier could raise on malformed payloads
        valid = False
        reason = str(exc) or "signature verification error"
    algorithm = signature.get("algorithm") or "Ed25519"
    return SignatureValidation(key_id=key_id, valid=valid, algorithm=algorithm, reason=reason)


def verify_receipt(receipt: dict[str, Any]) -> ReceiptVerification:
    payload = {k: v for k, v in receipt.items() if k not in {"signature", "attestations"}}
    miner_sig = receipt.get("signature") or {}
    miner_validation = _verify_signature(payload, miner_sig)

    attestations = receipt.get("attestations") or []
    att_validations = [
        _verify_signature(payload, att) for att in attestations if isinstance(att, dict)
    ]

    return ReceiptVerification(
        receipt=receipt,
        miner_signature=miner_validation,
        coordinator_attestations=att_validations,
    )


def verify_receipts(receipts: Iterable[dict[str, Any]]) -> list[ReceiptVerification]:
    return [verify_receipt(receipt) for receipt in receipts]


def _decode_key(data: str) -> bytes:
    if not data:
        return b""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
