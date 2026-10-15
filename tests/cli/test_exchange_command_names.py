"""Guards for the exchange command group: every command name is registered once.

click replaces a command silently when a second module registers the same name on a group — the
``aitbc market cancel`` collision (offers.py vs host.py) hid a command and nothing failed. The
exchange group adds names through both ``@exchange.command`` decorators and ``add_command`` calls
in main.py, so this file scans the decorator sites like the market guard and then asserts the
``prepay`` subgroup wired in by PREPAY-1 actually resolves at runtime.
"""

import ast
from collections import defaultdict
from pathlib import Path

from click.testing import CliRunner

from aitbc_cli.commands.exchange.main import exchange

EXCHANGE_DIR = Path(__file__).resolve().parents[2] / "cli" / "aitbc_cli" / "commands" / "exchange"


def _registered_name(node: ast.FunctionDef | ast.AsyncFunctionDef, deco: ast.expr) -> tuple[str, str] | None:
    """Resolve one decorator to (group variable, registered name), or None when it
    is not a ``@<group>.command``/``@<group>.group`` registration."""
    call = deco if isinstance(deco, ast.Call) else None
    func = call.func if call else deco
    if not (isinstance(func, ast.Attribute) and func.attr in ("command", "group") and isinstance(func.value, ast.Name)):
        return None
    name = None
    if call:
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name = kw.value.value
        if name is None and call.args and isinstance(call.args[0], ast.Constant):
            name = call.args[0].value
    if name is None:
        name = node.name.replace("_", "-")
    return func.value.id, str(name)


def _registered_command_names() -> dict[tuple[str, str], list[str]]:
    """Map (group variable, command name) to every ``@<group>.command`` site that registers it."""
    sites: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in sorted(EXCHANGE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for deco in node.decorator_list:
                site = _registered_name(node, deco)
                if site is not None:
                    sites[site].append(f"{path.name}:{node.lineno}")
    return sites


class TestExchangeCommandNames:
    def test_no_command_name_is_registered_twice(self):
        sites = _registered_command_names()
        assert sites, "the scan found no @<group>.command registrations; the test is looking in the wrong place"
        duplicates = {key: where for key, where in sites.items() if len(where) > 1}
        assert not duplicates, f"command names registered more than once (the later one hides the earlier): {duplicates}"

    def test_prepay_subgroup_is_registered_and_resolves(self):
        assert "prepay" in exchange.commands, (
            "aitbc exchange prepay vanished — check add_command wiring in exchange/main.py and name collisions"
        )
        prepay = exchange.commands["prepay"]
        assert "deposit" in prepay.commands

    def test_prepay_deposit_answers_help(self):
        runner = CliRunner()
        group_help = runner.invoke(exchange, ["prepay", "--help"])
        assert group_help.exit_code == 0 and "deposit" in group_help.output
        deposit_help = runner.invoke(exchange, ["prepay", "deposit", "--help"])
        assert deposit_help.exit_code == 0
        for flag in ("--amount-eth", "--send", "--max-eth", "--exchange-url", "--eth-rpc-url"):
            assert flag in deposit_help.output
