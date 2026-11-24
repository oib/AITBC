"""AUDIT-EDGE pins: #2911 memory cross-tenant defects.

1. Re-store/retrieve used to answer the FIRST storer's owner identity —
   tenant B learned tenant A's owner string. Responses now name the caller.
2. _evict_lru picked the global LRU record regardless of owner — any
   caller could force eviction of a victim tenant's blob. Eviction is now
   caller-namespace only; a full store of other tenants' blobs refuses
   the write instead of destroying their data.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from memory_app import api as api_module
from memory_app.config import settings
from memory_app.main import app


_XT_OWNERS = {"xt-owner-a", "xt-owner-b", "xt-victim", "xt-intruder", "xt-other", "xt-self"}


@pytest.fixture(autouse=True)
def _cleanup_xt_records():
    """The store is shared across the suite — leave no xt-* records behind
    or later byte-cap tests inherit our heap."""
    yield
    for cid in [c for c, r in api_module.store._store.items() if (r.get("owners") or set()) & _XT_OWNERS]:
        api_module.store._drop(cid)


def _reset_store(owners: set[str]) -> None:
    """Drop records outside the test's owner set — the store is shared
    across the suite, so byte-cap assertions need a deterministic heap."""
    for cid in [c for c, r in api_module.store._store.items() if not (r.get("owners") or set()) & owners]:
        api_module.store._drop(cid)


def _store(client, owner, payload, tags=None):
    resp = client.post(
        "/v1/store",
        json={"owner": owner, "data": base64.b64encode(payload).decode("ascii"), "tags": tags or {}},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.unit
def test_restore_does_not_disclose_first_owner() -> None:
    client = TestClient(app)
    data = base64.b64encode(b"cross-tenant shared").decode("ascii")
    first = client.post("/v1/store", json={"owner": "xt-owner-a", "data": data, "tags": {}})
    assert first.status_code == 201
    second = client.post("/v1/store", json={"owner": "xt-owner-b", "data": data, "tags": {}})
    assert second.status_code == 201
    assert second.json()["owner"] == "xt-owner-b", "re-store must answer the caller, not the first storer"
    cid = first.json()["content_address"]
    for caller in ("xt-owner-a", "xt-owner-b"):
        resp = client.get(f"/v1/retrieve/{cid}", params={"owner": caller})
        assert resp.status_code == 200
        assert resp.json()["owner"] == caller


@pytest.mark.unit
def test_caller_cannot_evict_victim_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """A store full of tenant A's blobs refuses tenant B's write (507)
    instead of LRU-evicting A's data."""
    client = TestClient(app)
    _reset_store({"xt-victim", "xt-intruder"})
    monkeypatch.setattr(settings, "memory_max_total_bytes", 400)
    victim = _store(client, "xt-victim", b"v" * 150)
    # Fill remaining headroom with the victim's own second blob.
    _store(client, "xt-victim", b"w" * 150)
    intruder = client.post(
        "/v1/store",
        json={"owner": "xt-intruder", "data": base64.b64encode(b"i" * 150).decode("ascii"), "tags": {}},
    )
    assert intruder.status_code == 507, intruder.text
    # Victim data untouched.
    resp = client.get(f"/v1/retrieve/{victim['content_address']}", params={"owner": "xt-victim"})
    assert resp.status_code == 200


@pytest.mark.unit
def test_caller_evicts_own_namespace_not_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under pressure the caller's own LRU records go first; other tenants'
    blobs survive even when the caller still has evictable records."""
    client = TestClient(app)
    _reset_store({"xt-other", "xt-self"})
    monkeypatch.setattr(settings, "memory_max_total_bytes", 500)
    other = _store(client, "xt-other", b"o" * 200)
    mine_old = _store(client, "xt-self", b"m" * 100)
    # Deterministically make mine_old the caller's LRU victim.
    api_module.store._store[mine_old["content_address"]]["last_accessed"] = datetime(2000, 1, 1, tzinfo=UTC)
    _store(client, "xt-self", b"n" * 100)
    # One more self write forces eviction inside the self namespace only.
    third = _store(client, "xt-self", b"p" * 120)
    assert third["content_address"]
    gone = client.get(f"/v1/retrieve/{mine_old['content_address']}", params={"owner": "xt-self"})
    assert gone.status_code == 404, "caller's own LRU record should be evicted"
    alive = client.get(f"/v1/retrieve/{other['content_address']}", params={"owner": "xt-other"})
    assert alive.status_code == 200, "another tenant's blob must survive"
