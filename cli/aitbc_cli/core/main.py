#!/usr/bin/env python3
"""
AITBC CLI - Fixed version with modular command groups

Canonical invocation: `aitbc` (installed via /opt/aitbc/venv/bin/aitbc)
"""

import sys
from pathlib import Path
from typing import Any, NoReturn, cast

# Make the repository root discoverable so that the core ``aitbc`` package
# can be imported by the CLI utilities. The CLI package itself lives under
# ``cli/aitbc_cli`` and is still found through the editable installation.
REPO_ROOT = str(Path(__file__).resolve().parents[3])
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import click
from aitbc_cli.utils.http_client import get_logger
import importlib

# Lazy command proxies. Each command module is imported only when the command is
# invoked or its help text is needed, so `aitbc --help` remains usable even when
# optional dependencies are missing.


class _UnavailableCommand:
    """Stand-in for a command that could not be loaded."""

    def __init__(self, name: str, exc: BaseException) -> None:
        self.name = name
        self.exc = exc
        self.hidden = False
        self.deprecated = False
        self.help = f"Command {name!r} is not available: {exc}"
        self.short_help = self.help
        self.params: list[Any] = []
        self.callback = self._raise
        self.add_help_option = True
        self.no_args_is_help = False
        self.options_metavar = "[OPTIONS]"
        self.invoke_without_command = False
        self.context_settings: dict[str, Any] = {}

    def _raise(self, *args, **kwargs) -> NoReturn:
        raise click.ClickException(f"Command {self.name!r} is not available: {self.exc}")

    def get_short_help_str(self, limit: int = 80) -> str:
        return f"({self.name} unavailable)"

    def get_help(self, ctx: click.Context) -> str:
        return f"Command {self.name} is not available: {self.exc}"

    def get_usage(self, ctx: click.Context) -> str:
        return ""

    def parse_args(self, ctx: click.Context, args: list[str]) -> NoReturn:
        self._raise()

    def invoke(self, ctx: click.Context) -> NoReturn:
        self._raise()

    def make_context(self, info_name: str, args: list[str], parent: click.Context | None = None, **extra: Any) -> NoReturn:
        self._raise()

    def get_command(self, ctx: click.Context, cmd_name: str) -> NoReturn:
        self._raise()

    def list_commands(self, ctx: click.Context) -> list[str]:
        return []


class LazyCommand(click.Command):
    """Proxy that defers import of a command module until first use."""

    def __init__(self, module_name: str, attr_name: str, name: str | None = None) -> None:
        self._lazy_module = module_name
        self._lazy_attr = attr_name
        self._command_name: str = name or attr_name
        self._lazy_loaded: click.Command | None = None
        self.name = self._command_name

    def _load(self) -> click.Command:
        if self._lazy_loaded is None:
            try:
                mod = importlib.import_module(self._lazy_module)
                self._lazy_loaded = cast(click.Command, getattr(mod, self._lazy_attr))
            except Exception as exc:
                logger.warning("Cannot load command %r from %s.%s: %s", self.name, self._lazy_module, self._lazy_attr, exc)
                self._lazy_loaded = cast(click.Command, _UnavailableCommand(self._command_name, exc))
        return self._lazy_loaded

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the real command once loaded."""
        return getattr(self._load(), name)

    def get_short_help_str(self, limit: int = 80) -> str:
        """Return help text, masking load failures so `aitbc --help` stays usable."""
        return self._load().get_short_help_str(limit)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def get_usage(self, ctx: click.Context) -> str:
        return self._load().get_usage(ctx)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return self._load().parse_args(ctx, args)

    def invoke(self, ctx: click.Context) -> Any:
        return self._load().invoke(ctx)

    def make_context(self, info_name: str | None, args: list[str], parent: click.Context | None = None, **extra: Any) -> click.Context:
        return self._load().make_context(info_name, args, parent=parent, **extra)


class LazyGroup(click.Group):
    """Proxy that defers import of a command group module until first use."""

    def __init__(self, module_name: str, attr_name: str, name: str | None = None) -> None:
        self._lazy_module = module_name
        self._lazy_attr = attr_name
        self._command_name: str = name or attr_name
        self._lazy_loaded: click.Group | None = None
        self.name = self._command_name

    def _load(self) -> click.Group:
        if self._lazy_loaded is None:
            try:
                mod = importlib.import_module(self._lazy_module)
                self._lazy_loaded = cast(click.Group, getattr(mod, self._lazy_attr))
            except Exception as exc:
                logger.warning(
                    "Cannot load command group %r from %s.%s: %s", self.name, self._lazy_module, self._lazy_attr, exc
                )
                self._lazy_loaded = cast(click.Group, _UnavailableCommand(self._command_name, exc))
        return self._lazy_loaded

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the real group once loaded."""
        return getattr(self._load(), name)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return self._load().get_command(ctx, cmd_name)

    def list_commands(self, ctx: click.Context) -> list[str]:
        return self._load().list_commands(ctx)

    def get_short_help_str(self, limit: int = 80) -> str:
        """Return help text, masking load failures so `aitbc --help` stays usable."""
        return self._load().get_short_help_str(limit)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def get_usage(self, ctx: click.Context) -> str:
        return self._load().get_usage(ctx)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return self._load().parse_args(ctx, args)

    def invoke(self, ctx: click.Context) -> Any:
        return self._load().invoke(ctx)

    def make_context(self, info_name: str | None, args: list[str], parent: click.Context | None = None, **extra: Any) -> click.Context:
        return self._load().make_context(info_name, args, parent=parent, **extra)


def _lazy(module_name: str, attr_name: str, name: str | None = None, group: bool = False):
    """Factory for lazy command/group proxies."""
    return LazyGroup(module_name, attr_name, name=name) if group else LazyCommand(module_name, attr_name, name=name)


account = _lazy("aitbc_cli.commands.account", "account", name="account", group=True)
agent = _lazy("aitbc_cli.commands.agent_sdk", "agent", name="agent", group=True)
agent_comm = _lazy("aitbc_cli.commands.agent_comm", "agent_comm", name="agent-comm", group=True)
agent_msg = _lazy("aitbc_cli.commands.agent", "messaging", name="agent-msg", group=True)
agent_wallet = _lazy("aitbc_cli.commands.agent_wallet", "agent_wallet", name="agent-wallet", group=True)
ai = _lazy("aitbc_cli.commands.ai", "ai", name="ai", group=True)
analytics = _lazy("aitbc_cli.commands.analytics", "analytics", name="analytics", group=True)
auth = _lazy("aitbc_cli.commands.auth", "auth", name="auth", group=True)
bond = _lazy("aitbc_cli.commands.bond", "bond", name="bond", group=True)
bootstrap = _lazy("aitbc_cli.commands.bootstrap", "bootstrap", name="bootstrap", group=True)
brand = _lazy("aitbc_cli.commands.brand", "brand", name="brand", group=True)
bridge = _lazy("aitbc_cli.commands.bridge", "bridge", name="bridge", group=True)
chain = _lazy("aitbc_cli.commands.chain", "chain", name="blockchain", group=True)
cluster = _lazy("aitbc_cli.commands.cluster", "cluster", name="cluster", group=True)
coin_requests = _lazy("aitbc_cli.commands.coin_requests", "coin_requests", name="coin-requests", group=True)
compliance = _lazy("aitbc_cli.commands.compliance", "compliance", name="compliance", group=True)
confidential = _lazy("aitbc_cli.commands.confidential", "confidential", name="confidential", group=True)
config_cmd = _lazy("aitbc_cli.commands.config", "config", name="config", group=True)
contract = _lazy("aitbc_cli.commands.contract", "contract", name="contract", group=True)
cross_chain = _lazy("aitbc_cli.commands.cross_chain", "cross_chain", name="crosschain", group=True)
dashboard = _lazy("aitbc_cli.commands.dashboard", "dashboard", name="dashboard", group=True)
deploy = _lazy("aitbc_cli.commands.deploy", "deploy", name="deploy", group=True)
developer = _lazy("aitbc_cli.commands.developer", "developer", name="developer", group=True)
economics = _lazy("aitbc_cli.commands.economics", "economics", name="economics", group=True)
edge = _lazy("aitbc_cli.commands.edge", "edge", name="edge", group=True)
exchange = _lazy("aitbc_cli.commands.exchange", "exchange", name="exchange", group=True)
exchange_island = _lazy("aitbc_cli.commands.exchange_island", "exchange_island", name="exchange-island", group=True)
explorer = _lazy("aitbc_cli.commands.explorer", "explorer", name="explorer", group=True)
genesis = _lazy("aitbc_cli.commands.genesis", "genesis", name="genesis", group=True)
governance = _lazy("aitbc_cli.commands.governance", "governance", name="governance", group=True)
gpu = _lazy("aitbc_cli.commands.gpu_marketplace", "gpu", name="gpu", group=True)
gpu_onchain = _lazy("aitbc_cli.commands.gpu_resources", "gpu", name="gpu-onchain", group=True)
grant = _lazy("aitbc_cli.commands.grant", "grant", name="grant", group=True)
http = _lazy("aitbc_cli.commands.http", "http", name="http", group=True)
ipfs = _lazy("aitbc_cli.commands.ipfs", "ipfs", name="ipfs", group=True)
market = _lazy("aitbc_cli.commands.market", "market", name="market", group=True)
messaging = _lazy("aitbc_cli.commands.messaging", "messaging", name="messaging", group=True)
mining = _lazy("aitbc_cli.commands.mining", "mining", name="mining", group=True)
monitor = _lazy("aitbc_cli.commands.monitor", "monitor", name="monitor", group=True)
network = _lazy("aitbc_cli.commands.network", "network", name="network", group=True)
node = _lazy("aitbc_cli.commands.node", "node", name="node", group=True)
operations = _lazy("aitbc_cli.commands.operations", "operations", name="operations", group=True)
oracle = _lazy("aitbc_cli.commands.oracle", "oracle", name="oracle", group=True)
performance = _lazy("aitbc_cli.commands.performance", "performance", name="performance", group=True)
platform = _lazy("aitbc_cli.commands.platform", "platform", name="platform", group=True)
plugin = _lazy("aitbc_cli.commands.plugin", "plugin", name="plugin", group=True)
pool_hub = _lazy("aitbc_cli.commands.pool_hub", "pool_hub", name="pool-hub", group=True)
prometheus = _lazy("aitbc_cli.commands.prometheus", "prometheus", name="prometheus", group=True)
reinvest = _lazy("aitbc_cli.commands.reinvest", "reinvest", name="reinvest", group=True)
reputation = _lazy("aitbc_cli.commands.reputation", "reputation", name="reputation", group=True)
resource = _lazy("aitbc_cli.commands.resource", "resource", name="resource", group=True)
restart = _lazy("aitbc_cli.commands.control", "restart", name="restart", group=False)
script = _lazy("aitbc_cli.commands.script", "script", name="script", group=True)
security = _lazy("aitbc_cli.commands.security", "security", name="security", group=True)
simulate = _lazy("aitbc_cli.commands.simulate", "simulate", name="simulate", group=True)
start = _lazy("aitbc_cli.commands.control", "start", name="start", group=False)
stop = _lazy("aitbc_cli.commands.control", "stop", name="stop", group=False)
sync = _lazy("aitbc_cli.commands.sync", "sync", name="sync", group=True)
system = _lazy("aitbc_cli.commands.system", "system", name="system", group=True)
trade = _lazy("aitbc_cli.commands.trade", "trade", name="trade", group=True)
transactions = _lazy("aitbc_cli.commands.transactions", "transactions", name="transactions", group=True)
update = _lazy("aitbc_cli.commands.update", "update", name="update", group=False)
wallet = _lazy("aitbc_cli.commands.wallet", "wallet", name="wallet", group=True)
workflow = _lazy("aitbc_cli.commands.workflow", "workflow", name="workflow", group=True)
zk = _lazy("aitbc_cli.commands.zk", "zk", name="zk", group=True)

# Force CLI version for user-facing output
__version__ = "0.10.18"

logger = get_logger(__name__)


@click.command(
    name="list",
    epilog="""Examples:

  aitbc list

  aitbc list --output json""",
)
@click.pass_context
def list_wallets(ctx):
    """Legacy alias for 'aitbc wallet list' that lists all locally stored wallets."""
    # Forward to the wallet group's list subcommand so global flags in ctx.obj are preserved.
    ctx.invoke(
        wallet,
        wallet_name=None,
        wallet_path=None,
        use_daemon=True,
        chain_id=ctx.obj.get("chain_id"),
    )
    list_cmd = wallet.get_command(ctx, "list")
    if list_cmd is None:
        from ..utils import error

        error("wallet list subcommand not found")
        return
    return ctx.invoke(list_cmd)


@click.command(
    epilog="""Examples:

  aitbc version"""
)
def version():
    """Show the AITBC CLI version and architecture support status."""
    click.echo(f"aitbc, version {__version__}")
    click.echo("System Architecture Support: ✅")
    click.echo("FHS Compliance: ✅")
    click.echo("New Features: ✅")


@click.group()
@click.version_option(version=__version__, prog_name="aitbc")
@click.option("--url", default=None, help="Coordinator API URL (overrides config)")
@click.option("--api-key", default=None, help="API key for authentication")
@click.option("--chain-id", default=None, help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.option("--output", default="table", type=click.Choice(["table", "json", "yaml", "csv"]), help="Output format")
@click.option("--verbose", "-v", count=True, help="Increase verbosity (can be used multiple times)")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def cli(ctx, url, api_key, chain_id, output, verbose, debug):
    """AITBC CLI - Command Line Interface for AITBC Network

    Manage jobs, mining, wallets, blockchain tasks, market, and AI
    services.

    COMMAND GROUP DISAMBIGUATION:
    - `aitbc market` — GPU/software offers (coordinator-backed, miner-published).
    - `aitbc governance` — service-backed proposals, voting, and execution.
    - `aitbc operations` and `aitbc operations <subgroup>` are deprecated; use the groups above.

    SYSTEM ARCHITECTURE COMMANDS:
    system          System management commands
    system architect    System architecture analysis
    system audit         Audit system compliance
    system check         Check service configuration

    Examples:
    aitbc system architect
    aitbc system audit
    aitbc system check --service blockchain-node
    """
    from aitbc_cli.config import get_config

    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["api_key"] = api_key
    ctx.obj["output"] = output
    ctx.obj["output_format"] = output
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug

    # Load the configuration object once and share it with all subcommands.
    # Commands that need fresh data (e.g., after a config set) can call
    # get_config() directly.
    ctx.obj["config"] = get_config()

    # Handle chain_id with auto-detection
    from aitbc_cli.utils.chain_id import get_chain_id

    default_rpc_url = url.replace("/api", "") if url else "http://127.0.0.1:8202"
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)


# Add commands to CLI
cli.add_command(system)
cli.add_command(start)
cli.add_command(stop)
cli.add_command(restart)
cli.add_command(market, name="market")
cli.add_command(chain, name="blockchain")
cli.add_command(agent, name="agent")  # Agent SDK and coordinator commands
cli.add_command(ai)  # AI job submission and inspection
cli.add_command(analytics)  # Re-enabled - core.analytics exists
cli.add_command(cross_chain, name="crosschain")  # Re-enabled - no core dependency
cli.add_command(reputation)  # Reputation management
cli.add_command(governance)  # Governance operations
cli.add_command(developer)  # Developer registry
cli.add_command(grant)  # DAO grant proposals
cli.add_command(monitor)
cli.add_command(prometheus)  # Re-enabled - no core dependency
cli.add_command(node)
cli.add_command(agent_comm)  # Cross-chain agent communication (distinct from `agent` SDK group)
cli.add_command(exchange)
cli.add_command(ipfs)  # Local content-addressed storage
cli.add_command(oracle)  # Local data oracle
cli.add_command(config_cmd, name="config")
cli.add_command(list_wallets)
cli.add_command(version)
cli.add_command(gpu)
cli.add_command(gpu_onchain)
cli.add_command(exchange_island)
cli.add_command(wallet)
cli.add_command(genesis)

# Add new modular commands
cli.add_command(zk)
cli.add_command(auth)
cli.add_command(dashboard)
cli.add_command(transactions)
cli.add_command(update)
cli.add_command(mining)
cli.add_command(http)
cli.add_command(agent_msg, name="agent-msg")
cli.add_command(workflow)
cli.add_command(resource)
cli.add_command(operations)
cli.add_command(simulate)
cli.add_command(edge)
cli.add_command(sync)
cli.add_command(account)
cli.add_command(messaging)
cli.add_command(network)
cli.add_command(performance)
cli.add_command(platform)
cli.add_command(pool_hub)
cli.add_command(plugin)
cli.add_command(brand)
cli.add_command(bridge)
cli.add_command(deploy)
cli.add_command(contract)
cli.add_command(script)
cli.add_command(economics)
cli.add_command(bond)
cli.add_command(bootstrap)
cli.add_command(reinvest)
cli.add_command(confidential)
cli.add_command(cluster)
cli.add_command(security)
cli.add_command(compliance)
cli.add_command(coin_requests)
cli.add_command(explorer)
cli.add_command(trade)
cli.add_command(agent_wallet, name="agent-wallet")

# Canonical top-level command groups are exposed by default. Legacy `operations`
# and its subgroups are hidden from default `--help` and marked deprecated.


def main(argv=None):
    """Entry point for console scripts and compatibility wrappers."""
    from aitbc_cli.utils.error_handling import CLIError

    try:
        return cli.main(args=argv, prog_name="aitbc", standalone_mode=False)
    except CLIError as e:
        # Error already printed by abort(); just exit with the proper code
        logger.debug("CLI error: %s", e, exc_info=True)
        return e.exit_code
    except click.Abort:
        # Legacy bare click.Abort() — error message already printed, no traceback
        logger.debug("CLI aborted", exc_info=True)
        return 1
    except click.exceptions.NoArgsIsHelpError as e:
        # Show help message and exit cleanly
        click.echo(str(e))
        return 0
    except click.exceptions.UsageError as e:
        # Print friendly usage error (e.g. missing required option) and exit 2
        e.show()
        return e.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
