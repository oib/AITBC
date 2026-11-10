"""Coverage pin: ``offset`` on governance list endpoints (#1503 residual,
914876188).

``GET /v1/governance/profiles`` and ``GET /v1/governance/votes`` gained an
``offset`` query param (``Query(0, ge=0, le=100000)``) passed through to
``GovernanceService.list_profiles``/``list_votes`` ``.offset()`` so clients
can page the bounded result set. No test exercised it — this pins the HTTP
surface end-to-end against the sqlite test database.

Coder: C
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from governance_service.main import app


@pytest.fixture
def client():
    """Same fixture shape as test_main.py — TestClient on the governance app."""
    return TestClient(app)


def _seed_profiles(test_database_path, prefix: str, n: int) -> list[str]:
    user_ids = [f"{prefix}_{i}" for i in range(n)]
    connection = sqlite3.connect(test_database_path)
    try:
        for i, uid in enumerate(user_ids):
            connection.execute(
                "INSERT INTO governance_profiles "
                "(profile_id, user_id, role, voting_power, delegated_power, "
                " total_votes_cast, proposals_created, proposals_passed, "
                " delegate_to, joined_at, last_voted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"{prefix}_prof_{i}",
                    uid,
                    # The column stores the enum NAME (GovernanceRole.MEMBER),
                    # not the StrEnum value — 'member' 500s on read.
                    "MEMBER",
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    "2026-11-10T00:00:00",
                    None,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return user_ids


def _cleanup(test_database_path, prefix: str) -> None:
    connection = sqlite3.connect(test_database_path)
    try:
        connection.execute("DELETE FROM governance_profiles WHERE profile_id LIKE ?", (f"{prefix}_%",))
        connection.commit()
    finally:
        connection.close()


class TestProfilesOffset:
    def test_offset_pages_the_bounded_result_set(self, client, test_database_path):
        prefix = "offpin"
        seeded = _seed_profiles(test_database_path, prefix, 5)
        try:
            page1 = client.get("/v1/governance/profiles", params={"limit": 100}).json()
            seeded_in_db = {p["user_id"] for p in page1 if p["user_id"].startswith(prefix)}
            assert seeded_in_db == set(seeded)

            # limit=2 pages: offsets 0/2/4 must partition the seeded rows —
            # offset actually skips rows rather than re-reading the head.
            pages = []
            for offset in (0, 2, 4):
                rows = client.get(
                    "/v1/governance/profiles",
                    params={"limit": 2, "offset": offset},
                ).json()
                pages.append({p["user_id"] for p in rows if p["user_id"].startswith(prefix)})

            flat = [uid for page in pages for uid in page]
            assert sorted(flat) == sorted(seeded)
            assert len(flat) == len(set(flat)) == 5
        finally:
            _cleanup(test_database_path, prefix)

    def test_offset_beyond_end_returns_empty(self, client, test_database_path):
        prefix = "offend"
        _seed_profiles(test_database_path, prefix, 2)
        try:
            rows = client.get(
                "/v1/governance/profiles",
                params={"limit": 10, "offset": 100000},
            ).json()
            assert [p for p in rows if p["user_id"].startswith(prefix)] == []
        finally:
            _cleanup(test_database_path, prefix)

    def test_offset_out_of_range_is_422(self, client):
        """The Query bound (0..100000) is part of the contract."""
        response = client.get("/v1/governance/profiles", params={"offset": 100001})
        assert response.status_code == 422
        response = client.get("/v1/governance/profiles", params={"offset": -1})
        assert response.status_code == 422
