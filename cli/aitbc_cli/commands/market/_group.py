"""The ``aitbc market`` click group.

Kept in a leaf module so command submodules can register against it without
importing this package's ``__init__`` — ``__init__`` imports the submodules to
attach their commands, and a submodule importing the group back from the
package would close an import cycle.
"""

import click

from ...utils.wallet_secret import wallet_password_options


@click.group(
    epilog="""Examples:

  aitbc market list

  aitbc market run --offer-id-or-plugin-id offer-1 --prompt 'hello'"""
)
@click.option("--wallet", "market_wallet", help="Wallet name for market payments")
@click.option("--wallet-path", "market_wallet_path", help="Direct wallet file path (overrides --wallet)")
@wallet_password_options
@click.pass_context
def market(ctx, market_wallet, market_wallet_path, password, password_file, password_stdin):
    """GPU and software market offers published by shop miners and backed by the coordinator."""
    ctx.ensure_object(dict)
    ctx.obj["market_wallet"] = market_wallet
    ctx.obj["market_wallet_path"] = market_wallet_path
    ctx.obj["market_password"] = password
    ctx.obj["market_password_file"] = password_file
    ctx.obj["market_password_stdin"] = password_stdin
