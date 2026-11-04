"""Pin for #1083: re-registering an existing miner_id requires its api key.

Pre-fix, POST /v1/miners/register had no check at all — anyone could
overwrite another miner's addr/price/payout wallet by reusing its
miner_id (the api_key_hash was never updated, so the real owner was
hijacked silently). Post-fix: a hash mismatch on an existing row raises
403; a matching key re-registers normally; a new miner_id registers
openly.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from poolhub.app.routers.miners import MinerRegisterRequest, register_miner


class _Session:
    def __init__(self, existing: object | None) -> None:
        self._existing = existing
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def get(self, model: object, pk: str) -> object | None:
        return self._existing


def _request(miner_id: str = "m-1", api_key: str = "key-1") -> MinerRegisterRequest:
    return MinerRegisterRequest(miner_id=miner_id, api_key=api_key)


def _miner(miner_id: str = "m-1", api_key_hash: str = "") -> MagicMock:
    miner = MagicMock()
    miner.miner_id = miner_id
    miner.api_key_hash = api_key_hash
    return miner


def _repo_mock() -> MagicMock:
    repo = MagicMock()
    repo.register_miner = AsyncMock(return_value=_miner())
    return repo


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
    existing = _miner(api_key_hash=hashlib.sha256(b"key-1").hexdigest())
    session = _Session(existing)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=_repo_mock()):
        result = await register_miner(_request(), session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_first_registration_is_open() -> None:
    session = _Session(None)
    with patch("poolhub.app.routers.miners.MinerRepository", return_value=_repo_mock()):
        result = await register_miner(_request(), session, MagicMock())  # type: ignore[arg-type]
    assert result["success"] is True
