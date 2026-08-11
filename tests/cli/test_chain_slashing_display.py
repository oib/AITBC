"""The slashing-history table showed a rate under a heading that said "Amount".

V23-48. The node sent `slash_amount` holding a fraction of stake, and the CLI printed it
verbatim in a column called "Amount": a 50% double-sign penalty rendered as `0.5`, which
reads as 0.5 AIT. The rate and the amount are now separate columns, and an event that was
detected but never levied says so instead of showing a blank.
"""

from __future__ import annotations

from aitbc_cli.commands.chain import _slash_rate


def test_rate_renders_as_a_percentage():
    assert _slash_rate({"slash_rate": 0.5}) == "50%"
    assert _slash_rate({"slash_rate": 0.05}) == "5%"
    assert _slash_rate({"slash_rate": 0.3}) == "30%"


def test_legacy_nodes_send_the_rate_under_the_old_key():
    """`slash_amount` never held an amount, so reading it as a rate is the correct reading."""
    assert _slash_rate({"slash_amount": 0.5}) == "50%"


def test_the_new_key_wins_when_a_node_sends_both():
    assert _slash_rate({"slash_rate": 0.3, "slash_amount": 0.5}) == "30%"


def test_absent_or_unparseable_rates_do_not_crash_the_table():
    """One malformed event must not take down the whole listing."""
    assert _slash_rate({}) == "N/A"
    assert _slash_rate({"slash_rate": None}) == "N/A"
    assert _slash_rate({"slash_rate": "not-a-number"}) == "N/A"
