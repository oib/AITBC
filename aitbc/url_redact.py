"""Keep RPC URLs out of anything printed, logged, or persisted (ETH-15).

Ethereum RPC endpoints may carry credentials in their path (keyed gateway
URLs). Operator output, journal lines, error strings, and database fields
must never contain more than ``scheme://host[:port]`` — the path, query,
userinfo, and fragment are dropped unconditionally.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_URL_RE = re.compile(r"https?://\S+")

# Trailing characters a URL regex match commonly over-captures from the
# surrounding sentence — kept so "for url '<redacted>'." stays readable.
# ':' covers "http://host:8202: All connection attempts failed" — a URL
# immediately followed by a colon (#1636); without it the match reaches
# urlsplit with '8202:' as the port and parts.port raises ValueError.
_TRAILING = "').,;]>\":"


def redact_url(url: str | None) -> str:
    """Return ``scheme://host[:port]`` only — never the path, query,
    userinfo, or fragment. An unset or unparseable value becomes a fixed
    placeholder rather than being echoed (it could still carry a key)."""
    if not url:
        return "(unset)"
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "(redacted)"
    if not parts.scheme or not parts.hostname:
        return "(redacted)"
    host = parts.hostname
    try:
        port = parts.port
    except ValueError:
        # Malformed port (e.g. 'host:8202:path' reached urlsplit whole) —
        # drop the port rather than raising inside the logging formatter.
        port = None
    if port is not None:
        host = f"{host}:{port}"
    return f"{parts.scheme}://{host}"


def redact_text(text: str) -> str:
    """Replace every http(s) URL in arbitrary text with its redacted form.

    Use on exception text before printing or persisting it — httpx error
    messages embed the full request URL.
    """
    return _URL_RE.sub(_redact_match, str(text))


def _redact_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    tail = ""
    while raw and raw[-1] in _TRAILING:
        tail = raw[-1] + tail
        raw = raw[:-1]
    return redact_url(raw) + tail
