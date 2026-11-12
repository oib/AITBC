"""IPFS-DEPTH-1 (#1582): CID-arg sanitization, ownership-scoped unpin, and
upload/pin bounds on the coordinator-api IPFS service.

The shared Kubo node holds pins owned by many tenants; these tests pin the
invariants that keep ``/v1/ipfs*`` from being a cross-tenant destruction or
resource-exhaustion primitive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from coordinator_api.contexts.ipfs.services.ipfs_service import (
    IPFSService,
    IPFSUploadResult,
    _validate_cid_arg,
)


def _streamable(resp: object) -> object:
    """Give a fake response the streaming surface get_content now uses."""
    if not hasattr(resp, "headers"):
        resp.headers = {}  # type: ignore[attr-defined]
    if not hasattr(resp, "aiter_bytes"):
        content = getattr(resp, "content", b"")

        async def _aiter() -> object:
            yield content

        resp.aiter_bytes = _aiter  # type: ignore[attr-defined]
    return resp


class _StubClient:
    """Minimal stand-in for httpx.AsyncClient used by IPFSClient."""

    def __init__(self, post=None, get=None) -> None:  # noqa: ANN001
        self._post = post
        self._get = get

    async def post(self, url: str, **kwargs: object):  # noqa: ANN202
        assert self._post is not None
        return await self._post(url, **kwargs)

    async def get(self, url: str, **kwargs: object):  # noqa: ANN202
        assert self._get is not None
        return await self._get(url, **kwargs)

    def stream(self, method: str, url: str, **kwargs: object):  # noqa: ANN202
        """httpx-style streaming context manager over the same fakes."""
        fake = self._post if method == "POST" else self._get
        assert fake is not None

        class _CM:
            async def __aenter__(self) -> object:
                return _streamable(await fake(url, **kwargs))

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _CM()


def _service(**config: object) -> IPFSService:
    svc = IPFSService({"ipfs_url": "http://127.0.0.1:5001", **config})
    svc.client.check_availability = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return svc


def _upload_result(cid: str = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi") -> IPFSUploadResult:
    return IPFSUploadResult(
        cid=cid,
        size=1,
        name="mem",
        timestamp=datetime.now(UTC),
        gateway_url=f"https://ipfs.io/ipfs/{cid}",
        pinned=True,
    )


class TestCidArgValidation:
    @pytest.mark.parametrize("bad", ["ipfs/Qmabc", "/ipfs/Qmabc", "..", "a/b", "a b", "ipfs://Qmabc", ""])
    def test_rejects_ipfs_paths_and_separators(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _validate_cid_arg(bad)

    @pytest.mark.parametrize("good", ["Qm" + "a" * 44, "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"])
    def test_accepts_bare_cids(self, good: str) -> None:
        assert _validate_cid_arg(good) == good

    async def test_pin_cid_rejects_path_arg(self) -> None:
        svc = _service()
        with pytest.raises(ValueError):
            await svc.client.pin_cid("ipfs/whatever")

    async def test_unpin_cid_rejects_path_arg(self) -> None:
        svc = _service()
        with pytest.raises(ValueError):
            await svc.client.unpin_cid("/ipfs/whatever")


class TestOwnershipScopedUnpin:
    async def test_foreign_cid_is_never_unpinned(self) -> None:
        """A CID the service never uploaded must not reach pin/rm."""
        svc = _service()
        svc.client.unpin_cid = AsyncMock(return_value=True)  # type: ignore[method-assign]
        foreign = "Qm" + "z" * 44
        assert await svc.delete_memory(foreign) is False
        svc.client.unpin_cid.assert_not_called()

    async def test_owned_memory_cid_is_unpinned(self) -> None:
        svc = _service()
        cid = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"
        svc.client.upload_file = AsyncMock(return_value=_upload_result(cid))  # type: ignore[method-assign]
        svc.client.unpin_cid = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await svc.upload_memory(agent_id="agent-1", memory_data={"k": "v"}, pin=True)
        assert await svc.delete_memory(cid) is True
        svc.client.unpin_cid.assert_awaited_once_with(cid)

    async def test_owned_job_result_cid_is_unpinned(self) -> None:
        svc = _service()
        cid = "Qm" + "y" * 44
        svc.client.upload_file = AsyncMock(return_value=_upload_result(cid))  # type: ignore[method-assign]
        svc.client.unpin_cid = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await svc.store_job_result("job-1", {"result": 1})
        assert await svc.delete_memory(cid) is True


class TestUploadBounds:
    async def test_memory_size_cap(self) -> None:
        svc = _service(ipfs_max_memory_bytes=1024)
        svc.client.upload_file = AsyncMock()  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="exceeding"):
            await svc.upload_memory(agent_id="a", memory_data={"blob": "x" * 5000})
        svc.client.upload_file.assert_not_called()

    async def test_batch_count_cap(self) -> None:
        svc = _service(ipfs_max_batch_memories=3)
        with pytest.raises(ValueError, match="cap"):
            await svc.batch_upload_memories(
                agent_id="a",
                memories=[({}, "t", [])] * 4,
            )

    async def test_registry_is_bounded_lru(self) -> None:
        svc = _service(ipfs_registry_max=3)
        cids = [f"bafy{i:027d}" for i in range(6)]
        results = [_upload_result(c) for c in cids]
        svc.client.upload_file = AsyncMock(side_effect=results)  # type: ignore[method-assign]
        for _ in range(6):
            await svc.upload_memory(agent_id="a", memory_data={"k": "v"})
        assert len(svc._memories) == 3
        # oldest entries evicted
        assert cids[0] not in svc._memories
        assert cids[-1] in svc._memories


class TestRetrieveViaLocalCat:
    async def test_get_content_uses_local_api_not_public_gateway(self) -> None:
        """Default path must not leak the CID to ipfs.io (#1582)."""
        svc = _service()
        posted: list[str] = []

        class _Resp:
            status_code = 200
            content = b"{}"

        async def fake_post(url: str, **kwargs: object) -> _Resp:
            posted.append(url)
            return _Resp()

        svc.client._client = _StubClient(post=fake_post)  # type: ignore[assignment]
        got = await svc.client.get_content("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi")
        assert got == b"{}"
        assert posted and posted[0].endswith("/api/v0/cat")
        assert "ipfs.io" not in posted[0]

    async def test_get_content_refuses_declared_oversize(self) -> None:
        """#1932 F2: a Content-Length over the cap is refused before reading."""
        svc = _service()

        class _Resp:
            status_code = 200
            headers = {"Content-Length": "2048"}
            content = b"x" * 2048

        async def fake_post(url: str, **kwargs: object) -> _Resp:
            return _Resp()

        svc.client._client = _StubClient(post=fake_post)  # type: ignore[assignment]
        with pytest.raises(ValueError, match="cap"):
            await svc.client.get_content("Qm" + "a" * 44, max_bytes=1024)

    async def test_get_content_refuses_streamed_oversize(self) -> None:
        """#1932 F2: chunked bodies without Content-Length are still capped."""
        svc = _service()

        class _Resp:
            status_code = 200
            headers: dict[str, str] = {}

            async def aiter_bytes(self):
                yield b"x" * 700
                yield b"x" * 700

        async def fake_post(url: str, **kwargs: object) -> _Resp:
            return _Resp()

        svc.client._client = _StubClient(post=fake_post)  # type: ignore[assignment]
        with pytest.raises(ValueError, match="cap"):
            await svc.client.get_content("Qm" + "a" * 44, max_bytes=1024)

    async def test_gateway_fallback_is_opt_in(self) -> None:
        svc = _service(ipfs_public_gateway_fallback=True)
        calls: list[str] = []

        class _Resp:
            def __init__(self, code: int) -> None:
                self.status_code = code
                self.content = b"gw"

        async def fake_post(url: str, **kwargs: object) -> _Resp:
            calls.append(url)
            return _Resp(500)

        async def fake_get(url: str, **kwargs: object) -> _Resp:
            calls.append(url)
            return _Resp(200)

        svc.client._client = _StubClient(post=fake_post, get=fake_get)  # type: ignore[assignment]
        got = await svc.client.get_content("Qm" + "a" * 44)
        assert got == b"gw"
        assert any("ipfs.io" in c for c in calls)


class TestMemoryPinDefault:
    async def test_memory_upload_pins_by_default(self) -> None:
        """#1713: island daemon runs --enable-gc; default must be pin=True."""
        svc = _service()
        svc.client.upload_file = AsyncMock(return_value=_upload_result())  # type: ignore[method-assign]
        result = await svc.upload_memory(agent_id="a", memory_data={"k": "v"})
        assert result.pinned is True
        assert svc.client.upload_file.call_args.kwargs["pin"] is True

    async def test_explicit_unpinned_still_allowed(self) -> None:
        svc = _service()
        svc.client.upload_file = AsyncMock(return_value=_upload_result())  # type: ignore[method-assign]
        result = await svc.upload_memory(agent_id="a", memory_data={"k": "v"}, pin=False)
        assert result.pinned is False
        assert svc.client.upload_file.call_args.kwargs["pin"] is False
