"""Zero-value transaction types need --amount 0 through `aitbc transactions send`.

GPU_REGISTER/MESSAGE/etc. are rejected at apply time when value != 0, while
the CLI used to require a positive amount — making them unreachable. The gate
now allows amount=0 for exactly those types (and rejects nonzero, which would
fail at apply anyway) and keeps rejecting 0 for TRANSFER.
"""

from decimal import Decimal
from unittest.mock import patch

from aitbc_cli.commands import transactions as tx_cmd

RECIPIENT = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


def _send(tmp_path, tx_type, amount):
    """Invoke the send impl with a nonexistent wallet dir; return error messages."""
    errors = []
    with patch.object(tx_cmd, "error", side_effect=lambda m, **kw: errors.append(str(m))):
        tx_cmd._send_transaction_impl(
            "no-such-wallet",
            RECIPIENT,
            Decimal(amount),
            Decimal("0.001"),
            "pw",
            keystore_dir=tmp_path,
            tx_type=tx_type,
        )
    return errors


def test_transfer_rejects_zero_amount(tmp_path):
    assert _send(tmp_path, "TRANSFER", "0") == ["Amount must be positive"]


def test_transfer_positive_amount_passes_gate(tmp_path):
    # Past the amount check, the next failure is the missing keystore.
    assert _send(tmp_path, "TRANSFER", "0.001") == ["Wallet 'no-such-wallet' not found"]


def test_gpu_register_accepts_zero_amount(tmp_path):
    assert _send(tmp_path, "GPU_REGISTER", "0") == ["Wallet 'no-such-wallet' not found"]


def test_gpu_register_rejects_nonzero_amount(tmp_path):
    assert _send(tmp_path, "GPU_REGISTER", "0.001") == ["GPU_REGISTER transactions must have amount=0"]


def test_message_accepts_zero_amount(tmp_path):
    assert _send(tmp_path, "MESSAGE", "0") == ["Wallet 'no-such-wallet' not found"]


def test_zero_value_set_matches_node(tmp_path):
    # Keep the CLI mirror in sync with the apply-side source of truth.
    import pytest

    st = pytest.importorskip("aitbc_chain.state.state_transition")

    assert tx_cmd._ZERO_VALUE_TX_TYPES == st._ZERO_VALUE_TX_TYPES
