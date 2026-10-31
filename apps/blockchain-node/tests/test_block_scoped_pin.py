"""COMMITTED-SURFACE-1 regression (#755) — the non-block-scoped bridge flag
is pinned: refused at settings construction, reachable only via
post-construction patch (the test mode the 11 bridge suites use).

A live env flip of ``BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=false``
silently re-opened direct committed-table mutations in bridge_transfer —
invisible to every check. The pin refuses it at startup instead.
"""

from __future__ import annotations

import pytest


def _settings(**kwargs):
    from aitbc_chain.config import ChainSettings

    return ChainSettings(**kwargs)


def test_env_false_refused(monkeypatch) -> None:
    monkeypatch.setenv("BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS", "false")
    with pytest.raises(Exception, match="block_scoped_preregistered_transactions"):
        _settings()


def test_kwarg_false_refused() -> None:
    with pytest.raises(Exception, match="block_scoped_preregistered_transactions"):
        _settings(block_scoped_preregistered_transactions=False)


def test_default_true(monkeypatch) -> None:
    monkeypatch.delenv("BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS", raising=False)
    assert _settings().block_scoped_preregistered_transactions is True


def test_post_construction_patch_still_works(monkeypatch) -> None:
    """The tested legacy mode survives: patching the attribute after
    construction bypasses the pin (no validate_assignment)."""
    monkeypatch.delenv("BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS", raising=False)
    s = _settings()
    s.block_scoped_preregistered_transactions = False
    assert s.block_scoped_preregistered_transactions is False
