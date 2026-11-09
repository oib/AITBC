"""Tests for /v1/hipaa/* — consent lifecycle, PHI access gating, right-to-delete (#1289 round 4).

Real ``HIPAAComplianceService`` on the in-memory session — consent records,
access logs and the policy-template controls are exercised end to end.
Router-level ``require_auth`` is the only auth dep; the security matrix
(`/v1/hipaa/*` → ANY) is enforced by AuthMiddleware, which is disabled in
test mode, so these tests pin the dep + service contract.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from coordinator_api.contexts.compliance.hipaa import ConsentRecord, PHIAccessLog

BASE = "/v1/hipaa"


def _headers(sub: str = "nurse-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _grant(client: TestClient, subject: str = "patient-1", purpose: str = "treatment") -> dict:
    resp = client.post(
        f"{BASE}/consent",
        json={"subject_id": subject, "purpose": purpose, "expires_in_days": 30},
        headers=_headers(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAuth:
    def test_no_token_rejected(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/consent", json={"subject_id": "s", "purpose": "p"}).status_code == 401
        assert client.post(f"{BASE}/phi/access?subject_id=s&actor_id=a&resource_id=r&purpose=p").status_code == 401


class TestConsentLifecycle:
    def test_grant_returns_active_record(self, client: TestClient, db_session: Session) -> None:
        data = _grant(client)
        assert data["subject_id"] == "patient-1"
        assert data["purpose"] == "treatment"
        assert data["granted"] is True
        assert data["status"] == "active"
        row = db_session.get(ConsentRecord, data["id"])
        assert row is not None

    def test_revoke_marks_revoked(self, client: TestClient, db_session: Session) -> None:
        data = _grant(client)
        resp = client.post(f"{BASE}/consent/{data['id']}/revoke", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
        assert resp.json()["granted"] is False

    def test_revoke_missing_404(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/consent/consent_missing/revoke", headers=_headers())
        assert resp.status_code == 404

    def test_revoke_twice_still_200(self, client: TestClient) -> None:
        data = _grant(client)
        client.post(f"{BASE}/consent/{data['id']}/revoke", headers=_headers())
        resp = client.post(f"{BASE}/consent/{data['id']}/revoke", headers=_headers())
        assert resp.status_code == 200


class TestPhiAccess:
    def _access(self, client: TestClient, subject: str = "patient-1", purpose: str = "treatment") -> object:
        return client.post(
            f"{BASE}/phi/access",
            params={"subject_id": subject, "actor_id": "nurse-1", "resource_id": "chart-1", "purpose": purpose},
            headers=_headers(),
        )

    def test_access_denied_without_consent(self, client: TestClient) -> None:
        resp = self._access(client)
        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()

    def test_access_allowed_with_consent(self, client: TestClient) -> None:
        _grant(client)
        resp = self._access(client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["outcome"] == "allowed"
        assert data["action"] == "access"

    def test_access_denied_after_revoke(self, client: TestClient) -> None:
        data = _grant(client)
        client.post(f"{BASE}/consent/{data['id']}/revoke", headers=_headers())
        assert self._access(client).status_code == 403

    def test_access_denied_for_wrong_purpose(self, client: TestClient) -> None:
        _grant(client, purpose="treatment")
        assert self._access(client, purpose="billing").status_code == 403

    def test_every_attempt_is_logged(self, client: TestClient, db_session: Session) -> None:
        self._access(client)  # denied
        _grant(client)
        self._access(client)  # allowed
        logs = db_session.scalars(select(PHIAccessLog)).all()
        assert len(logs) == 2
        outcomes = {log.outcome for log in logs}
        assert outcomes == {"denied", "allowed"}


class TestRightToDelete:
    def test_delete_returns_audit_log_and_revokes_consents(self, client: TestClient, db_session: Session) -> None:
        _grant(client, subject="patient-9")
        _grant(client, subject="patient-9", purpose="billing")
        resp = client.post(
            f"{BASE}/phi/delete",
            params={"subject_id": "patient-9"},
            json={"actor_id": "patient-9"},
            headers=_headers(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "delete"
        assert data[0]["subject_id"] == "patient-9"
        consents = db_session.scalars(select(ConsentRecord).where(ConsentRecord.subject_id == "patient-9")).all()
        assert consents and all(c.status == "revoked" and not c.granted for c in consents)

    def test_delete_other_subject_untouched(self, client: TestClient, db_session: Session) -> None:
        _grant(client, subject="patient-keep")
        client.post(
            f"{BASE}/phi/delete",
            params={"subject_id": "patient-gone"},
            json={"actor_id": "patient-gone"},
            headers=_headers(),
        )
        keep = db_session.scalars(select(ConsentRecord).where(ConsentRecord.subject_id == "patient-keep")).all()
        assert keep and all(c.status == "active" for c in keep)
