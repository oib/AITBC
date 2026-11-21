"""#2365: provider billing-report POST helper in aitbc.shop_gate.

The shop daemons call ``report_job_billing``/``report_request_billing`` once
the served usage is known. The report must carry the job's access triple as
headers, ``{"metrics": ..., "final": ...}`` as the body, and the provider
wallet signature fields (``signer_address``/``chain_id``/``issued_at``/
``signature``) that authorize it server-side — the buyer-held access token
alone must never attest the provider's usage. The helper must never raise
into the paid-work path, and must report failure (False) on missing signing
material, transport, or HTTP errors so the caller degrades to full-lock
settlement.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import aitbc.shop_gate as shop_gate

_SIGNED = {
    "signer_address": "0xProvider",
    "chain_id": "bc-test",
    "issued_at": 1700000000,
    "signature": "0xsig",
}


class _Resp:
    def __init__(self, status_code: int = 200, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text


def _client(post: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(post=post)


@pytest.mark.asyncio
async def test_report_job_billing_posts_triple_metrics_and_signature() -> None:
    post = AsyncMock(return_value=_Resp(200))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
        patch.object(shop_gate, "_billing_signature", return_value=dict(_SIGNED)) as sign,
    ):
        ok = await shop_gate.report_job_billing(
            job_id="job-1",
            access_key="key-1",
            access_secret="secret-1",
            provider_address="0xProvider",
            metrics={"eval_count": 123},
            final=True,
        )
    assert ok is True
    # The signature binds the exact route + metrics + final flag.
    sign.assert_called_once_with("0xProvider", "job-1", {"eval_count": 123}, True)
    args, kwargs = post.call_args
    assert args[0] == "http://market.test/v1/market/jobs/job-1/billing"
    assert kwargs["headers"] == {
        "X-Access-Key": "key-1",
        "X-Access-Secret": "secret-1",
        "X-Job-Id": "job-1",
    }
    assert kwargs["json"] == {"metrics": {"eval_count": 123}, "final": True, **_SIGNED}


@pytest.mark.asyncio
async def test_report_job_billing_skips_without_provider_address() -> None:
    """No provider address -> no signature -> no POST (buyer token cannot attest)."""
    post = AsyncMock()
    with patch.object(shop_gate, "_verify_client", return_value=_client(post)):
        assert (
            await shop_gate.report_job_billing(
                job_id="job-1", access_key="k", access_secret="s", provider_address=None, metrics={"eval_count": 1}
            )
            is False
        )
    post.assert_not_called()


@pytest.mark.asyncio
async def test_report_job_billing_skips_when_signing_material_missing() -> None:
    """No provider wallet key / chain id on this host -> unsigned report never sent."""
    post = AsyncMock()
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "_provider_signing_key", return_value=None),
        patch.object(shop_gate, "_chain_id", return_value="bc-test"),
    ):
        assert (
            await shop_gate.report_job_billing(
                job_id="job-1",
                access_key="k",
                access_secret="s",
                provider_address="0xProvider",
                metrics={"eval_count": 1},
            )
            is False
        )
    post.assert_not_called()


@pytest.mark.asyncio
async def test_report_job_billing_never_raises_on_transport_error() -> None:
    import httpx

    post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
        patch.object(shop_gate, "_billing_signature", return_value=dict(_SIGNED)),
    ):
        assert (
            await shop_gate.report_job_billing(
                job_id="job-1",
                access_key="k",
                access_secret="s",
                provider_address="0xProvider",
                metrics={"eval_count": 1},
            )
            is False
        )


@pytest.mark.asyncio
async def test_report_job_billing_false_on_http_error() -> None:
    post = AsyncMock(return_value=_Resp(403, "forbidden"))
    with (
        patch.object(shop_gate, "_verify_client", return_value=_client(post)),
        patch.object(shop_gate, "MARKET_VERIFY_URL", "http://market.test"),
        patch.object(shop_gate, "_billing_signature", return_value=dict(_SIGNED)),
    ):
        assert (
            await shop_gate.report_job_billing(
                job_id="job-1",
                access_key="k",
                access_secret="s",
                provider_address="0xProvider",
                metrics={"eval_count": 1},
            )
            is False
        )


@pytest.mark.asyncio
async def test_report_job_billing_skips_empty_credentials() -> None:
    post = AsyncMock()
    with patch.object(shop_gate, "_verify_client", return_value=_client(post)):
        assert (
            await shop_gate.report_job_billing(
                job_id="", access_key="", access_secret="", provider_address="0xP", metrics={"eval_count": 1}
            )
            is False
        )
        assert (
            await shop_gate.report_job_billing(
                job_id="job-1", access_key="k", access_secret="s", provider_address="0xP", metrics={}
            )
            is False
        )
    post.assert_not_called()


@pytest.mark.asyncio
async def test_report_request_billing_reads_headers_and_provider() -> None:
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
        patch.object(shop_gate, "_billing_signature", return_value=dict(_SIGNED)),
    ):
        ok = await shop_gate.report_request_billing(request, {"duration_minutes": 2.5}, provider_address="0xProvider9")
    assert ok is True
    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Job-Id"] == "job-9"
    assert kwargs["json"]["metrics"] == {"duration_minutes": 2.5}
    assert kwargs["json"]["signer_address"] == "0xProvider"


# --- _billing_signature: real signing path ---------------------------------


def test_billing_signature_signs_with_provider_wallet_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: wallet JSON in the wallet dir -> signature verifies against
    the provider address for the exact route + binding, and fails for a
    tampered binding (the market rebuilds it from the submitted body)."""
    from aitbc.crypto.crypto import derive_ethereum_address, recover_signer
    from aitbc.market.job_request_signature import jobs_request_message

    private_key = "0x" + "77" * 32
    address = derive_ethereum_address(private_key)
    wallet = tmp_path / "provider.json"
    wallet.write_text(json.dumps({"address": address, "private_key": private_key}))
    (tmp_path / "other.json").write_text(json.dumps({"address": "0x" + "00" * 20, "private_key": "0x" + "11" * 32}))

    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    monkeypatch.setenv("CHAIN_ID", "bc-test")
    monkeypatch.delenv("AITBC_CHAIN_ID", raising=False)

    signed = shop_gate._billing_signature(address, "job-S1", {"eval_count": 42}, True)
    assert signed is not None
    assert signed["signer_address"] == address
    assert signed["chain_id"] == "bc-test"

    route = "/v1/market/jobs/job-S1/billing"
    binding = {"metrics": {"eval_count": 42}, "final": True}
    message = jobs_request_message(address, "bc-test", signed["issued_at"], route, binding=binding)
    assert recover_signer(message, signed["signature"]) is not None

    tampered = jobs_request_message(
        address, "bc-test", signed["issued_at"], route, binding={"metrics": {"eval_count": 1}, "final": True}
    )
    assert recover_signer(tampered, signed["signature"]) != address


def test_billing_signature_none_without_wallet_or_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))  # empty dir
    monkeypatch.setenv("CHAIN_ID", "bc-test")
    assert shop_gate._billing_signature("0x" + "22" * 20, "job-1", {"eval_count": 1}, True) is None

    from aitbc.crypto.crypto import derive_ethereum_address

    private_key = "0x" + "77" * 32
    address = derive_ethereum_address(private_key)
    (tmp_path / "w.json").write_text(json.dumps({"address": address, "private_key": private_key}))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.delenv("AITBC_CHAIN_ID", raising=False)
    assert shop_gate._billing_signature(address, "job-1", {"eval_count": 1}, True) is None
