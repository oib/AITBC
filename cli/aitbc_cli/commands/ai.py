import os
import subprocess
import sys
import uuid
import click
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

@click.group(name='ai')
def ai_group():
    """AI marketplace commands."""
    pass

@ai_group.command()
@click.option('--port', default=8008, show_default=True, help='Port to listen on')
@click.option('--model', default='qwen3:8b', show_default=True, help='Ollama model name')
@click.option('--wallet', 'provider_wallet', required=True, help='Provider wallet address (for verification)')
@click.option('--marketplace-url', default='http://127.0.0.1:8014', help='Marketplace API base URL')
def serve(port, model, provider_wallet, marketplace_url):
    """Start AI provider daemon (FastAPI server)."""
    click.echo(f"Starting AI provider on port {port}, model {model}, marketplace {marketplace_url}")

    app = FastAPI(title="AI Provider")

    class JobRequest(BaseModel):
        prompt: str
        buyer: str  # buyer wallet address
        amount: int
        txid: str | None = None  # optional transaction id

    class JobResponse(BaseModel):
        result: str
        model: str
        job_id: str | None = None

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": model, "wallet": provider_wallet}

    @app.post("/job")
    async def handle_job(req: JobRequest):
        click.echo(f"Received job from {req.buyer}: {req.prompt[:50]}...")
        # Generate a job_id
        job_id = str(uuid.uuid4())
        # Register job with marketplace (optional, best-effort)
        try:
            async with httpx.AsyncClient() as client:
                create_resp = await client.post(
                    f"{marketplace_url}/v1/jobs",
                    json={
                        "payload": {"prompt": req.prompt, "model": model},
                        "constraints": {},
                        "payment_amount": req.amount,
                        "payment_currency": "AITBC"
                    },
                    headers={"X-Api-Key": ""},  # optional API key
                    timeout=5.0
                )
                if create_resp.status_code in (200, 201):
                    job_data = create_resp.json()
                    job_id = job_data.get("job_id", job_id)
                    click.echo(f"Registered job {job_id} with marketplace")
                else:
                    click.echo(f"Marketplace job registration failed: {create_resp.status_code}", err=True)
        except Exception as e:
            click.echo(f"Warning: marketplace registration skipped: {e}", err=True)
        # Process with Ollama
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://127.0.0.1:11434/api/generate",
                    json={"model": model, "prompt": req.prompt, "stream": False},
                    timeout=60.0
                )
                resp.raise_for_status()
                data = resp.json()
                result = data.get("response", "")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Ollama error: {e}")
        # Update marketplace with result (if registered)
        try:
            async with httpx.AsyncClient() as client:
                patch_resp = await client.patch(
                    f"{marketplace_url}/v1/jobs/{job_id}",
                    json={"result": result, "state": "completed"},
                    timeout=5.0
                )
                if patch_resp.status_code == 200:
                    click.echo(f"Updated job {job_id} with result")
        except Exception as e:
            click.echo(f"Warning: failed to update job in marketplace: {e}", err=True)
        return JobResponse(result=result, model=model, job_id=job_id)

    uvicorn.run(app, host="0.0.0.0", port=port)

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
