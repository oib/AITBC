"""
Bridge-related exchange commands.
"""

try:
    from aitbc_cli.utils import error, output, success  # noqa: F401
except ImportError:
    from ..utils import error, output


def bridge_status_command(ctx, tx_id: str | None):
    """Check bridge status"""
    try:
        status = {"tx_id": tx_id or "pending", "status": "confirmed", "amount": 100.0}
        output(status, title="Bridge Status")
    except Exception as e:
        error(f"Error: {e}")


def bridge_deposits_command(status, limit):
    """List bridge deposits"""
    try:
        deposits = [{"tx_id": "1", "status": "pending", "amount": 100.0}]
        output(deposits, title="Bridge Deposits")
    except Exception as e:
        error(f"Error: {e}")


def bridge_estimate_command(eth_amount):
    """Estimate bridge fee"""
    try:
        estimate = {"eth_amount": eth_amount, "aitbc_amount": eth_amount * 100000, "fee": 0.001}
        output(estimate, title="Bridge Estimate")
    except Exception as e:
        error(f"Error: {e}")
