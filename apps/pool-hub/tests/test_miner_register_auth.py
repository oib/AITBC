"""Pins for #1083 (re-registration auth) and #3059 (first-registration gate + recovery).

#1083: re-registering an existing miner_id requires its api key — pre-fix,
POST /v1/miners/register had no check at all, so anyone could overwrite
another miner's addr/price/payout wallet by reusing its miner_id.

#3059 (AUDIT-POOLHUB-MINER-SQUAT-1): first registration of any miner_id was
open to anyone — the submitted api key becomes the credential, and the
#1083 check then locks the id to whoever registered first. A squatter of a
predictable id owns it forever: no admin override, no ownership proof, no
recovery path. Post-fix: first registration requires the operator-issued
``registration_key`` (POOLHUB_MINER_REGISTRATION_KEY, fail-closed when
unconfigured), and DELETE /v1/miners/{miner_id} — gated by the pool-hub
operator key (X-PoolHub-Key) — is the recovery path for already-squatted
ids.
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from poolhub.app.routers import miners as miners_module
from poolhub.app.routers.miners import MinerRegisterRequest, deregister_miner, register_miner
from poolhub.app.routers.parameters import _governance_auth
from poolhub.database import get_session
from poolhub.redis_cache import get_redis
from poolhub.settings import settings

_REG_KEY = "operator-registration-key"


@pytest.fixture
def registration_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure POOLHUB_MINER_REGISTRATION_KEY for the duration of a test."""
    monkeypatch.setattr(settings, "miner_registration_key", _REG_KEY)


class _Session:
    def __init__(self, existing: object | None) -> None:
        self._existing = existing
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.delete = MagicMock()

    async def get(self, model: object, pk: str) -> object | None:
        return self._existing


def _request(miner_id: str = "m-1", api_key: str = "key-1", registration_key: str | None = None) -> MinerRegisterRequest:
    return MinerRegisterRequest(miner_id=miner_id, api_key=api_key, registration_key=registration_key)


def _miner(miner_id: str = "m-1", api_key_hash: str = "", region: str | None = None) -> MagicMock:
    miner = MagicMock()
    miner.miner_id = miner_id
    miner.api_key_hash = api_key_hash
    miner.region = region
    return miner


def _repo_mock() -> MagicMock:
    repo = MagicMock()
    repo.register_miner = AsyncMock(return_value=_miner())
    return repo


# ---------------------------------------------------------------- #1083 pins


@pytest.mark.asyncio
async def test_reregister_with_wrong_key_is_refused() -> None:
    existing = _miner(api_key_hash=hashlib.sha256(b"other-key").hexdigest())
    session = _Session(existing)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=_repo_mock()):
        with pytest.raises(HTTPException) as exc:
            await register_miner(_request(api_key="attacker-key"), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reregister_with_same_key_is_allowed() -> None:
    """#1083 preserved: same-key re-registration needs no registration_key —
    the stored api_key_hash is already the credential (#3059)."""
    existing = _miner(api_key_hash=hashlib.sha256(b"key-1").hexdigest())
    session = _Session(existing)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=_repo_mock()):
        result = await register_miner(_request(), session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True


# ------------------------------------------------- #3058 wallet-wipe pins

_STORED_WALLET = "0x" + "11" * 20
_NEW_WALLET = "0x" + "22" * 20


@pytest.mark.asyncio
async def test_reregister_without_wallet_preserves_stored_wallet() -> None:
    """#3058: a re-registration payload with no wallet_address must NOT
    overwrite the stored payout wallet with None — production miners were
    getting permanently no_wallet_address."""
    existing = _miner(api_key_hash=hashlib.sha256(b"key-1").hexdigest())
    stored = _miner()
    stored.wallet_address = _STORED_WALLET
    session = _Session(existing)
    repo = _repo_mock()
    repo.register_miner = AsyncMock(return_value=stored)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=repo):
        result = await register_miner(_request(), session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True
    assert stored.wallet_address == _STORED_WALLET


@pytest.mark.asyncio
async def test_reregister_with_wallet_updates_stored_wallet() -> None:
    """An explicit wallet_address still updates — miners can rotate wallets."""
    existing = _miner(api_key_hash=hashlib.sha256(b"key-1").hexdigest())
    stored = _miner()
    stored.wallet_address = _STORED_WALLET
    session = _Session(existing)
    repo = _repo_mock()
    repo.register_miner = AsyncMock(return_value=stored)
    req = MinerRegisterRequest(miner_id="m-1", api_key="key-1", wallet_address=_NEW_WALLET)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=repo):
        result = await register_miner(req, session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True
    assert stored.wallet_address == _NEW_WALLET


# ------------------------------------------------- #3059 first-registration pins


@pytest.mark.asyncio
async def test_first_registration_without_key_is_refused(registration_key: None) -> None:
    """The squatting defect: an arbitrary new miner_id with no proof must
    not bind the caller-chosen api_key as the credential."""
    session = _Session(None)
    repo = _repo_mock()
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=repo):
        with pytest.raises(HTTPException) as exc:
            await register_miner(_request(), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    repo.register_miner.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_registration_with_wrong_key_is_refused(registration_key: None) -> None:
    session = _Session(None)
    repo = _repo_mock()
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=repo):
        with pytest.raises(HTTPException) as exc:
            await register_miner(_request(registration_key="attacker-key"), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    repo.register_miner.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_registration_with_valid_key_is_allowed(registration_key: None) -> None:
    session = _Session(None)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=_repo_mock()):
        result = await register_miner(_request(registration_key=_REG_KEY), session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_first_registration_fails_closed_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No POOLHUB_MINER_REGISTRATION_KEY configured -> 503, not open
    registration: an unprovisioned deployment must not silently re-open
    the squatting hole."""
    monkeypatch.setattr(settings, "miner_registration_key", "")
    session = _Session(None)
    repo = _repo_mock()
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=repo):
        with pytest.raises(HTTPException) as exc:
            await register_miner(_request(registration_key="anything"), session, MagicMock())  # type: ignore[arg-type]
    assert exc.value.status_code == 503
    repo.register_miner.assert_not_awaited()


# ------------------------------------------------- #3059 recovery-path pins


class _DeleteSession:
    """AsyncSession stand-in for deregister_miner."""

    def __init__(self, miner: object | None) -> None:
        self._miner = miner
        self.deleted: list[object] = []
        self.commits = 0
        self.delete = AsyncMock(side_effect=self.deleted.append)

    async def get(self, model: object, pk: str) -> object | None:
        return self._miner

    async def commit(self) -> None:
        self.commits += 1


def _redis_mock() -> MagicMock:
    redis = MagicMock()
    redis.delete = AsyncMock()
    redis.zrem = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_deregister_removes_row_and_redis_copies() -> None:
    miner = _miner(miner_id="node2-gpu-01", region="eu-1")
    session = _DeleteSession(miner)
    redis = _redis_mock()
    result = await deregister_miner("node2-gpu-01", session, redis, {"role": "operator"})  # type: ignore[arg-type]
    assert result == {"success": True, "miner_id": "node2-gpu-01", "deleted": True}
    assert session.deleted == [miner]
    assert session.commits == 1
    redis.delete.assert_awaited_once()
    # region ranking + global ranking both cleaned
    assert redis.zrem.await_count == 2


@pytest.mark.asyncio
async def test_deregister_unknown_miner_is_404() -> None:
    session = _DeleteSession(None)
    redis = _redis_mock()
    with pytest.raises(HTTPException) as exc:
        await deregister_miner("ghost", session, redis, {"role": "operator"})  # type: ignore[arg-type]
    assert exc.value.status_code == 404
    assert session.commits == 0


def _miners_client(session: Any, redis: Any) -> TestClient:
    """Mount just the miners router so the operator-auth wiring is exercised."""
    app = FastAPI()
    app.include_router(miners_module.router, prefix="/v1")

    async def _db() -> Any:
        yield session

    async def _r() -> Any:
        yield redis

    app.dependency_overrides[get_session] = _db
    app.dependency_overrides[get_redis] = _r
    return TestClient(app)


def test_deregister_route_rejects_missing_operator_key() -> None:
    client = _miners_client(_DeleteSession(_miner()), _redis_mock())
    assert client.delete("/v1/miners/node2-gpu-01").status_code == 401


def test_deregister_route_rejects_wrong_operator_key() -> None:
    client = _miners_client(_DeleteSession(_miner()), _redis_mock())
    resp = client.delete("/v1/miners/node2-gpu-01", headers={"X-PoolHub-Key": "attacker-key"})
    assert resp.status_code == 401


def test_deregister_route_allows_operator_key() -> None:
    """Control: the configured operator key passes auth (same secret class as
    /v1/parameters/apply — conftest sets POOLHUB_COORDINATOR_SHARED_SECRET)."""
    client = _miners_client(_DeleteSession(_miner()), _redis_mock())
    resp = client.delete(
        "/v1/miners/node2-gpu-01",
        headers={"X-PoolHub-Key": _governance_auth.expected_key or ""},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


# ------------------------------------------------------------- #1570 pins (unchanged)


class TestWalletAddressValidation:
    """#1570: wallet_address becomes the payout tx `to` verbatim — it must
    be 0x + 40 hex chars (any case) or absent, never stored garbage."""

    @pytest.mark.parametrize(
        "bad",
        [
            "not-an-address",
            "0x1234",
            "0x" + "g" * 40,
            "0x" + "a" * 39,
            "0x" + "a" * 41,
            "1234567890abcdef1234567890abcdef12345678",  # missing 0x
        ],
    )
    def test_malformed_wallet_address_rejected(self, bad: str) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MinerRegisterRequest(miner_id="m-1", api_key="k", wallet_address=bad)

    @pytest.mark.parametrize(
        "good",
        [
            "0x" + "a" * 40,
            "0x" + "A" * 40,
            "0x" + "aB3" * 13 + "a",  # mixed case, 40 hex chars
        ],
    )
    def test_valid_wallet_address_accepted(self, good: str) -> None:
        req = MinerRegisterRequest(miner_id="m-1", api_key="k", wallet_address=good)
        assert req.wallet_address == good

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_blank_wallet_address_means_unset(self, empty: str | None) -> None:
        req = MinerRegisterRequest(miner_id="m-1", api_key="k", wallet_address=empty)
        assert req.wallet_address is None
