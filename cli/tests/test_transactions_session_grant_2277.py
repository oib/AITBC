"""#2277 — AGENT_SESSION_GRANT without expires_at_height must warn.

The chain accepts a grant payload with no ``expires_at_height`` and the
session then never expires (agent_spend._grant_verdict: missing expiry is
unbounded). ``transactions send``/batch now warn loudly so the operator
sees the unbounded grant before signing.
"""

from decimal import Decimal
from unittest.mock import patch

from aitbc_cli.commands import transactions as tx_cmd

RECIPIENT = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


def _send(tmp_path, tx_type, payload):
    """Invoke the send impl with a nonexistent wallet; return warning messages."""
    warnings = []
    with (
        patch.object(tx_cmd, "warning", side_effect=lambda m, **kw: warnings.append(str(m))),
        patch.object(tx_cmd, "error", side_effect=lambda m, **kw: None),
    ):
        tx_cmd._send_transaction_impl(
            "no-such-wallet",
            RECIPIENT,
            Decimal("0"),
            Decimal("0.001"),
            "pw",
            keystore_dir=tmp_path,
            tx_type=tx_type,
            payload=payload,
        )
    return warnings


def test_grant_without_expiry_warns(tmp_path):
    warnings = _send(tmp_path, "AGENT_SESSION_GRANT", {"agent_address": RECIPIENT, "ops": ["swap"]})
    assert any("never expire" in w for w in warnings)


def test_grant_without_payload_warns(tmp_path):
    warnings = _send(tmp_path, "AGENT_SESSION_GRANT", None)
    assert any("never expire" in w for w in warnings)


def test_grant_with_expiry_is_quiet(tmp_path):
    warnings = _send(
        tmp_path,
        "AGENT_SESSION_GRANT",
        {"agent_address": RECIPIENT, "ops": ["swap"], "expires_at_height": 999999},
    )
    assert not any("never expire" in w for w in warnings)


def test_other_tx_types_do_not_warn(tmp_path):
    warnings = _send(tmp_path, "AGENT_SESSION_REVOKE", {"session_id": "s1"})
    assert not any("never expire" in w for w in warnings)
