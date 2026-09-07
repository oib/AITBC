"""Tests that market and marketplace group help are distinguishable."""

from click.testing import CliRunner


class TestMarketMarketplaceHelp:
    def test_market_help_describes_gpu_offers(self):
        from aitbc_cli.commands.market import market

        runner = CliRunner()
        result = runner.invoke(market, ["--help"])

        assert result.exit_code == 0, result.output
        assert "GPU" in result.output or "software" in result.output

    # The ``marketplace`` top-level group was removed in the market-subtree
    # refactor; the on-chain/global help it described no longer exists.
