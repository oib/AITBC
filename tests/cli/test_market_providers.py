"""``market providers`` used to be a stub.

It printed "GPU provider query via P2P network to be implemented" and pointed
at `aitbc gpu list`, which shows locally registered GPUs -- a different
population entirely. It now collapses the live offer list to one row per seller.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from aitbc_cli.commands.market.offers import _group_by_provider, _provider_rating, providers

OFFERS = [
    {
        "provider_address": "0xalice",
        "node_id": "node-a",
        "service_type": "whisper",
        "model": "base",
        "status": "active",
        "gpu_name": "RTX 4060 Ti",
        "public_endpoint": "https://a.example/",
        "avg_rating": 5.0,
        "rating_count": 2,
    },
    {
        "provider_address": "0xalice",
        "node_id": "node-a",
        "service_type": "ollama",
        "model": "llama3.2:3b",
        "status": "disabled",
        "gpu_name": "RTX 4060 Ti",
        "public_endpoint": "https://a.example/",
        "avg_rating": 3.0,
        "rating_count": 8,
    },
    {
        "provider_address": "bob-miner",
        "node_id": "bob-miner",
        "service_type": "gpu_marketplace",
        "model": "RTX 4090",
        "status": "active",
        "gpu_name": "RTX 4090",
        "public_endpoint": "https://b.example/",
        "avg_rating": 0,
        "rating_count": 0,
    },
]


def test_grouping_falls_back_to_node_id():
    grouped = _group_by_provider([{"node_id": "only-node"}, {"provider_address": "0xa", "node_id": "n"}])
    assert sorted(grouped) == ["0xa", "only-node"]


def test_rating_is_weighted_by_review_count():
    # 5.0 over 2 reviews and 3.0 over 8 must not average to 4.0.
    assert _provider_rating(OFFERS[:2]) == "3.4 (10 reviews)"


def test_trust_score_wins_over_stars():
    assert _provider_rating([{**OFFERS[0], "trust_score": 850}]) == "0.85 trust"


def test_no_reviews_reads_as_unrated():
    assert _provider_rating(OFFERS[2:]) == "unrated"


def _run(fmt: str, offers: list[dict] | None):
    client = Mock()

    def _get(path, **kw):
        return {"offers": offers} if "marketplace/offer" in path else {"error": "no profile"}

    client.get.side_effect = _get
    with (
        patch("aitbc_cli.commands.market.offers.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.market.offers.get_config") as get_config,
    ):
        get_config.return_value = Mock(hub_discovery_url="hub.example", coordinator_api_url=None)
        return CliRunner().invoke(providers, ["--format", fmt], obj={})


def test_one_row_per_provider_not_per_offer():
    result = _run("json", OFFERS)
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert [r["Provider"] for r in rows] == ["0xalice", "bob-miner"]
    assert rows[0]["Offers"] == 2
    # One of alice's two offers is disabled; a buyer needs that distinction.
    assert rows[0]["Active"] == 1
    assert rows[0]["Services"] == "ollama, whisper"


def test_it_is_not_a_stub_anymore():
    result = _run("table", OFFERS)
    assert result.exit_code == 0, result.output
    assert "to be implemented" not in result.output
    assert "Total: 2 provider(s), 3 offer(s)" in result.output


def test_an_empty_marketplace_says_so():
    result = _run("table", [])
    assert result.exit_code == 0, result.output
    assert "No providers are listing offers right now." in result.output
