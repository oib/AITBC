"""#2361: ``aitbc liquidity stakes`` lists on-chain positions.

The wallet file's local liquidity records carry ``stake_id: null`` (pre-fix)
and there was no CLI surface for ``GET /rpc/liquidity/stakes/{address}`` —
operators had to hand-roll HTTP to discover ``liq_<txhash>`` ids.
"""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from aitbc_cli.commands.liquidity import stakes


def _runner() -> CliRunner:
    return CliRunner()


def test_stakes_lists_positions_for_address():
    payload = {
        "success": True,
        "address": "0xAbc",
        "stakes": [{"stake_id": "liq_0x944d99b9ab12aa", "amount": 5000, "status": "active"}],
    }
    with patch("aitbc_cli.commands.liquidity.AITBCHTTPClient") as cls:
        cls.return_value.get.return_value = payload
        result = _runner().invoke(
            stakes,
            ["--address", "0xAbc", "--chain-id", "bc-2", "--format", "json"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output
    cls.return_value.get.assert_called_once_with("/rpc/liquidity/stakes/0xAbc?chain_id=bc-2")
    assert "liq_0x944d99b9ab12aa" in result.output


def test_stakes_requires_address_or_wallet():
    result = _runner().invoke(stakes, ["--format", "json"], obj={"output_format": "json"})
    assert result.exit_code != 0
