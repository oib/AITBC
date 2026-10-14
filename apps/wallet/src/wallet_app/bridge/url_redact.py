"""Compatibility shim — the implementation lives in ``aitbc.url_redact``.

It moved to the shared package so ``aitbc_logging``'s httpx filter can use
the same redaction (ETH-15); bridge imports keep working through this shim.
"""

from aitbc.url_redact import redact_text, redact_url

__all__ = ["redact_text", "redact_url"]
