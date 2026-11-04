"""Tests for wallet spend policy enforcement."""

from __future__ import annotations


import pytest

from wallet_app.spend_policy import assert_transfer_allowed, spend_policy_enforced


@pytest.mark.unit
def test_spend_policy_off_by_default(monkeypatch):
    monkeypatch.delenv("AITBC_SPEND_POLICY_ENFORCE", raising=False)
    assert not spend_policy_enforced()
    assert_transfer_allowed(100, None)


@pytest.mark.unit
def test_spend_policy_requires_payload(monkeypatch):
    monkeypatch.setenv("AITBC_SPEND_POLICY_ENFORCE", "1")
    with pytest.raises(ValueError, match="payload required"):
        assert_transfer_allowed(10, None)


@pytest.mark.unit
def test_spend_policy_requires_max_amount(monkeypatch):
    monkeypatch.setenv("AITBC_SPEND_POLICY_ENFORCE", "1")
    with pytest.raises(ValueError, match="max_amount required"):
        assert_transfer_allowed(5, {"op": "wallet.execute"})


@pytest.mark.unit
def test_spend_policy_max_amount(monkeypatch):
    monkeypatch.setenv("AITBC_SPEND_POLICY_ENFORCE", "1")
    assert_transfer_allowed(5, {"op": "wallet.execute", "max_amount": 10})
    with pytest.raises(ValueError, match="max_amount"):
        assert_transfer_allowed(11, {"op": "wallet.execute", "max_amount": 10})
