"""Bounded CSP report ingestion for the public website.

The public nginx /csp-report route supplies the rate and request-body limits.
The application repeats the body-size limit, validates the complete envelope
before logging, and never records query strings, credentials, referrers or
script samples. Browser reports are untrusted diagnostics, not security events
that authorize any action.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request, Response

from aitbc.aitbc_logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

MAX_REPORT_BYTES = 16_384
MAX_BATCH_REPORTS = 16
_NO_STORE = {"Cache-Control": "no-store"}
_MEDIA_TYPES = {"application/csp-report", "application/reports+json"}
_DIRECTIVE = re.compile(r"[a-z][a-z-]{0,63}")
_SYMBOLIC_URLS = {"inline", "eval", "wasm-eval", "self"}


def _error(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail, headers=_NO_STORE)


def _safe_url(value: object, *, origin_only: bool = False) -> str:
    """Keep a bounded URL without userinfo/query/fragment, or a scheme marker."""
    if not isinstance(value, str):
        return ""
    if value in _SYMBOLIC_URLS:
        return value
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https"):
            return f"{parts.scheme}:" if re.fullmatch(r"[a-z][a-z0-9+.-]{0,31}", parts.scheme) else ""
        host = parts.hostname
        port = parts.port
    except ValueError:
        return ""
    if not host:
        return ""
    if ":" in host:
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    path = "" if origin_only else (parts.path or "/")
    return urlunsplit((parts.scheme, host, path, "", ""))[:512]


def _integer(value: object, maximum: int) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum:
        return value
    return None


def _normalize(body: dict[str, object], *, modern: bool, fallback_url: object = "") -> dict[str, object]:
    document = _safe_url(body.get("documentURL" if modern else "document-uri") or fallback_url)
    raw_directive = body.get("effectiveDirective" if modern else "effective-directive")
    if not raw_directive:
        raw_directive = body.get("violatedDirective" if modern else "violated-directive")
    tokens = raw_directive.split() if isinstance(raw_directive, str) else []
    directive = tokens[0] if tokens else ""
    if not document.startswith(("http://", "https://")) or not _DIRECTIVE.fullmatch(directive):
        raise _error(400, "Invalid CSP report")
    disposition = body.get("disposition")
    fields: dict[str, object] = {
        "event": "csp_violation",
        "document": document,
        "effective_directive": directive,
        "blocked": _safe_url(body.get("blockedURL" if modern else "blocked-uri"), origin_only=True),
        "disposition": disposition if disposition in ("enforce", "report") else "unknown",
    }
    source = _safe_url(body.get("sourceFile" if modern else "source-file"))
    if source:
        fields["source_file"] = source
    for output, legacy, current, maximum in (
        ("status_code", "status-code", "statusCode", 599),
        ("line_number", "line-number", "lineNumber", 2_147_483_647),
        ("column_number", "column-number", "columnNumber", 2_147_483_647),
    ):
        number = _integer(body.get(current if modern else legacy), maximum)
        if number is not None:
            fields[output] = number
    return fields


def _reports(payload: object, media_type: str) -> list[dict[str, object]]:
    if media_type == "application/csp-report":
        body = payload.get("csp-report") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise _error(400, "Invalid CSP report envelope")
        return [_normalize(body, modern=False)]
    if not isinstance(payload, list) or not payload:
        raise _error(400, "Invalid CSP report batch")
    if len(payload) > MAX_BATCH_REPORTS:
        raise _error(413, "Too many CSP reports")
    records: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "csp-violation" or not isinstance(item.get("body"), dict):
            raise _error(400, "Invalid CSP report batch")
        records.append(_normalize(item["body"], modern=True, fallback_url=item.get("url", "")))
    return records


@router.post("/api/csp-report", status_code=204, include_in_schema=False)
async def csp_report(request: Request) -> Response:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in _MEDIA_TYPES:
        raise _error(415, "Unsupported CSP report media type")
    length_header = request.headers.get("content-length")
    if length_header is not None:
        try:
            length = int(length_header)
        except ValueError:
            raise _error(400, "Invalid content length") from None
        if length < 0:
            raise _error(400, "Invalid content length")
        if length > MAX_REPORT_BYTES:
            raise _error(413, "CSP report too large")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REPORT_BYTES:
            raise _error(413, "CSP report too large")
        raw.extend(chunk)
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        raise _error(400, "Invalid CSP report JSON") from None
    # Validate the entire batch first: a malformed later item must not produce
    # a partial set of events followed by a failed HTTP response.
    records = _reports(payload, media_type)
    for fields in records:
        logger.warning(
            "csp_violation %s",
            json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
            extra={"extra": fields},
        )
    return Response(status_code=204, headers=_NO_STORE)
