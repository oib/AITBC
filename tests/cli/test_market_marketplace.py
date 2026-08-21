"""Tests that market and marketplace group help are distinguishable."""

from click.testing import CliRunner


class TestMarketMarketplaceHelp:
    def test_market_help_describes_gpu_offers(self):
        from aitbc_cli.commands.market import market

        runner = CliRunner()
        result = runner.invoke(market, ["--help"])

        assert result.exit_code == 0, result.output
        assert "GPU" in result.output or "software" in result.output

    def test_marketplace_help_describes_global_chain(self):
        from aitbc_cli.commands.marketplace_cmd import marketplace

        runner = CliRunner()
        result = runner.invoke(marketplace, ["--help"])

        assert result.exit_code == 0, result.output
        assert "Global" in result.output or "on-chain" in result.output
