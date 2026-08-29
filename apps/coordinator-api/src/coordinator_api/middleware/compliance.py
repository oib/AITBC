"""Compliance middleware for data classification and consent enforcement (v0.15.2 §B3).

The middleware delegates consent decisions to a ``ConsentTracker``. Use
``SQLConsentStore`` from ``coordinator_api.contexts.compliance.services`` to back
the tracker with the ``consent_record`` table. Payload classification remains
header-based; a dedicated data-classification service can be used if available.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from aitbc.compliance.consent import ConsentTracker
from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import DataClassification, SENSITIVE_CLASSIFICATIONS, normalize_classification


class ComplianceMiddleware(BaseHTTPMiddleware):
    """Middleware that blocks requests for sensitive data without active consent."""

    def __init__(self, app: FastAPI, tracker: ConsentTracker | None = None) -> None:
        super().__init__(app)
        self.tracker = tracker or ConsentTracker()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Inspect request headers for classification and consent before routing."""
        classification = request.headers.get("x-data-classification", "")
        subject_id = request.headers.get("x-consent-subject", "")
        purpose = request.headers.get("x-consent-purpose", "")

        if classification:
            try:
                label = normalize_classification(classification)
            except Exception:
                return Response("Invalid data classification", status_code=400)
            if label in SENSITIVE_CLASSIFICATIONS and subject_id and purpose:
                if not self.tracker.is_consented(subject_id, purpose, label):
                    return Response("Consent required for sensitive data processing", status_code=403)

        return await call_next(request)


def require_consent(
    tracker: ConsentTracker,
    subject_id: str,
    purpose: str,
    classification: DataClassification | str | None = None,
) -> None:
    """Raise ``PolicyViolationError`` if active consent is missing."""
    try:
        tracker.require_consent(subject_id, purpose, classification)
    except PolicyViolationError as exc:
        raise PolicyViolationError(f"compliance check failed: {exc}") from exc
