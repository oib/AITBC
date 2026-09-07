"""
A-4: Energy-quote verification fails closed when ENERGY_OPERATOR_ADDRESS
or the energy pricing oracle is not configured.

Previously, a missing ENERGY_OPERATOR_ADDRESS silently skipped the operator
signature check, and a missing oracle config fell back to the quote's
self-attested profile/rate. Both paths now reject with 503.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from coordinator_api.contexts.payments.services.payments import (
    _resolve_authoritative_inputs,
)


class _FakeQuote:
    """Minimal stand-in for EnergyQuote to test _resolve_authoritative_inputs."""

    def to_profile(self):
        return "self-attested-profile"

    def to_rate(self):
        return "self-attested-rate"

    @property
    def resource_id(self):
        return "gpu-0"

    @property
    def evm_block_number(self):
        return None


def test_resolve_authoritative_inputs_fails_without_oracle_config():
    """No fallback to self-attested values when oracle is not configured."""
    quote = _FakeQuote()
    with patch("coordinator_api.config.settings") as mock_settings:
        mock_settings.energy_pricing_contract_address = None
        mock_settings.eth_rpc_url = None
        with pytest.raises(HTTPException) as exc_info:
            _resolve_authoritative_inputs(quote)
    assert exc_info.value.status_code == 503
    assert "oracle is not configured" in exc_info.value.detail


def test_resolve_authoritative_inputs_fails_with_only_contract():
    """Contract set but no RPC URL still fails."""
    quote = _FakeQuote()
    with patch("coordinator_api.config.settings") as mock_settings:
        mock_settings.energy_pricing_contract_address = "0xabc"
        mock_settings.eth_rpc_url = None
        with pytest.raises(HTTPException) as exc_info:
            _resolve_authoritative_inputs(quote)
    assert exc_info.value.status_code == 503


def test_resolve_authoritative_inputs_fails_with_only_rpc():
    """RPC URL set but no contract still fails."""
    quote = _FakeQuote()
    with patch("coordinator_api.config.settings") as mock_settings:
        mock_settings.energy_pricing_contract_address = None
        mock_settings.eth_rpc_url = "https://eth.example.com"
        with pytest.raises(HTTPException) as exc_info:
            _resolve_authoritative_inputs(quote)
    assert exc_info.value.status_code == 503
