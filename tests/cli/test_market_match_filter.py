"""``market match`` must count offers, not every marketplace transaction.

GPU_MARKETPLACE carries listings *and* job settlements. Until 2026-09-15
``/rpc/transactions/marketplace/match`` selected on the transaction type alone,
so settlements came back as "matches" projected to empty strings and price 0 --
the table printed them as rows of N/A and the footer counted them.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from click.testing import CliRunner

from aitbc_cli.commands.market.offers import _purchasable_matches, match

SOFTWARE_OFFER = {
    "listing_id": "tx_1",
    "seller": "0xseller",
    "service_type": "whisper",
    "model": "base",
    "price": 0.02,
    "price_unit": "per_audio_min",
}
HARDWARE_OFFER = {
    "listing_id": "tx_2",
    "seller": "0xseller",
    # A hardware offer payload sets neither service_type nor price -- it carries
    # model and price_per_hour -- so a filter keyed on price alone drops it.
    "service_type": "",
    "model": "RTX 4090",
    "price": 0,
}
SETTLEMENT = {
    "listing_id": "tx_3",
    "seller": "0xbuyer",
    "service_type": "",
    "model": "",
    "price": 0,
    "price_unit": "",
}


def test_settlements_are_dropped_and_both_offer_shapes_survive():
    assert _purchasable_matches([SOFTWARE_OFFER, SETTLEMENT, HARDWARE_OFFER]) == [
        SOFTWARE_OFFER,
        HARDWARE_OFFER,
    ]


def test_a_free_offer_is_not_mistaken_for_a_settlement():
    free = {**SOFTWARE_OFFER, "price": 0}
    assert _purchasable_matches([free]) == [free]


def test_empty_input_is_empty_output():
    assert _purchasable_matches([]) == []


def _run(fmt: str, matches: list[dict]):
    client = Mock()
    client.get.return_value = {"chain_id": "test", "matches": matches, "total": len(matches)}
    with (
        patch("aitbc_cli.commands.market.offers.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.market.offers.get_config") as get_config,
    ):
        get_config.return_value = Mock(blockchain_rpc_url="http://localhost:8202", hub_discovery_url=None)
        return CliRunner().invoke(match, ["--format", fmt], obj={})


def test_table_footer_counts_only_offers():
    result = _run("table", [SOFTWARE_OFFER, SETTLEMENT, HARDWARE_OFFER])
    assert result.exit_code == 0, result.output
    assert "Total: 2 offer(s)" in result.output
    assert "0xbuyer" not in result.output


def test_json_total_agrees_with_the_table():
    result = _run("json", [SOFTWARE_OFFER, SETTLEMENT, HARDWARE_OFFER])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # The server reported 3; a machine-readable format that disagrees with the
    # table is worse than either alone.
    assert payload["total"] == 2
    assert [m["listing_id"] for m in payload["matches"]] == ["tx_1", "tx_2"]


def test_a_response_of_only_settlements_reports_nothing_to_buy():
    result = _run("table", [SETTLEMENT])
    assert result.exit_code == 0, result.output
    assert "No matching offers found." in result.output
