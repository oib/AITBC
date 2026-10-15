"""`aitbc exchange sell_admin` — read-only sell-lane operator surface
(CLI-5). The mutating verbs stay in wallet_app.bridge.sell_admin on the
hub; the CLI exposes only what an operator needs without journald.
"""

import click

from ...utils import error, output
from ..wallet.bridge import _hub_bridge_client


@click.group("sell_admin", invoke_without_command=False)
def sell_admin():
    """Sell-escrow lane status (read-only)."""
    pass


@sell_admin.command(
    epilog="""Examples:

  aitbc exchange sell_admin status
  aitbc exchange sell_admin status --hub-url https://hub.example/wallet""",
)
@click.option("--hub-url", "hub_url", default=None, help="Hub wallet-service base URL (default: configured wallet daemon)")
@click.pass_context
def status(ctx, hub_url: str | None):
    """Show the sell lane's enabled/disabled state and non-secret config
    (flags, limits, addresses, key-slot booleans — never key material)."""
    client = _hub_bridge_client(hub_url)
    try:
        doc = client.get("/v1/bridge/sell/config-status")
    except Exception as e:
        error(f"Failed to read sell config status: {e}")
        raise click.Abort() from e
    output(doc, ctx.obj.get("output_format", "table"))
