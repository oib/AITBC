"""Guards for the market command group: every command name is registered once.

click replaces a command silently when a second module registers the same name on a group. That is how
``aitbc market cancel --order-ids`` (offers.py) vanished behind ``aitbc market cancel --job-id`` (host.py):
the offer cancel was unreachable from the deployed CLI and nothing failed.
"""

import ast
from collections import defaultdict
from pathlib import Path

from click.testing import CliRunner

from aitbc_cli.commands.market import market

MARKET_DIR = Path(__file__).resolve().parents[2] / "cli" / "aitbc_cli" / "commands" / "market"


def _registered_command_names() -> dict[tuple[str, str], list[str]]:
    """Map (group variable, command name) to every ``@<group>.command`` site that registers it."""
    sites: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in sorted(MARKET_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for deco in node.decorator_list:
                call = deco if isinstance(deco, ast.Call) else None
                func = call.func if call else deco
                if not (isinstance(func, ast.Attribute) and func.attr == "command" and isinstance(func.value, ast.Name)):
                    continue
                name = None
                if call:
                    for kw in call.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            name = kw.value.value
                    if name is None and call.args and isinstance(call.args[0], ast.Constant):
                        name = call.args[0].value
                if name is None:
                    name = node.name.replace("_", "-")
                sites[(func.value.id, str(name))].append(f"{path.name}:{node.lineno}")
    return sites


class TestMarketCommandNames:
    def test_no_command_name_is_registered_twice(self):
        sites = _registered_command_names()
        assert sites, "the scan found no @<group>.command registrations; the test is looking in the wrong place"
        duplicates = {key: where for key, where in sites.items() if len(where) > 1}
        assert not duplicates, f"command names registered more than once (the later one hides the earlier): {duplicates}"

    def test_job_cancel_and_offer_cancel_are_distinct_commands(self):
        assert "cancel" in market.commands and "offer-cancel" in market.commands
        assert market.commands["cancel"] is not market.commands["offer-cancel"]
        job_params = {p.name for p in market.commands["cancel"].params}
        offer_params = {p.name for p in market.commands["offer-cancel"].params}
        assert "job_id" in job_params and "order_ids" not in job_params
        assert "order_ids" in offer_params and "job_id" not in offer_params

    def test_both_cancel_commands_answer_help(self):
        runner = CliRunner()
        job_help = runner.invoke(market, ["cancel", "--help"])
        offer_help = runner.invoke(market, ["offer-cancel", "--help"])
        assert job_help.exit_code == 0 and "--job-id" in job_help.output
        assert offer_help.exit_code == 0 and "--order-ids" in offer_help.output
