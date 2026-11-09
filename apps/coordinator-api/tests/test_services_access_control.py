"""Coverage for the access_control service (#1289 residual).

AccessController.verify_access is the gate for confidential-transaction
data access. The participant/transaction lookups are stubbed (role is
derived from the requester-id prefix, transactions are hardcoded), so
these tests pin the *decision logic* contract: who is allowed, who is
denied, and where privileged prefix-derived roles fail closed (#1359 fixed).
"""

from datetime import UTC, datetime

import pytest

from coordinator_api.contexts.security.services.access_control import (
    AccessController,
    PolicyStore,
)
from coordinator_api.schemas import ConfidentialAccessRequest


@pytest.fixture
def controller() -> AccessController:
    return AccessController(PolicyStore())


def _req(requester: str, transaction_id: str = "tx-123", purpose: str = "settlement") -> ConfidentialAccessRequest:
    return ConfidentialAccessRequest(transaction_id=transaction_id, requester=requester, purpose=purpose)


# ---------------------------------------------------------------------------
# Passing pins — current behavior that is correct and must be preserved
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_requester_denied(controller):
    assert controller.verify_access(_req("nobody-1")) is False


@pytest.mark.unit
def test_unknown_transaction_denied(controller):
    assert controller.verify_access(_req("client-456", transaction_id="other-1")) is False


@pytest.mark.unit
def test_client_settlement_on_own_transaction_allowed(controller):
    # client-456 is a participant of the stubbed tx-123 and holds settlement_own.
    assert controller.verify_access(_req("client-456")) is True


@pytest.mark.unit
def test_miner_settlement_on_assigned_transaction_allowed(controller):
    assert controller.verify_access(_req("miner-789")) is True


@pytest.mark.unit
def test_client_cannot_audit(controller):
    # Client role lacks audit/audit_all permissions.
    assert controller.verify_access(_req("client-456", purpose="audit")) is False


@pytest.mark.unit
def test_non_participant_client_denied(controller):
    # client-999 is a valid role but not a participant of tx-123.
    assert controller.verify_access(_req("client-999")) is False


@pytest.mark.unit
def test_cache_hit_returns_same_result(controller):
    req = _req("client-456")
    first = controller.verify_access(req)
    second = controller.verify_access(req)
    assert first is second is True
    assert len(controller._access_cache) == 1


@pytest.mark.unit
def test_revoke_access_evicts_cached_result(controller):
    controller.verify_access(_req("client-456"))
    controller.revoke_access("client-456")
    assert controller._access_cache == {}


@pytest.mark.unit
def test_access_summary_for_known_and_unknown(controller):
    summary = controller.get_access_summary("client-456")
    assert summary["role"] == "client"
    assert "settlement_own" in summary["permissions"]
    assert controller.get_access_summary("nobody-1") == {"error": "Participant not found"}


# ---------------------------------------------------------------------------
# Regression pins — #1359 defects fixed (fail-closed privileged roles + live time_restrictions)
# ---------------------------------------------------------------------------


def test_auditor_prefix_must_not_grant_privileged_access(controller):
    # The requester string is self-asserted; _get_participant_info maps
    # 'auditor-*' -> role auditor with audit_all/compliance_all permissions.
    # An unprivileged caller can claim the prefix and read audit data.
    # Expected (fail-closed): deny until real identity binding exists.
    assert controller.verify_access(_req("auditor-999", purpose="audit")) is False


def test_auditor_access_respects_business_hours_policy(controller, monkeypatch):
    # auditor_compliance policy declares business_hours_only, but
    # _apply_policies returns True for audit/compliance before any time
    # check. Pin a Saturday 03:00 UTC request -> must be denied.
    import coordinator_api.contexts.security.services.access_control as ac

    class _SatNight(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 7, 3, 0, tzinfo=UTC)  # Saturday

    monkeypatch.setattr(ac, "datetime", _SatNight)
    assert controller.verify_access(_req("auditor-001", purpose="audit")) is False
