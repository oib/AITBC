"""#2719: /v1/developer-platform/certifications/verify/{id} must not answer
is_valid:true unconditionally — an expired certification is not valid."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from coordinator_api.contexts.developer_platform.domain.developer_platform import (
    DeveloperCertification,
    DeveloperProfile,
)

BASE = "/v1/developer-platform"


def _seed_cert(db_session: Session, expires_at: datetime | None) -> str:
    profile = DeveloperProfile(wallet_address="0x" + "55" * 20)
    db_session.add(profile)
    db_session.flush()
    cert = DeveloperCertification(
        developer_id=profile.id,
        certification_name="zk-auditor",
        issued_by="aitbc-dao",
        expires_at=expires_at,
    )
    db_session.add(cert)
    db_session.commit()
    return cert.id


def test_verify_valid_cert(client: TestClient, db_session: Session) -> None:
    cert_id = _seed_cert(db_session, expires_at=datetime.now(UTC) + timedelta(days=30))
    resp = client.get(f"{BASE}/certifications/verify/{cert_id}")
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


def test_verify_expired_cert_is_invalid(client: TestClient, db_session: Session) -> None:
    cert_id = _seed_cert(db_session, expires_at=datetime.now(UTC) - timedelta(days=1))
    resp = client.get(f"{BASE}/certifications/verify/{cert_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False
    assert body["expires_at"] is not None


def test_verify_no_expiry_is_valid(client: TestClient, db_session: Session) -> None:
    cert_id = _seed_cert(db_session, expires_at=None)
    resp = client.get(f"{BASE}/certifications/verify/{cert_id}")
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


def test_verify_unknown_cert_404(client: TestClient) -> None:
    resp = client.get(f"{BASE}/certifications/verify/nonexistent-id")
    assert resp.status_code == 404
