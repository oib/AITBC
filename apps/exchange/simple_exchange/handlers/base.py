"""Shared base handler with common JSON/CORS helpers."""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.request import urlopen

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
RPC_TIMEOUT = 10  # seconds

RPC_BASE_URL = os.getenv("BLOCKCHAIN_RPC_BASE_URL", "http://localhost:9080").rstrip("/")
if not RPC_BASE_URL.startswith(("http://", "https://")):
    raise RuntimeError(f"BLOCKCHAIN_RPC_BASE_URL must start with http:// or https://, got: {RPC_BASE_URL}")


class BaseHandler(BaseHTTPRequestHandler):
    """Shared base handler with common JSON/CORS helpers."""

    def _rpc_get(self, path: str) -> dict:
        """Fetch JSON from blockchain RPC with timeout.

        Returns parsed JSON dict. Raises on HTTP errors or timeouts.
        """
        url = f"{RPC_BASE_URL}{path}"
        with urlopen(url, timeout=RPC_TIMEOUT) as response:
            return json.loads(response.read().decode())

    def _require_api_key(self) -> bool:
        """Check X-Api-Key header against EXCHANGE_API_KEY env var.

        Returns True if auth is disabled (no key configured) or the key matches.
        Returns False after sending a 401 response if the key is missing/invalid.
        """
        expected = os.getenv("EXCHANGE_API_KEY")
        if not expected:
            return True
        provided = self.headers.get("X-Api-Key", "")
        if provided != expected:
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
