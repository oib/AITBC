"""#2365: provider billing-report POST helper in aitbc.shop_gate.

The shop daemons call ``report_job_billing``/``report_request_billing`` once
the served usage is known. The report must carry the job's access triple as
headers and ``{"metrics": ..., "final": ...}`` as the body, must never raise
into the paid-work path, and must report failure (False) on transport or
HTTP errors so the caller can degrade to full-lock settlement.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import aitbc.shop_gate as shop_gate


class _Resp:
    def __init__(self, status_code: int = 200, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text


def _client(post: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(post=post)


@pytest.mark.asyncio
async def test_report_job_billing_posts_triple_and_metrics() -> None:
    post = AsyncMock(return_value=_Resp(200))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
    ):
        ok = await shop_gate.report_job_billing(
            job_id="job-1",
            access_key="key-1",
            access_secret="secret-1",
            metrics={"eval_count": 123},
            final=True,
        )
    assert ok is True
    args, kwargs = post.call_args
    assert args[0] == "http://market.test/v1/market/jobs/job-1/billing"
    assert kwargs["headers"] == {
        "X-Access-Key": "key-1",
        "X-Access-Secret": "secret-1",
        "X-Job-Id": "job-1",
    }
    assert kwargs["json"] == {"metrics": {"eval_count": 123}, "final": True}


@pytest.mark.asyncio
async def test_report_job_billing_never_raises_on_transport_error() -> None:
    import httpx

    post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
    ):
        assert (
            await shop_gate.report_job_billing(job_id="job-1", access_key="k", access_secret="s", metrics={"eval_count": 1})
            is False
        )


@pytest.mark.asyncio
async def test_report_job_billing_false_on_http_error() -> None:
    post = AsyncMock(return_value=_Resp(403, "forbidden"))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
    ):
        assert (
            await shop_gate.report_job_billing(job_id="job-1", access_key="k", access_secret="s", metrics={"eval_count": 1})
            is False
        )


@pytest.mark.asyncio
async def test_report_job_billing_skips_empty_credentials() -> None:
    post = AsyncMock()
    with patch.object(shop_gate, "_verify_client", return_value=_client(post)):
        assert (
            await shop_gate.report_job_billing(job_id="", access_key="", access_secret="", metrics={"eval_count": 1}) is False
        )
        assert await shop_gate.report_job_billing(job_id="job-1", access_key="k", access_secret="s", metrics={}) is False
    post.assert_not_called()


@pytest.mark.asyncio
async def test_report_request_billing_reads_headers() -> None:
    post = AsyncMock(return_value=_Resp(200))
    request = SimpleNamespace(
        headers={
            "X-Access-Key": "key-9",
            "X-Access-Secret": "secret-9",
            "X-Job-Id": "job-9",
        }
    )
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
    ):
        ok = await shop_gate.report_request_billing(request, {"duration_minutes": 2.5})
    assert ok is True
    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Job-Id"] == "job-9"
    assert kwargs["json"] == {"metrics": {"duration_minutes": 2.5}, "final": True}
