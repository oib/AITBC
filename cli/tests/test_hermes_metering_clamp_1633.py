"""HERMES-IPFS-DEPTH2-1 (#1633) + #2365: shop-reported duration_minutes is
clamped to [0, max_time] before billing, and metered escrow is never
released buyer-side — the provider's attested report settles it.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import click

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


def _offer() -> dict[str, Any]:
    return {
        "service_type": "hermes",
        "model": "m",
        "price": "10",  # 10 AIT per minute
        "price_unit": "per_minute",
        "provider_address": "0xP",
        "offer_id": "o1",
        "public_endpoint": "http://127.0.0.1:8270",
    }


def _billed_duration(monkeypatch, reported: float, max_time: int = 120) -> Decimal:
    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {"status": "completed", "duration_minutes": reported}

    monkeypatch.setattr(jobs_mod, "get_config", _config)
    monkeypatch.setattr(jobs_mod, "get_chain_id", lambda: "bc-2")
    monkeypatch.setattr(jobs_mod, "_escrow_create", lambda *a, **kw: "contract-1")
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    return jobs_mod._hermes_billed_duration(_ctx(), "job-1", "contract-1", {"duration_minutes": reported}, 1.0, max_time)


def test_inflated_duration_is_clamped(monkeypatch) -> None:
    # max_time=120s -> 2 minutes max; provider claims 100000 minutes.
    duration = _billed_duration(monkeypatch, reported=100000.0, max_time=120)
    assert jobs_mod._hermes_actual_cost(Decimal("10"), "per_minute", duration) == Decimal("10") * Decimal("2")


def test_negative_duration_is_clamped_to_zero(monkeypatch) -> None:
    duration = _billed_duration(monkeypatch, reported=-50.0, max_time=120)
    assert jobs_mod._hermes_actual_cost(Decimal("10"), "per_minute", duration) == Decimal("0")


def _run_hermes_full(monkeypatch, reported: float) -> None:
    """Drive ``_run_hermes`` end-to-end — it must complete without any
    buyer-side escrow release RPC (#2365)."""

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {
                "status": "completed",
                "text": "ok",
                "duration_minutes": reported,
                "elapsed_seconds": 1.0,
                "result_hash": "",
            }

    monkeypatch.setattr(jobs_mod, "get_config", _config)
    monkeypatch.setattr(jobs_mod, "get_chain_id", lambda: "bc-2")
    monkeypatch.setattr(jobs_mod, "_escrow_create", lambda *a, **kw: "contract-1")
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    monkeypatch.setattr(jobs_mod, "_record_job_on_chain", lambda *a, **kw: None)
    monkeypatch.setattr(jobs_mod, "_track_coordinator_job", lambda *a, **kw: None)
    jobs_mod._run_hermes(_ctx(), _offer(), "hi", 120, "0xB", "dead", "json")


def test_metered_hermes_run_never_releases_buyer_side(monkeypatch) -> None:
    """#2365: the buyer CLI must not attempt any escrow release for a metered
    job — settlement is provider-attested and server-side. ``market escrow
    release`` remains the manual recovery path."""
    _run_hermes_full(monkeypatch, reported=100000.0)
    # The buyer-side release helper is gone from the module entirely — a
    # regression that re-adds it fails here, not in production.
    assert not hasattr(jobs_mod, "_post_escrow_release")
