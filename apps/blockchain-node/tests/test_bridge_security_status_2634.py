"""#2634 AUDIT-BN-BRIDGE-SECURITY-STATUS-GAUGE-TRUTHY-1 pin.

``GET /bridge/security/status`` tested the Prometheus gauge object
``bridge_initialized`` (always truthy) instead of the local
``bridge_initialized_value`` flag, so an uninitialised bridge fell into
``bridge._session_factory()`` on ``None`` and answered HTTP 500. It now
reports the zero-validator status body honestly.
"""

from __future__ import annotations

from unittest.mock import Mock

import aitbc_chain.cross_chain.bridge as ccb
from aitbc_chain.rpc import bridge as bridge_rpc


def test_security_status_uninitialised_bridge_is_200(monkeypatch):
    monkeypatch.setattr(ccb, "get_cross_chain_bridge", lambda: None)
    out = bridge_rpc.bridge_security_status(request=Mock())
    assert out["success"] is True
    assert out["validator_count"] == 0
    assert out["bridge_validators_active_latest_epoch"] == 0
    assert out["current_epoch"] == 0
