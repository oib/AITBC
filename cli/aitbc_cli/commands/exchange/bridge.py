"""
Bridge-related exchange commands.
"""

from aitbc_cli.utils import error, output, success  # noqa: F401
from ...utils.error_handling import CLIError, abort

# Expected failure surface for these stub command handlers: filesystem/JSON,
# data-shape, runtime and CLIError (abort()). BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    CLIError,
)


def bridge_status_command(ctx, tx_id: str | None):
    """Check bridge status"""
    try:
        status = {
            "tx_id": tx_id or "pending",
            "status": "confirmed",
            "amount": 100.0,
        }  # not-money: stub/demo response, not a live amount
        output(status, title="Bridge Status")
    except _OPS_ERRORS as e:
        abort(None, f"Error: {e}")


def bridge_deposits_command(status, limit):
    """List bridge deposits"""
    try:
        deposits = [{"tx_id": "1", "status": "pending", "amount": 100.0}]  # not-money: stub/demo response, not a live amount
        output(deposits, title="Bridge Deposits")
    except _OPS_ERRORS as e:
        abort(None, f"Error: {e}")


def bridge_estimate_command(eth_amount):
    """Estimate bridge fee"""
    try:
        estimate = {
            "eth_amount": eth_amount,
            "aitbc_amount": eth_amount * 100000,
            "fee": 0.001,
        }  # not-money: stub/demo response, not a live amount
        output(estimate, title="Bridge Estimate")
    except _OPS_ERRORS as e:
        abort(None, f"Error: {e}")
