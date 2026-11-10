"""Shared base handler with common JSON/CORS helpers."""

import hmac
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler
from urllib.request import urlopen

from aitbc.operations import BeginResult, BeginStatus, OperationLedger

from ..db import get_db_path

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
RPC_TIMEOUT = 10  # seconds

RPC_BASE_URL = os.getenv("BLOCKCHAIN_RPC_BASE_URL", "http://localhost:8202").rstrip("/")
if not RPC_BASE_URL.startswith(("http://", "https://")):
    raise RuntimeError(f"BLOCKCHAIN_RPC_BASE_URL must start with http:// or https://, got: {RPC_BASE_URL}")


def _idempotency_key(handler) -> str:
    """The request's Idempotency-Key header, or "".

    Reads via getattr so MagicMock(spec=Mixin) handlers in tests — which lack
    the ``headers`` attribute BaseHTTPRequestHandler provides — don't break.
    """
    headers = getattr(handler, "headers", None)
    if headers is None:
        return ""
    return (headers.get("Idempotency-Key") or "").strip()


# In-memory sliding-window buckets for the section-9 abuse limits, shared by
# every handler mixin (#1678). The handlers run on a ThreadPoolExecutor
# (main.py), so a lock guards the map; buckets are per-process state —
# restarting the service resets the windows, which the design accepts
# (limits exist to blunt spam, not to audit it).
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque] = {}
_RATE_WINDOW_S = 60.0
_RATE_MAX_KEYS = 10_000


def _rate_limit_hit(key: str, per_minute: int) -> bool:
    """Record one event for ``key``; True when the window is already full."""
    if per_minute <= 0:
        return False
    now = time.monotonic()
    with _RATE_LOCK:
        if len(_RATE_BUCKETS) >= _RATE_MAX_KEYS:
            for k, bucket in list(_RATE_BUCKETS.items()):
                if not bucket or now - bucket[-1] > _RATE_WINDOW_S:
                    del _RATE_BUCKETS[k]
        dq = _RATE_BUCKETS.get(key)
        if dq is None:
            dq = deque()
            _RATE_BUCKETS[key] = dq
        while dq and now - dq[0] > _RATE_WINDOW_S:
            dq.popleft()
        if len(dq) >= per_minute:
            return True
        dq.append(now)
        return False


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def client_ip_for_rate_limit(handler) -> str:
    """Client IP for per-IP rate buckets.

    Delegates to the handler's ``_client_ip`` (trusted-proxy aware — see
    ExchangeMixin) when the assembled handler provides it; falls back to the
    raw request peer so single-mixin test doubles still get a stable bucket.
    """
    method = getattr(handler, "_client_ip", None)
    if callable(method):
        try:
            ip = method()
        except Exception:
            ip = None
        if isinstance(ip, str) and ip:
            return ip
    request = getattr(handler, "request", None)
    client = getattr(request, "client", None)
    peer = getattr(client, "host", None)
    return peer if isinstance(peer, str) and peer else "unknown"


def mutating_rate_limit_reached(handler, scope: str, per_minute: int) -> bool:
    """True — after sending 429 — when ``scope``'s per-IP window is full.

    ``scope`` namespaces the bucket (``market``, ``bridge``, ``wallet-connect``,
    ...). Used by the market/bridge/wallet mutating handlers that had no rate
    limiting at all (#1678).
    """
    if _rate_limit_hit(f"{scope}:{client_ip_for_rate_limit(handler)}", per_minute):
        handler.send_json_response({"error": "Rate limit reached"}, status=429)  # type: ignore[attr-defined]
        return True
    return False


_operation_ledgers: dict[str, OperationLedger] = {}


def get_operation_ledger() -> OperationLedger:
    """Return this service's operation ledger, one row per Idempotency-Key.

    The ledger lives inside the exchange database file so handlers can pass
    their own connection to ``begin``/``complete`` and commit the operation
    record atomically with the domain write.
    """
    path = get_db_path()
    ledger = _operation_ledgers.get(path)
    if ledger is None:
        ledger = OperationLedger(path, service="exchange")
        _operation_ledgers[path] = ledger
    return ledger


class BaseHandler(BaseHTTPRequestHandler):
    """Shared base handler with common JSON/CORS helpers."""

    def _send_operation_result(self, begin: BeginResult) -> None:
        """Respond for a non-EXECUTE ``begin`` outcome.

        REPLAY returns the originally recorded response verbatim; the other
        outcomes are 409s with distinct honest messages.
        """
        if begin.status is BeginStatus.REPLAY:
            self.send_json_response(begin.result, status=begin.response_status or 200)
            return
        if begin.status is BeginStatus.CONFLICT:
            self.send_json_response({"error": "Idempotency-Key was already used with a different request"}, status=409)
            return
        if begin.status is BeginStatus.UNCERTAIN:
            self.send_json_response(
                {
                    "error": "A previous attempt with this Idempotency-Key did not complete and its "
                    "outcome is unknown; it must be resolved before retrying"
                },
                status=409,
            )
            return
        self.send_json_response({"error": "A request with this Idempotency-Key is already in progress"}, status=409)

    def _rpc_get(self, path: str) -> dict:
        """Fetch JSON from blockchain RPC with timeout.

        Returns parsed JSON dict. Raises on HTTP errors or timeouts.
        """
        url = f"{RPC_BASE_URL}{path}"
        # RPC_BASE_URL is validated (module-level startswith http(s):// check, see top of this file) before this call
        with urlopen(url, timeout=RPC_TIMEOUT) as response:  # nosec B310
            return json.loads(response.read().decode())  # type: ignore[no-any-return]

    def _require_api_key(self) -> bool:
        """Check X-Api-Key header against EXCHANGE_API_KEY env var.

        Returns False after sending a 401 response if the key is missing, invalid,
        or not configured. A missing EXCHANGE_API_KEY is treated as an auth failure.
        """
        expected = os.getenv("EXCHANGE_API_KEY")
        if not expected:
            self.send_error(401, "API key not configured")
            return False
        provided = self.headers.get("X-Api-Key", "")
        # Constant-time compare — `!=` returns at the first differing byte.
        if not provided or not hmac.compare_digest(provided, expected):
            self.send_error(401, "Invalid or missing X-Api-Key")
            return False
        return True

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _read_json_body(self):
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.send_error(411, "Content-Length required")
            return {}
        try:
            length = int(length_header)
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return {}
        if length < 0:
            self.send_error(400, "Invalid Content-Length")
            return {}
        if length > MAX_BODY_BYTES:
            self.send_error(413, f"Request body too large (max {MAX_BODY_BYTES} bytes)")
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON body")
            return {}
