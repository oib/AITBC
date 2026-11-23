"""POST /developer-platform/certifications caller restriction + bounded
reputation boost (#2682).

The route took no user dependency and ``grant_certification`` added
10–100 reputation per call without limit — a developer could self-grant
EXPERT repeatedly. Granting is now admin-only, and the boost applies
once per (developer, certification_name, level).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

from coordinator_api.contexts.developer_platform.domain.developer_platform import (
    DeveloperProfile,
)

BASE = "/v1/developer-platform"
DEV_ID = "dev-cert-1"


def _headers(role: str = "client", sub: str = "u-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _developer(db_session) -> DeveloperProfile:
    row = DeveloperProfile(id=DEV_ID, wallet_address="0x" + "dd" * 20)
    db_session.add(row)
    db_session.commit()
    return row


def _grant_body(level: str = "expert") -> dict:
    return {
        "developer_id": DEV_ID,
        "certification_name": "Blockchain Development",
        "level": level,
        "issued_by": "ops",
    }


def test_client_cannot_grant_certification(client: TestClient, db_session):
    _developer(db_session)
    resp = client.post(f"{BASE}/certifications", json=_grant_body(), headers=_headers("client"))
    assert resp.status_code == 403


def test_admin_grant_boosts_reputation_once(client: TestClient, db_session):
    _developer(db_session)
    headers = _headers("admin", "admin-1")
    first = client.post(f"{BASE}/certifications", json=_grant_body(), headers=headers)
    assert first.status_code == 200, first.text
    db_session.expire_all()
    assert db_session.get(DeveloperProfile, DEV_ID).reputation_score == 100.0

    # Repeat grant of the same (developer, name, level): recorded, no boost.
    second = client.post(f"{BASE}/certifications", json=_grant_body(), headers=headers)
    assert second.status_code == 200, second.text
    db_session.expire_all()
    assert db_session.get(DeveloperProfile, DEV_ID).reputation_score == 100.0


def test_different_level_still_boosts(client: TestClient, db_session):
    _developer(db_session)
    headers = _headers("admin", "admin-2")
    assert client.post(f"{BASE}/certifications", json=_grant_body("expert"), headers=headers).status_code == 200
    resp = client.post(f"{BASE}/certifications", json=_grant_body("beginner"), headers=headers)
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    # EXPERT 100 + BEGINNER 10 — bounded per distinct (name, level) pair.
    assert db_session.get(DeveloperProfile, DEV_ID).reputation_score == 110.0
