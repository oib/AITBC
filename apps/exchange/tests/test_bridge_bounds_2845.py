"""#2845: bridge withdraw-signature bounds + deposits int() params.

- ``_verify_bridge_withdrawal_signatures`` now signs
  ``BRIDGE_WITHDRAW:{eth}:{ait}:{expiry_height}`` — a quorum captured under
  the old 3-field message must NOT verify (replay bound).
- ``handle_bridge_withdraw`` rejects non-list/oversized signature lists,
  missing expiry_height, and already-expired bounds with 400 — before any
  keccak/recover work.
- ``handle_bridge_deposits`` answers 400 (not 500) on non-integer
  limit/offset.
"""

import urllib.parse
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.exchange.simple_exchange.handlers import bridge as bridge_module
from apps.exchange.simple_exchange.handlers.bridge import BridgeMixin, _MAX_WITHDRAW_SIGNATURES


class _Handler(BridgeMixin):
    pass


@pytest.fixture
def handler():
    return _Handler()


def _signer():
    try:
        from eth_keys import keys
    except ImportError as e:
        pytest.skip(f"eth_keys not installed: {e}")
    private = keys.PrivateKey(b"\x01" * 32)
    return private, private.public_key.to_address()


def _cfg(signers=("0x" + "11" * 20,), threshold=1):
    from apps.exchange.simple_exchange.config import BridgeConfig

    return BridgeConfig(
        bridge_eth_address="0x818018F30d8F5FB7AE7a64f25895F15110923748",
        bridge_contract_address="0x24403CCff489D9355A534D34d4F88bC5b3EcF6FA",
        withdraw_enabled=False,
        multisig_threshold=threshold,
        signers=signers,
    )


class TestExpiryBoundMessage:
    def test_old_three_field_signature_does_not_verify(self, handler):
        """A signature over BRIDGE_WITHDRAW:eth:ait (no expiry) is dead."""
        private, addr = _signer()
        # sign the OLD format — must fail against the new 4-field message
        old_msg = f"BRIDGE_WITHDRAW:{addr}:1.0".encode()
        sig = private.sign_msg(old_msg).to_hex()
        with patch.object(bridge_module, "bridge_config", _cfg((addr,), 1)):
            ok, count = handler._verify_bridge_withdrawal_signatures(addr, Decimal("1.0"), [{"signature": sig}], 2000)
        assert ok is False
        assert count == 0

    def test_new_four_field_signature_verifies(self, handler):
        private, addr = _signer()
        msg = f"BRIDGE_WITHDRAW:{addr}:1.0:2000".encode()
        sig = private.sign_msg(msg).to_hex()
        with patch.object(bridge_module, "bridge_config", _cfg((addr,), 1)):
            ok, count = handler._verify_bridge_withdrawal_signatures(addr, Decimal("1.0"), [{"signature": sig}], 2000)
        assert ok is True
        assert count == 1


class TestWithdrawRequestBounds:
    def _mock_handler(self, body, head=1000):
        h = MagicMock()
        h.send_json_response = MagicMock()
        h.send_error = MagicMock()
        h._read_json_body = MagicMock(return_value=body)
        h._require_api_key = MagicMock(return_value=True)
        h._chain_head_height = MagicMock(return_value=head)
        for name in ("handle_bridge_withdraw", "_verify_bridge_withdrawal_signatures"):
            setattr(h, name, getattr(BridgeMixin, name).__get__(h, BridgeMixin))
        return h

    def _post(self, h, body):
        with (
            patch.object(bridge_module, "mutating_rate_limit_reached", return_value=False),
            patch.object(bridge_module, "bridge_config", _cfg()),
        ):
            h.handle_bridge_withdraw()
        return h.send_json_response.call_args

    def test_oversized_signatures_list_400(self):
        body = {
            "ait_amount": "1.0",
            "eth_address": "0x" + "22" * 20,
            "expiry_height": 2000,
            "signatures": [{"signature": "aa"}] * (_MAX_WITHDRAW_SIGNATURES + 1),
        }
        call = self._post(self._mock_handler(body), body)
        assert call[1].get("status") == 400
        assert "signatures" in call[0][0]["error"]

    def test_non_list_signatures_400(self):
        body = {
            "ait_amount": "1.0",
            "eth_address": "0x" + "22" * 20,
            "expiry_height": 2000,
            "signatures": "not-a-list",
        }
        call = self._post(self._mock_handler(body), body)
        assert call[1].get("status") == 400

    def test_missing_expiry_height_400(self):
        body = {
            "ait_amount": "1.0",
            "eth_address": "0x" + "22" * 20,
            "signatures": [],
        }
        call = self._post(self._mock_handler(body), body)
        assert call[1].get("status") == 400
        assert "expiry_height" in call[0][0]["error"]

    def test_expired_expiry_height_400(self):
        body = {
            "ait_amount": "1.0",
            "eth_address": "0x" + "22" * 20,
            "expiry_height": 1000,  # == head
            "signatures": [],
        }
        call = self._post(self._mock_handler(body, head=1000), body)
        assert call[1].get("status") == 400
        assert "expired" in call[0][0]["error"]

    def test_live_expiry_reaches_signature_gate(self):
        """expiry > head clears the new gates — empty signer config then
        answers 403 forbidden, proving the bound checks passed."""
        body = {
            "ait_amount": "1.0",
            "eth_address": "0x" + "22" * 20,
            "expiry_height": 2000,
            "signatures": [],
        }
        call = self._post(self._mock_handler(body, head=1000), body)
        assert call[1].get("status") == 403


class TestDepositsIntParams:
    def test_bad_limit_offset_400_not_500(self):
        h = MagicMock()
        h.send_json_response = MagicMock()
        h.send_error = MagicMock()
        h.handle_bridge_deposits = BridgeMixin.handle_bridge_deposits.__get__(h, BridgeMixin)
        for qs in ("limit=abc", "offset=xyz", "limit=1.5&offset=0"):
            h.send_json_response.reset_mock()
            parsed = urllib.parse.urlparse(f"/v1/bridge/deposits?{qs}")
            h.handle_bridge_deposits(parsed)
            call = h.send_json_response.call_args
            assert call is not None and call[1].get("status") == 400, qs
