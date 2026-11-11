"""HERMES-IPFS-DEPTH2-1 (#1633): shop-reported duration_minutes is clamped
to [0, max_time] before billing — a malicious/MITM'd provider cannot inflate
the charge past the locked escrow.
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


def _run_with_reported_duration(monkeypatch, reported: float, max_time: int = 120) -> Decimal:
    released: list[str] = []

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

    def _release(ctx: Any, config: Any, job_id: str, amount: str, **kw: Any) -> tuple[dict[str, Any], list[str]]:
        released.append(amount)
        return {"tx_hash": "0xabc", "released_amount": amount}, []

    monkeypatch.setattr(jobs_mod, "_post_escrow_release", _release)
    jobs_mod._run_hermes(_ctx(), _offer(), "hi", max_time, "0xB", "dead", "json")
    assert released, "escrow release was never attempted"
    return Decimal(released[0])


def test_inflated_duration_is_clamped(monkeypatch) -> None:
    # max_time=120s -> 2 minutes max; provider claims 100000 minutes.
    amount = _run_with_reported_duration(monkeypatch, reported=100000.0, max_time=120)
    assert amount == Decimal("10") * Decimal("2")  # 10 AIT/min * 2 min


def test_negative_duration_is_clamped_to_zero(monkeypatch) -> None:
    amount = _run_with_reported_duration(monkeypatch, reported=-50.0, max_time=120)
    assert amount == Decimal("0")
