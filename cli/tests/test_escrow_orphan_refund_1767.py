"""HERMES-ESCROW-SIGKILL-1 (#1767): provider-call failure after escrow lock
must attempt a buyer refund instead of stranding the on-chain escrow.

``sw_job_*`` escrows have no market/coordinator job row, so no sweeper ever
reclaims them — the CLI is the only place that can refund inline.
"""

from types import SimpleNamespace
from typing import Any, cast

import click
import pytest

import aitbc_cli.commands.market.jobs as jobs_mod


def _ctx() -> click.Context:
    return cast(click.Context, SimpleNamespace(obj={}))


def _config() -> Any:
    return SimpleNamespace(
        hub_proposer_id="0xPROP",
        blockchain_rpc_api_key=None,
        hub_discovery_url="https://hub.aitbc.bubuit.net",
        blockchain_rpc_url="http://127.0.0.1:8202",
        coordinator_api_url=None,
    )


def _offer(service_type: str = "hermes") -> dict[str, Any]:
    return {
        "service_type": service_type,
        "model": "m",
        "price": "1",
        "price_unit": "per_minute",
        "provider_address": "0xP",
        "offer_id": "o1",
        "public_endpoint": "http://127.0.0.1:8270",
    }


@pytest.fixture
def escrow_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Stub escrow create + capture refund_escrow calls."""
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(jobs_mod, "get_config", _config)
    monkeypatch.setattr(jobs_mod, "get_chain_id", lambda: "bc-2")
    monkeypatch.setattr(jobs_mod, "_escrow_create", lambda *a, **kw: "contract-1")

    def _refund(ctx: Any, job_id: str, reason: str) -> dict[str, Any]:
        calls.append((job_id, reason, "ok"))
        return {"refunded": True}

    monkeypatch.setattr(jobs_mod, "refund_escrow", _refund)
    return calls


def test_refund_helper_noops_without_contract(escrow_spy: list[Any]) -> None:
    jobs_mod._refund_orphaned_escrow(_ctx(), "sw_job_x", None)
    jobs_mod._refund_orphaned_escrow(_ctx(), "sw_job_x", "")
    assert escrow_spy == []


def test_refund_helper_swallows_abort(escrow_spy: list[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def _abort(ctx: Any, job_id: str, reason: str) -> None:
        raise click.Abort()

    monkeypatch.setattr(jobs_mod, "refund_escrow", _abort)
    jobs_mod._refund_orphaned_escrow(_ctx(), "sw_job_x", "contract-1")  # must not raise


def test_hermes_post_failure_refunds(escrow_spy: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            raise ConnectionResetError("provider SIGKILLed")

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(ConnectionResetError):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(escrow_spy) == 1
    assert escrow_spy[0][1] == "job_failed"


def test_hermes_noncompleted_status_refunds(escrow_spy: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {"status": "failed", "text": "boom"}

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(click.Abort):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(escrow_spy) == 1


def test_ollama_failure_refunds(escrow_spy: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    def _boom(req: Any, timeout: int = 0) -> Any:
        raise TimeoutError("provider gone")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    offer = _offer("ollama")
    offer["price_unit"] = "per_1k_tokens"
    with pytest.raises(TimeoutError):
        jobs_mod._run_ollama(_ctx(), offer, "prompt", "0xB", "dead", 512, False, "json")
    assert len(escrow_spy) == 1
    assert escrow_spy[0][1] == "job_failed"
