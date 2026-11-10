"""Regression tests for aitbc.url_redact (#1636).

redact_url used to raise ValueError (``Port could not be cast to integer
value as '8202:'``) when redact_text matched a URL immediately followed by a
colon — e.g. ``http://10.103.6.37:8202: All connection attempts failed``.
Raised inside the logging formatter it produced ``--- Logging error ---``
and the log record was lost.
"""

from __future__ import annotations

import pytest

from aitbc.url_redact import redact_text, redact_url


@pytest.mark.unit
def test_url_followed_by_colon_does_not_raise():
    text = "connect http://10.103.6.37:8202: All connection attempts failed"
    out = redact_text(text)
    assert "10.103.6.37:8202" in out
    assert out.endswith(": All connection attempts failed")
    assert "Logging error" not in out


@pytest.mark.unit
def test_redact_url_trailing_colon_port():
    # The exact shape that raised: netloc ends '8202:' → parts.port ValueError.
    # redact_url drops the unparseable port rather than raising.
    assert redact_url("http://10.103.6.37:8202:") == "http://10.103.6.37"


@pytest.mark.unit
def test_redact_url_malformed_port_drops_port_not_raise():
    assert redact_url("http://host:8202:path") == "http://host"
    assert redact_url("http://host:notaport/x") == "http://host"


@pytest.mark.unit
def test_redact_text_preserves_sentence_punctuation():
    out = redact_text("failed for url 'http://h:1/secret?key=x'.")
    assert out == "failed for url 'http://h:1'."


@pytest.mark.unit
def test_redact_url_normal_cases_unchanged():
    assert redact_url("https://user:pw@example.com:8443/a/b?c=d#f") == "https://example.com:8443"
    assert redact_url("http://example.com/path") == "http://example.com"
    assert redact_url(None) == "(unset)"
    assert redact_url("") == "(unset)"
    assert redact_url("not a url") == "(redacted)"
