"""
Payment-related exchange commands.
"""

try:
    from aitbc_cli.utils import error, output, success
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError
except ImportError:
    from ..utils import error, output, success
    from ..utils.http_client import AITBCHTTPClient, NetworkError


def create_payment_command(ctx, aitbc_amount: float | None, btc_amount: float | None, user_id: str | None, notes: str | None):
    """Create a Bitcoin payment request for AITBC purchase"""
    config = ctx.obj["config"]

    if aitbc_amount is not None and aitbc_amount <= 0:
        error("AITBC amount must be greater than 0")
        return

    if btc_amount is not None and btc_amount <= 0:
        error("BTC amount must be greater than 0")
        return

    if not aitbc_amount and not btc_amount:
        error("Either --aitbc-amount or --btc-amount must be specified")
        return

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        rates = http_client.get("/exchange/rates")
        btc_to_aitbc = rates.get("btc_to_aitbc", 100000)

        if aitbc_amount and not btc_amount:
            btc_amount = aitbc_amount / btc_to_aitbc
        elif btc_amount and not aitbc_amount:
            aitbc_amount = btc_amount * btc_to_aitbc

        payment_data = {"user_id": user_id or "cli_user", "aitbc_amount": aitbc_amount, "btc_amount": btc_amount}

        if notes:
            payment_data["notes"] = notes

        payment = http_client.post("/exchange/create-payment", json=payment_data)
        success(f"Payment created: {payment.get('payment_id')}")
        success(f"Send {btc_amount:.8f} BTC to: {payment.get('payment_address')}")
        success(f"Expires at: {payment.get('expires_at')}")
        output(payment, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


def payment_status_command(ctx, payment_id: str):
    """Check payment confirmation status"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        status_data = http_client.get(f"/exchange/payment-status/{payment_id}")
        status = status_data.get("status", "unknown")

        if status == "confirmed":
            success(f"Payment {payment_id} is confirmed!")
            success(f"AITBC amount: {status_data.get('aitbc_amount', 0)}")
        elif status == "pending":
            success(f"Payment {payment_id} is pending confirmation")
        elif status == "expired":
            error(f"Payment {payment_id} has expired")
        else:
            success(f"Payment {payment_id} status: {status}")

        output(status_data, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")


def market_stats_command(ctx):
    """Get exchange market statistics"""
    config = ctx.obj["config"]

    try:
        http_client = AITBCHTTPClient(base_url=config.exchange_service_url, timeout=10)
        stats = http_client.get("/exchange/market-stats")
        success("Exchange market statistics:")
        output(stats, ctx.obj["output_format"])
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error: {e}")
