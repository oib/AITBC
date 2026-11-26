"""#3022 AUTHZ-MINER-KEY-IMPERSONATION-1 pins.

Fleet audit (documented on the issue): hub coordinator-api provisions a
single shared ``MINER_API_KEYS`` entry and NO ``MINER_API_KEY_BINDINGS``;
node2's miner presents that key with ``X-Miner-ID: aitbc-miner-1``. Every
key was unbound, so the caller-asserted header won — one shared key could
act as ANY miner id on all ``/v1/miners/*`` + MINER routes.

Fix: an unbound key may not assert ``X-Miner-ID`` at all — it resolves
to the stable derived ``miner_<sha256>`` identity, or is refused (403 at
the dependency, 401 through AuthMiddleware) when it claims one. Bound
keys are unchanged.
"""

import hashlib

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from typing import Annotated

from aitbc.auth.dependencies import require_miner_api_key

KEY = "impersonation-test-key-32-chars"
OTHER_KEY = "other-miner-key-32-chars-xx"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: Annotated[dict, Depends(require_miner_api_key)]) -> dict:
        return user

    return app


def _keys(monkeypatch, bindings: str | None) -> None:
    monkeypatch.setenv("MINER_API_KEYS", f"{KEY},{OTHER_KEY}")
    if bindings is None:
        monkeypatch.delenv("MINER_API_KEY_BINDINGS", raising=False)
    else:
        monkeypatch.setenv("MINER_API_KEY_BINDINGS", bindings)


def test_unbound_key_cannot_assert_miner_id(monkeypatch) -> None:
    """Headline: shared key + foreign X-Miner-ID is refused, not honoured."""
    _keys(monkeypatch, None)  # no bindings configured at all — the fleet shape
    client = TestClient(_app())

    resp = client.get("/whoami", headers={"X-Api-Key": KEY, "X-Miner-ID": "aitbc-miner-1"})
    assert resp.status_code == 403
    assert "MINER_API_KEY_BINDINGS" in resp.json()["detail"]


def test_unbound_key_without_header_derives_stable_id(monkeypatch) -> None:
    """Dropping the header still works — the derived id is the identity."""
    _keys(monkeypatch, None)
    client = TestClient(_app())

    resp = client.get("/whoami", headers={"X-Api-Key": KEY})
    assert resp.status_code == 200
    expected = f"miner_{hashlib.sha256(KEY.encode()).hexdigest()[:16]}"
    assert resp.json()["sub"] == expected
    assert resp.json()["role"] == "miner"


def test_unbound_key_empty_miner_id_header_derives(monkeypatch) -> None:
    """A blank X-Miner-ID is not an identity claim — derived id, not 403."""
    _keys(monkeypatch, None)
    client = TestClient(_app())

    resp = client.get("/whoami", headers={"X-Api-Key": KEY, "X-Miner-ID": "   "})
    assert resp.status_code == 200
    assert resp.json()["sub"].startswith("miner_")


def test_bound_key_still_honours_matching_miner_id(monkeypatch) -> None:
    """Control: the bound path is unchanged — match works, mismatch 403s."""
    _keys(monkeypatch, f'{{"{KEY}": "aitbc-miner-1"}}')
    client = TestClient(_app())

    ok = client.get("/whoami", headers={"X-Api-Key": KEY, "X-Miner-ID": "aitbc-miner-1"})
    assert ok.status_code == 200 and ok.json()["sub"] == "aitbc-miner-1"

    bad = client.get("/whoami", headers={"X-Api-Key": KEY, "X-Miner-ID": "other-miner"})
    assert bad.status_code == 403

    # A *different* key stays unbound — its assertion is refused even though
    # bindings exist for someone else.
    foreign = client.get("/whoami", headers={"X-Api-Key": OTHER_KEY, "X-Miner-ID": "aitbc-miner-1"})
    assert foreign.status_code == 403


def test_bound_key_without_header_uses_bound_id(monkeypatch) -> None:
    _keys(monkeypatch, f"{KEY}=aitbc-miner-1")  # pair syntax also parses
    client = TestClient(_app())

    resp = client.get("/whoami", headers={"X-Api-Key": KEY})
    assert resp.status_code == 200 and resp.json()["sub"] == "aitbc-miner-1"
