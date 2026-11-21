"""Regression tests for gpu-onchain --wait result handling (#2404)."""

from unittest.mock import patch

from aitbc_cli.utils.gpu_onchain import apply_wait_result


def test_apply_wait_result_drops_stale_relay_warning_on_seal():
    """A sealed tx must not keep the submit-time fan-out warning (#2404)."""
    result = {
        "transaction_hash": "0xabc",
        "warning": "transaction relay outcome unknown (wait timed out); verify the tx seals",
        "peer_relay": {"status": "pending"},
    }
    with patch("aitbc_cli.utils.gpu_onchain.wait_for_tx", return_value={"block_height": 42}):
        out = apply_wait_result(result, "http://rpc", "0xabc")
    assert out["mined"] is True
    assert out["block_height"] == 42
    assert "warning" not in out
    assert out["peer_relay"] == {"status": "pending"}


def test_apply_wait_result_keeps_warning_on_timeout():
    """An unconfirmed tx keeps mined:false and the relay warning — both accurate."""
    result = {
        "transaction_hash": "0xabc",
        "warning": "transaction relay outcome unknown (wait timed out); verify the tx seals",
    }
    with patch("aitbc_cli.utils.gpu_onchain.wait_for_tx", return_value=None):
        out = apply_wait_result(result, "http://rpc", "0xabc")
    assert out["mined"] is False
    assert "warning" in out
