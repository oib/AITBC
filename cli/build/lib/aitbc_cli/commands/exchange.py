"""Exchange commands for AITBC CLI"""

import click
import httpx
from typing import Optional

from ..config import get_config
from ..utils import success, error, output


@click.group()
def exchange():
    """Bitcoin exchange operations"""
    pass


@exchange.command()
@click.pass_context
def rates(ctx):
    """Get current exchange rates"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/exchange/rates",
                timeout=10
            )
            
            if response.status_code == 200:
                rates_data = response.json()
                success("Current exchange rates:")
                output(rates_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get exchange rates: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.option("--aitbc-amount", type=float, help="Amount of AITBC to buy")
@click.option("--btc-amount", type=float, help="Amount of BTC to spend")
@click.option("--user-id", help="User ID for the payment")
@click.option("--notes", help="Additional notes for the payment")
@click.pass_context
def create_payment(ctx, aitbc_amount: Optional[float], btc_amount: Optional[float], 
                  user_id: Optional[str], notes: Optional[str]):
    """Create a Bitcoin payment request for AITBC purchase"""
    config = ctx.obj['config']
    
    # Validate input
    if aitbc_amount is not None and aitbc_amount <= 0:
        error("AITBC amount must be greater than 0")
        return
    
    if btc_amount is not None and btc_amount <= 0:
        error("BTC amount must be greater than 0")
        return
    
    if not aitbc_amount and not btc_amount:
        error("Either --aitbc-amount or --btc-amount must be specified")
        return
    
    # Get exchange rates to calculate missing amount
    try:
        with httpx.Client() as client:
            rates_response = client.get(
                f"{config.coordinator_url}/v1/exchange/rates",
                timeout=10
            )
            
            if rates_response.status_code != 200:
                error("Failed to get exchange rates")
                return
            
            rates = rates_response.json()
            btc_to_aitbc = rates.get('btc_to_aitbc', 100000)
            
            # Calculate missing amount
            if aitbc_amount and not btc_amount:
                btc_amount = aitbc_amount / btc_to_aitbc
            elif btc_amount and not aitbc_amount:
                aitbc_amount = btc_amount * btc_to_aitbc
            
            # Prepare payment request
            payment_data = {
                "user_id": user_id or "cli_user",
                "aitbc_amount": aitbc_amount,
                "btc_amount": btc_amount
            }
            
            if notes:
                payment_data["notes"] = notes
            
            # Create payment
            response = client.post(
                f"{config.coordinator_url}/v1/exchange/create-payment",
                json=payment_data,
                timeout=10
            )
            
            if response.status_code == 200:
                payment = response.json()
                success(f"Payment created: {payment.get('payment_id')}")
                success(f"Send {btc_amount:.8f} BTC to: {payment.get('payment_address')}")
                success(f"Expires at: {payment.get('expires_at')}")
                output(payment, ctx.obj['output_format'])
            else:
                error(f"Failed to create payment: {response.status_code}")
                if response.text:
                    error(f"Error details: {response.text}")
                    
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.option("--payment-id", required=True, help="Payment ID to check")
@click.pass_context
def payment_status(ctx, payment_id: str):
    """Check payment confirmation status"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/exchange/payment-status/{payment_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get('status', 'unknown')
                
                if status == 'confirmed':
                    success(f"Payment {payment_id} is confirmed!")
                    success(f"AITBC amount: {status_data.get('aitbc_amount', 0)}")
                elif status == 'pending':
                    success(f"Payment {payment_id} is pending confirmation")
                elif status == 'expired':
                    error(f"Payment {payment_id} has expired")
                else:
                    success(f"Payment {payment_id} status: {status}")
                
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get payment status: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.command()
@click.pass_context
def market_stats(ctx):
    """Get exchange market statistics"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/exchange/market-stats",
                timeout=10
            )
            
            if response.status_code == 200:
                stats = response.json()
                success("Exchange market statistics:")
                output(stats, ctx.obj['output_format'])
            else:
                error(f"Failed to get market stats: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@exchange.group()
def wallet():
    """Bitcoin wallet operations"""
    pass


@wallet.command()
@click.pass_context
def balance(ctx):
    """Get Bitcoin wallet balance"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/exchange/wallet/balance",
                timeout=10
            )
            
            if response.status_code == 200:
                balance_data = response.json()
                success("Bitcoin wallet balance:")
                output(balance_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get wallet balance: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")


@wallet.command()
@click.pass_context
def info(ctx):
    """Get comprehensive Bitcoin wallet information"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/exchange/wallet/info",
                timeout=10
            )
            
            if response.status_code == 200:
                wallet_info = response.json()
                success("Bitcoin wallet information:")
                output(wallet_info, ctx.obj['output_format'])
            else:
                error(f"Failed to get wallet info: {response.status_code}")
    except Exception as e:
        error(f"Network error: {e}")
