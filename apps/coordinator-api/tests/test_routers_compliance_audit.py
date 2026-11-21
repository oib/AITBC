"""Tests for GET /v1/compliance/audit-logs (#2377).

The endpoint merges the two compliance-domain audit tables —
``transaction_audit_record`` (PCI/GLBA) and ``phi_access_log`` (HIPAA) —
into one normalized, newest-first list. It is admin-only: the CLI's
``aitbc compliance export-audit`` authenticates with the admin credential.

Router-level ``require_auth`` plus the ``AdminDep`` param are the auth
deps; the security-matrix floor (``/v1/compliance/audit-logs`` → ADMIN) is
enforced by AuthMiddleware, which is disabled in test mode, so these tests
pin the dep + query contract.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from aitbc.auth import create_access_token
from coordinator_api.contexts.compliance.finance import TransactionAuditRecord
from coordinator_api.contexts.compliance.hipaa import PHIAccessLog

BASE = "/v1/compliance/audit-logs"


def _headers(sub: str = "admin-1", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _seed(session: Session) -> None:
    session.add(
        TransactionAuditRecord(
            transaction_id="txn-1",
            actor_id="merchant-1",
            counterparty_id="processor-1",
            amount=Decimal("12.50"),
            asset="AIT",
            classification="pci",
            status="approved",
        )
    )
    session.add(
        PHIAccessLog(
            subject_id="patient-1",
            actor_id="nurse-1",
            action="access",
            resource_id="chart-1",
            outcome="allowed",
            reason="consent granted for treatment",
        )
    )
    session.commit()


class TestAuth:
    def test_no_token_rejected(self, client: TestClient) -> None:
        assert client.get(BASE).status_code == 401

    def test_client_role_forbidden(self, client: TestClient) -> None:
        resp = client.get(BASE, headers=_headers(sub="nurse-1", role="client"))
        assert resp.status_code == 403


class TestAuditLogs:
    def test_empty_tables_return_empty_list(self, client: TestClient) -> None:
        resp = client.get(BASE, headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_admin_gets_records_from_both_tables(self, client: TestClient, db_session: Session) -> None:
        _seed(db_session)
        resp = client.get(BASE, headers=_headers())
        assert resp.status_code == 200, resp.text
        records = resp.json()
        assert len(records) == 2
        sources = {r["source"] for r in records}
        assert sources == {"transaction", "hipaa"}

        tx = next(r for r in records if r["source"] == "transaction")
        assert tx["record_id"].startswith("far_")
        assert tx["actor_id"] == "merchant-1"
        assert tx["subject_id"] == "processor-1"
        assert tx["resource_id"] == "txn-1"
        assert tx["outcome"] == "approved"
        assert tx["timestamp"]

        phi = next(r for r in records if r["source"] == "hipaa")
        assert phi["record_id"].startswith("pal_")
        assert phi["subject_id"] == "patient-1"
        assert phi["actor_id"] == "nurse-1"
        assert phi["action"] == "access"
        assert phi["resource_id"] == "chart-1"
        assert phi["outcome"] == "allowed"
        assert phi["details"]["reason"] == "consent granted for treatment"

    def test_records_ordered_newest_first(self, client: TestClient, db_session: Session) -> None:
        _seed(db_session)
        resp = client.get(BASE, headers=_headers())
        timestamps = [r["timestamp"] for r in resp.json()]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_limit_and_offset(self, client: TestClient, db_session: Session) -> None:
        _seed(db_session)
        resp = client.get(BASE, params={"limit": 1, "offset": 1}, headers=_headers())
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}])
    def test_pagination_bounds(self, client: TestClient, params: dict[str, int]) -> None:
        assert client.get(BASE, params=params, headers=_headers()).status_code == 422
