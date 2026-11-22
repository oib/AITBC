"""
Main exchange integration commands for AITBC CLI.
"""

import builtins
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import click

from aitbc_cli.config import get_config  # noqa: F401
from aitbc_cli.utils import DECIMAL, output, resolve_output_format, success, warning
from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError, get_logger  # noqa: F401
from aitbc_cli.utils.wallet_loader import write_json_0600

from .hub_orders import node as hub_node
from .hub_orders import order as hub_order
from .hub_orders import verify as hub_verify
from .prepay import prepay as hub_prepay
from .sell_admin import sell_admin as hub_sell_admin
from ...utils.error_handling import abort

logger = get_logger(__name__)


@click.group(
    epilog="""Examples:

  aitbc exchange register --name binance --api-key key

  aitbc exchange status --exchange-name binance"""
)
def exchange():
    """Register exchanges, create trading pairs, add liquidity, and monitor trading activity."""
    pass


def _exchanges_file() -> Path:
    return Path.home() / ".aitbc" / "exchanges.json"


def _read_exchanges() -> dict:
    path = _exchanges_file()
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_exchanges(exchanges: dict) -> None:
    """Persist exchanges.json owner-only: dir 0700, file 0600, no umask window.

    The file holds exchange API credentials (#2591) — every writer goes
    through here so no command can recreate it world-readable.
    """
    path = _exchanges_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    write_json_0600(path, exchanges)


def _read_secret_file(path: str, label: str) -> str:
    """Credential material from a file; warns when the mode is wider than 0600."""
    key_path = Path(path)
    raw = key_path.read_text().strip()
    if not raw:
        abort(None, f"{label} file {path} is empty")
    mode = key_path.stat().st_mode & 0o777
    if mode & 0o077:
        warning(f"{label} file {path} is group/other-accessible (mode {mode:o}); chmod 600 it")
    return raw


def _read_secret_stdin() -> str:
    line = sys.stdin.readline().strip()
    if not line:
        abort(None, "no credential provided on stdin")
    return line


def _resolve_exchange_credential(
    *,
    argv_value: str | None,
    file_value: str | None,
    stdin_flag: bool,
    env_name: str,
    label: str,
    option: str,
    required: bool,
) -> str | None:
    """Resolve an exchange credential without argv when possible (#2591).

    Order: --<option>-file > --<option>-stdin > env > deprecated argv
    (warns) > hidden prompt (required only). ``ps``/shell history expose
    argv values to every local user, so the file/stdin/prompt forms are
    the documented path.
    """
    if argv_value:
        warning(
            f"--{option} exposes the {label} in the process list and shell history; "
            f"prefer --{option}-file, --{option}-stdin, ${env_name}, or the prompt"
        )
    if file_value:
        return _read_secret_file(file_value, label)
    if stdin_flag:
        return _read_secret_stdin()
    env_value = (os.environ.get(env_name) or "").strip()
    if env_value:
        return env_value
    if argv_value:
        return argv_value
    if required:
        return str(click.prompt(f"{label}", hide_input=True))
    return None


def _mask_credential(value: object) -> str:
    """Last-four mask for stored credentials; 'NOT_SET' stays readable."""
    s = "" if value is None else str(value)
    if not s or s == "NOT_SET":
        return s or "***"
    return "***" + s[-4:] if len(s) > 4 else "***"


@exchange.command(
    epilog="""Examples:

  aitbc exchange register --name binance --api-key key

  aitbc exchange register --name binance --api-key key --secret-key secret --sandbox"""
)
@click.option("--name", required=True, help="Exchange name (e.g., Binance, Coinbase, Kraken)")
@click.option("--api-key", help="Exchange API key (deprecated on argv: prefer --api-key-file/--api-key-stdin)")
@click.option("--api-key-file", type=click.Path(dir_okay=False), help="File containing the API key (mode 0600)")
@click.option("--api-key-stdin", is_flag=True, help="Read the API key from one line of stdin")
@click.option("--secret-key", help="Exchange API secret key (deprecated on argv: prefer --secret-key-file/--secret-key-stdin)")
@click.option("--secret-key-file", type=click.Path(dir_okay=False), help="File containing the secret key (mode 0600)")
@click.option("--secret-key-stdin", is_flag=True, help="Read the secret key from one line of stdin")
@click.option("--sandbox", is_flag=True, help="Use sandbox/testnet environment")
@click.option("--description", help="Exchange description")
@click.pass_context
def register(
    ctx,
    name: str,
    api_key: str | None,
    api_key_file: str | None,
    api_key_stdin: bool,
    secret_key: str | None,
    secret_key_file: str | None,
    secret_key_stdin: bool,
    sandbox: bool,
    description: str | None,
):
    """Register a new exchange integration with API credentials and optional sandbox mode."""
    api_key = _resolve_exchange_credential(
        argv_value=api_key,
        file_value=api_key_file,
        stdin_flag=api_key_stdin,
        env_name="AITBC_EXCHANGE_API_KEY",
        label="API key",
        option="api-key",
        required=True,
    )
    secret_key = _resolve_exchange_credential(
        argv_value=secret_key,
        file_value=secret_key_file,
        stdin_flag=secret_key_stdin,
        env_name="AITBC_EXCHANGE_SECRET_KEY",
        label="secret key",
        option="secret-key",
        required=False,
    )
    if not api_key:
        abort(ctx, "API key is required")
        return

    exchange_config = {
        "name": name,
        "api_key": api_key,
        "secret_key": secret_key or "NOT_SET",
        "sandbox": sandbox,
        "description": description or f"{name} exchange integration",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
        "trading_pairs": [],
        "last_sync": None,
    }

    exchanges = _read_exchanges()
    exchanges[name.lower()] = exchange_config
    _write_exchanges(exchanges)

    success(f"Exchange '{name}' registered successfully")
    output(
        {"exchange": name, "status": "registered", "sandbox": sandbox, "created_at": exchange_config["created_at"]},
        resolve_output_format(ctx),
    )


@exchange.command(
    epilog="""Examples:

  aitbc exchange create-pair --base-asset AITBC --quote-asset ETH --exchange binance

  aitbc exchange create-pair --base-asset AITBC --quote-asset ETH --exchange binance --min-order-size 0.001"""
)
@click.option("--base-asset", required=True, help="Base asset symbol (e.g., AITBC)")
@click.option("--quote-asset", required=True, help="Quote asset symbol (e.g., ETH)")
@click.option("--exchange", required=True, help="Exchange name")
@click.option("--min-order-size", type=float, default=0.001, help="Minimum order size")
@click.option("--price-precision", type=int, default=8, help="Price precision")
@click.option("--quantity-precision", type=int, default=8, help="Quantity precision")
@click.pass_context
def create_pair(
    ctx, base_asset: str, quote_asset: str, exchange: str, min_order_size: float, price_precision: int, quantity_precision: int
):
    """Create a new trading pair on a registered exchange with precision and minimum order size."""
    pair_symbol = f"{base_asset}/{quote_asset}"

    if not _exchanges_file().exists():
        abort(None, "No exchanges registered. Use 'aitbc exchange register' first.")
        return

    exchanges = _read_exchanges()

    if exchange.lower() not in exchanges:
        abort(None, f"Exchange '{exchange}' not registered.")
        return

    pair_config = {
        "symbol": pair_symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "min_order_size": min_order_size,
        "price_precision": price_precision,
        "quantity_precision": quantity_precision,
        "trading_enabled": False,
        "created_at": datetime.now(UTC).isoformat(),
    }

    exchanges[exchange.lower()]["trading_pairs"].append(pair_config)

    _write_exchanges(exchanges)

    success(f"Trading pair '{pair_symbol}' created on {exchange}")
    output(pair_config, resolve_output_format(ctx))


@exchange.command(
    epilog="""Examples:

  aitbc exchange start-trading --pair AITBC/ETH --price 0.0001

  aitbc exchange start-trading --pair AITBC/ETH --base-liquidity 10000 --quote-liquidity 10000"""
)
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/ETH)")
@click.option("--price", type=DECIMAL, help="Initial price for the pair")
@click.option("--base-liquidity", type=float, default=10000, help="Base asset liquidity amount")
@click.option("--quote-liquidity", type=float, default=10000, help="Quote asset liquidity amount")
@click.option("--exchange", help="Exchange name (if not specified, uses first available)")
@click.pass_context
def start_trading(ctx, pair: str, price: Decimal | None, base_liquidity: float, quote_liquidity: float, exchange: str | None):
    """Start trading for a specific pair with optional initial price and liquidity."""
    if not _exchanges_file().exists():
        abort(None, "No exchanges registered. Use 'aitbc exchange register' first.")
        return

    exchanges = _read_exchanges()

    target_exchange = None
    target_pair = None

    for exchange_name, exchange_data in exchanges.items():
        for pair_config in exchange_data.get("trading_pairs", []):
            if pair_config["symbol"] == pair:
                target_exchange = exchange_name
                target_pair = pair_config
                break
        if target_pair:
            break

    if not target_pair:
        abort(None, f"Trading pair '{pair}' not found. Create it first with 'aitbc exchange create-pair'.")
        return

    target_pair["trading_enabled"] = True
    target_pair["started_at"] = datetime.now(UTC).isoformat()
    # exchanges.json is read back by other commands, so money is stored as a decimal
    # string -- json.dump cannot serialise a Decimal at all.
    target_pair["initial_price"] = str(price if price is not None else Decimal("0.00001"))
    target_pair["base_liquidity"] = base_liquidity
    target_pair["quote_liquidity"] = quote_liquidity

    _write_exchanges(exchanges)

    success(f"Trading started for pair '{pair}' on {target_exchange}")
    output(
        {
            "pair": pair,
            "exchange": target_exchange,
            "status": "trading_active",
            "initial_price": target_pair["initial_price"],
            "base_liquidity": base_liquidity,
            "quote_liquidity": quote_liquidity,
            "started_at": target_pair["started_at"],
        },
        resolve_output_format(ctx),
    )


def _load_monitoring_snapshot(pair: str | None, exchange: str | None) -> builtins.list[dict]:
    """Read ~/.aitbc/exchanges.json and flatten the pairs under watch."""
    if not _exchanges_file().exists():
        abort(None, "No exchanges registered. Use 'aitbc exchange register' first.")
        return []

    exchanges = _read_exchanges()

    monitoring_data = []

    for exchange_name, exchange_data in exchanges.items():
        if exchange and exchange_name != exchange.lower():
            continue

        for pair_config in exchange_data.get("trading_pairs", []):
            if pair and pair_config["symbol"] != pair:
                continue

            monitoring_data.append(
                {
                    "exchange": exchange_name,
                    "pair": pair_config["symbol"],
                    "status": "active" if pair_config.get("trading_enabled") else "inactive",
                    "created_at": pair_config.get("created_at"),
                    "started_at": pair_config.get("started_at"),
                    "initial_price": pair_config.get("initial_price"),
                    "base_liquidity": pair_config.get("base_liquidity"),
                    "quote_liquidity": pair_config.get("quote_liquidity"),
                }
            )

    if not monitoring_data:
        abort(None, "No trading pairs found for monitoring.")
        return []
    return monitoring_data


@exchange.command(
    epilog="""Examples:

  aitbc exchange monitor

  aitbc exchange monitor --real-time --interval 30"""
)
@click.option("--pair", help="Trading pair symbol (e.g., AITBC/ETH)")
@click.option("--exchange", help="Exchange name")
@click.option("--real-time", is_flag=True, help="Re-scan the registered pairs every --interval seconds until Ctrl-C")
@click.option("--interval", type=int, default=60, help="Update interval in seconds")
@click.pass_context
def monitor(ctx, pair: str | None, exchange: str | None, real_time: bool, interval: int):
    """Monitor exchange trading activity across registered pairs and exchanges."""
    if interval < 1:
        abort(ctx, "--interval must be at least 1 second")
        return

    fmt = resolve_output_format(ctx)
    first = True
    while True:
        monitoring_data = _load_monitoring_snapshot(pair, exchange)
        output(
            {
                "monitoring_active": True,
                "real_time": real_time,
                "interval": interval,
                "pairs": monitoring_data,
                "total_pairs": len(monitoring_data),
            },
            fmt,
        )
        if not real_time:
            return
        if first:
            warning(f"Real-time monitoring enabled. Re-scanning every {interval} seconds (Ctrl-C to stop).")
            first = False
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            warning("Monitoring stopped.")
            return


def _decimal_str(value: object) -> str:
    """#2439: one emitted type for liquidity fields — older exchanges.json rows
    can hold JSON numbers, so coerce every value to a decimal string."""
    return str(Decimal(str(value if value is not None else 0)))


@exchange.command(
    epilog="""Examples:

  aitbc exchange add-liquidity --pair AITBC/ETH --amount 1000

  aitbc exchange add-liquidity --pair AITBC/ETH --amount 1000 --side buy"""
)
@click.option("--pair", required=True, help="Trading pair symbol (e.g., AITBC/ETH)")
@click.option(
    "--amount",
    type=DECIMAL,
    required=True,
    help="Liquidity amount in the side's own units: --side buy adds quote-asset units "
    "(ETH for AITBC/ETH), --side sell adds base-asset units (AITBC), --side both adds "
    "the amount to each side in that side's units",
)
@click.option("--side", type=click.Choice(["buy", "sell", "both"]), default="both", help="Side to provide liquidity")
@click.option("--exchange", help="Exchange name")
@click.pass_context
def add_liquidity(ctx, pair: str, amount: Decimal, side: str, exchange: str | None):
    """Add liquidity to a trading pair on the specified side."""
    if not _exchanges_file().exists():
        abort(None, "No exchanges registered. Use 'aitbc exchange register' first.")
        return

    exchanges = _read_exchanges()

    target_exchange = None
    target_pair = None

    for exchange_name, exchange_data in exchanges.items():
        if exchange and exchange_name != exchange.lower():
            continue

        for pair_config in exchange_data.get("trading_pairs", []):
            if pair_config["symbol"] == pair:
                target_exchange = exchange_name
                target_pair = pair_config
                break
        if target_pair:
            break

    if not target_pair:
        abort(None, f"Trading pair '{pair}' not found.")
        return

    # str() on the way in: the stored value may be a JSON number written by an older
    # build, and Decimal will not add a float.
    if side == "buy" or side == "both":
        target_pair["quote_liquidity"] = str(Decimal(str(target_pair.get("quote_liquidity", 0))) + amount)
    if side == "sell" or side == "both":
        target_pair["base_liquidity"] = str(Decimal(str(target_pair.get("base_liquidity", 0))) + amount)

    target_pair["liquidity_updated_at"] = datetime.now(UTC).isoformat()

    _write_exchanges(exchanges)

    # #2447: state the unit — pair symbols are BASE/QUOTE (e.g. AITBC/ETH), so a
    # buy adds quote-asset units to quote_liquidity and a sell adds base-asset
    # units to base_liquidity; "both" adds the amount to each side in that
    # side's own units.
    base_asset, _, quote_asset = pair.partition("/")
    unit_note = {
        "buy": f"{amount} {quote_asset or 'quote'}",
        "sell": f"{amount} {base_asset or 'base'}",
        "both": f"{amount} {base_asset or 'base'} + {amount} {quote_asset or 'quote'}",
    }[side]
    success(f"Added liquidity to {pair} on {target_exchange} ({side} side): {unit_note}")
    output(
        {
            "pair": pair,
            "exchange": target_exchange,
            "amount": str(amount),
            "side": side,
            "unit": {
                "buy": quote_asset or "quote",
                "sell": base_asset or "base",
                "both": f"{base_asset or 'base'}+{quote_asset or 'quote'}",
            }[side],
            "base_liquidity": _decimal_str(target_pair.get("base_liquidity")),
            "quote_liquidity": _decimal_str(target_pair.get("quote_liquidity")),
            "updated_at": target_pair["liquidity_updated_at"],
        },
        resolve_output_format(ctx),
    )


@exchange.command(
    epilog="""Examples:

  aitbc exchange list

  aitbc exchange list --output json"""
)
@click.pass_context
def list(ctx):
    """List all registered exchanges and their trading pairs."""
    exchanges_file = _exchanges_file()
    if not exchanges_file.exists():
        if ctx.obj and ctx.obj.get("output_format") == "json":
            click.echo("[]")
        else:
            warning("No exchanges registered.")
        return

    exchanges = _read_exchanges()

    exchange_list = []
    for _exchange_name, exchange_data in exchanges.items():
        exchange_info = {
            "name": exchange_data["name"],
            "status": exchange_data["status"],
            "sandbox": exchange_data["sandbox"],
            "trading_pairs": len(exchange_data.get("trading_pairs", [])),
            "created_at": exchange_data["created_at"],
        }
        exchange_list.append(exchange_info)

    output(exchange_list, resolve_output_format(ctx), title="Registered Exchanges")


@exchange.command(
    epilog="""Examples:

  aitbc exchange status --exchange-name binance

  aitbc exchange status --exchange-name binance --output json"""
)
@click.option("--exchange-name", "exchange_name", required=True, help="The Exchange name.")
@click.pass_context
def status(ctx, exchange_name: str):
    """Get the status and configuration of a specific registered exchange."""
    if not _exchanges_file().exists():
        abort(None, "No exchanges registered.")
        return

    exchanges = _read_exchanges()

    if exchange_name.lower() not in exchanges:
        abort(None, f"Exchange '{exchange_name}' not found.")
        return

    exchange_data = dict(exchanges[exchange_name.lower()])
    # Stored credentials are never echoed — status is a read-only call and
    # its output lands in transcripts/logs (#2591).
    for field in ("api_key", "secret_key"):
        if field in exchange_data:
            exchange_data[field] = _mask_credential(exchange_data[field])
    output(exchange_data, resolve_output_format(ctx), title=f"Exchange Status: {exchange_name}")


# ETH-11 phase 2: signed AIT/ETH orders + node registration on the hub
# exchange (design eth8-exchange-page). These are the on-island counterparts
# of the external-exchange integrations above — `aitbc exchange order …` and
# `aitbc exchange node register`.
exchange.add_command(hub_order)
exchange.add_command(hub_node)
exchange.add_command(hub_verify)
exchange.add_command(hub_prepay)
exchange.add_command(hub_sell_admin)
