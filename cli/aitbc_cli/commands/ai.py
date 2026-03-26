import os
import subprocess
import sys
import uuid
import click
import httpx
from pydantic import BaseModel

@click.group(name='ai')
def ai_group():
    """AI marketplace commands."""
    pass

@ai_group.command()
@click.option('--port', default=8008, show_default=True, help='AI provider port')
@click.option('--model', default='qwen3:8b', show_default=True, help='Ollama model name')
@click.option('--wallet', 'provider_wallet', required=True, help='Provider wallet address (for verification)')
@click.option('--marketplace-url', default='http://127.0.0.1:8014', help='Marketplace API base URL')
def status(port, model, provider_wallet, marketplace_url):
    """Check AI provider service status."""
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5.0)
        if resp.status_code == 200:
            health = resp.json()
            click.echo(f"✅ AI Provider Status: {health.get('status', 'unknown')}")
            click.echo(f"   Model: {health.get('model', 'unknown')}")
            click.echo(f"   Wallet: {health.get('wallet', 'unknown')}")
        else:
            click.echo(f"❌ AI Provider not responding (status: {resp.status_code})")
    except httpx.ConnectError:
        click.echo(f"❌ AI Provider not running on port {port}")
    except Exception as e:
        click.echo(f"❌ Error checking AI Provider: {e}")

@ai_group.command()
@click.option('--port', default=8008, show_default=True, help='AI provider port')
@click.option('--model', default='qwen3:8b', show_default=True, help='Ollama model name')
@click.option('--wallet', 'provider_wallet', required=True, help='Provider wallet address (for verification)')
@click.option('--marketplace-url', default='http://127.0.0.1:8014', help='Marketplace API base URL')
def start(port, model, provider_wallet, marketplace_url):
    """Start AI provider service - provides setup instructions"""
    click.echo(f"AI Provider Service Setup:")
    click.echo(f"   Port: {port}")
    click.echo(f"   Model: {model}")
    click.echo(f"   Wallet: {provider_wallet}")
    click.echo(f"   Marketplace: {marketplace_url}")
    
    click.echo("\n📋 To start the AI Provider service:")
    click.echo(f"   1. Create systemd service: /etc/systemd/system/aitbc-ai-provider.service")
    click.echo(f"   2. Run: sudo systemctl daemon-reload")
    click.echo(f"   3. Run: sudo systemctl enable aitbc-ai-provider")
    click.echo(f"   4. Run: sudo systemctl start aitbc-ai-provider")
    click.echo(f"\n💡 Use 'aitbc ai status --port {port}' to verify service is running")

@ai_group.command()
def stop():
    """Stop AI provider service - provides shutdown instructions"""
    click.echo("📋 To stop the AI Provider service:")
    click.echo("   1. Run: sudo systemctl stop aitbc-ai-provider")
    click.echo("   2. Run: sudo systemctl status aitbc-ai-provider (to verify)")
    click.echo("\n💡 Use 'aitbc ai status' to check if service is stopped")

@ai_group.command()
@click.option('--to', required=True, help='Provider host (IP)')
@click.option('--port', default=8008, help='Provider port')
@click.option('--prompt', required=True, help='Prompt to send')
@click.option('--buyer-wallet', 'buyer_wallet', required=True, help='Buyer wallet name (in local wallet store)')
@click.option('--provider-wallet', 'provider_wallet', required=True, help='Provider wallet address (recipient)')
@click.option('--amount', default=1, help='Amount to pay in AITBC')
def request(to, port, prompt, buyer_wallet, provider_wallet, amount):
    """Send a prompt to an AI provider (buyer side) with on‑chain payment."""
    # Helper to get provider balance
    def get_balance():
        res = subprocess.run([
            sys.executable, "-m", "aitbc_cli.main", "blockchain", "balance",
            "--address", provider_wallet
        ], capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if "Balance:" in line:
                parts = line.split(":")
                return float(parts[1].strip())
        raise ValueError("Balance not found")

    # Step 1: get initial balance
    before = get_balance()
    click.echo(f"Provider balance before: {before}")

    # Step 2: send payment via blockchain CLI (use current Python env)
    if amount > 0:
        click.echo(f"Sending {amount} AITBC from wallet '{buyer_wallet}' to {provider_wallet}...")
        try:
            subprocess.run([
                sys.executable, "-m", "aitbc_cli.main", "blockchain", "send",
                "--from", buyer_wallet,
                "--to", provider_wallet,
                "--amount", str(amount)
            ], check=True, capture_output=True, text=True)
            click.echo("Payment sent.")
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"Blockchain send failed: {e.stderr}")

    # Step 3: get new balance
    after = get_balance()
    click.echo(f"Provider balance after: {after}")
    delta = after - before
    click.echo(f"Balance delta: {delta}")

    # Step 4: call provider
    url = f"http://{to}:{port}/job"
    payload = {
        "prompt": prompt,
        "buyer": provider_wallet,
        "amount": amount
    }
    try:
        resp = httpx.post(url, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        click.echo("Result: " + data.get("result", ""))
    except httpx.HTTPError as e:
        raise click.ClickException(f"Request to provider failed: {e}")

if __name__ == '__main__':
    ai_group()
