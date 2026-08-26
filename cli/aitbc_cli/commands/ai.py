"""AI job submission and inspection commands for AITBC CLI"""

import builtins
import os
import time
from decimal import Decimal, InvalidOperation
import json

from aitbc.crypto.crypto import sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from eth_utils import keccak

from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import wallet_dir

from typing import Any

import click

from aitbc.compliance.policies import (
    load_policy_template,
    normalize_classification,
)

from ..config import get_config
from ..utils import output, success, warning
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED", "EXPIRED"}


def _auth_headers(ctx) -> dict[str, str] | None:
    """Return Authorization header from --api-key or the stored credential."""
    token = ctx.obj.get("api_key")
    if not token:
        from ..auth import AuthManager

        token = AuthManager().get_credential("client")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path.

    The coordinator routers are mounted under /v1, and the endpoints below
    use /v1/... paths. If the configured URL already ends in /v1, strip it
    to avoid doubling the path.
    """
    config = get_config()
    url = coordinator_url or ctx.obj.get("url") or config.coordinator_api_url or "http://localhost:8203"
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _canonical_address_or_abort(ctx, address: str | None, label: str) -> str:
    if not address:
        abort(ctx, f"{label} address is required")
    assert address is not None
    try:
        return canonical_address(address)
    except Exception as e:
        abort(ctx, f"Invalid {label} address {address}: {e}")


def _load_wallet(ctx, wallet: str | None, password: str | None):
    if not wallet:
        return None, None
    wallet_path = wallet_dir() / f"{wallet}.json"
    if not wallet_path.exists():
        abort(ctx, f"Wallet not found: {wallet_path}")
    try:
        with open(wallet_path) as f:
            data = json.load(f)
    except Exception as e:
        abort(ctx, f"Failed to load wallet {wallet}: {e}")
    address = data.get("address")
    if not address:
        abort(ctx, f"Wallet {wallet} has no address")
    private_key = data.get("private_key")
    if isinstance(private_key, dict):
        if not password:
            abort(ctx, f"Wallet {wallet} is encrypted; --password required")
        assert password is not None
        try:
            private_key = decrypt_private_key(wallet_path, password)
        except Exception as e:
            abort(ctx, f"Failed to decrypt wallet {wallet}: {e}")
    elif not isinstance(private_key, str) or not private_key:
        abort(ctx, f"Wallet {wallet} has no usable private key")
    return address, private_key


def _get_rpc_client(rpc_url: str) -> AITBCHTTPClient:
    return AITBCHTTPClient(base_url=rpc_url, timeout=10)


def _get_node_wallet(ctx, rpc_url: str) -> str:
    client = _get_rpc_client(rpc_url)
    try:
        health = client.get("/health")
    except NetworkError as e:
        abort(ctx, f"Cannot reach blockchain RPC at {rpc_url}: {e}")
    proposer_id = health.get("proposer_id")
    if not proposer_id:
        abort(ctx, "Blockchain RPC /health did not return proposer_id (node wallet)")
    return _canonical_address_or_abort(ctx, proposer_id, "node wallet")


def _get_buyer_nonce(ctx, rpc_url: str, buyer: str) -> int:
    client = _get_rpc_client(rpc_url)
    try:
        account = client.get(f"/rpc/account/{buyer}")
    except NetworkError:
        return 0
    except Exception:
        return 0
    return int(account.get("nonce", 0))


def _ait_to_seconds(amount_ait: Decimal) -> int:
    seconds = int(amount_ait * 3600)
    return seconds if seconds > 0 else int(amount_ait)


def _build_escrow_lock_tx(
    ctx,
    job_id: str,
    buyer: str,
    provider: str,
    node_wallet: str,
    amount_ait: Decimal,
    nonce: int,
    fee: int | None = None,
    chain_id: str = "ait-hub.aitbc.bubuit.net",
) -> dict[str, Any]:
    try:
        node_wallet = canonical_address(node_wallet)
    except Exception as e:
        abort(ctx, f"Invalid node wallet address {node_wallet}: {e}")
    amount_seconds = _ait_to_seconds(amount_ait)
    if fee is None:
        fee = max(36, amount_seconds // 100)
    return {
        "from": buyer,
        "to": node_wallet,
        "amount": amount_seconds,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": chain_id,
        "payload": {
            "action": "escrow_lock",
            "job_id": job_id,
            "provider": provider,
        },
    }


def _sign_escrow_lock_tx(lock_tx: dict[str, Any], private_key: str) -> str:
    has_amount = "amount" in lock_tx
    tx_for_sign = {k: v for k, v in lock_tx.items() if k not in ("signature", "sig") and not (has_amount and k == "value")}
    canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
    tx_hash = "0x" + keccak(canonical).hex()
    return sign_transaction_hash(tx_hash, private_key)


def _create_escrow_payment(
    ctx,
    coord_http_client: AITBCHTTPClient,
    rpc_url: str,
    job_id: str,
    amount,
    token: str,
    buyer_address: str,
    provider_address: str,
    private_key: str,
    node_wallet: str,
    chain_id: str | None,
    offer_id: str | None,
    offer_quantity: Decimal | None,
) -> dict[str, Any]:
    buyer_canon = _canonical_address_or_abort(ctx, buyer_address, "buyer")
    provider_canon = _canonical_address_or_abort(ctx, provider_address, "provider")
    nonce = _get_buyer_nonce(ctx, rpc_url, buyer_canon)
    try:
        amount_ait = Decimal(str(amount))
    except InvalidOperation:
        abort(ctx, f"Invalid payment amount: {amount}")
    lock_tx = _build_escrow_lock_tx(
        ctx,
        job_id,
        buyer_canon,
        provider_canon,
        node_wallet,
        amount_ait,
        nonce,
        chain_id=chain_id or "ait-hub.aitbc.bubuit.net",
    )
    signature = _sign_escrow_lock_tx(lock_tx, private_key)
    payload: dict[str, Any] = {
        "job_id": job_id,
        "amount": str(amount_ait),
        "currency": token,
        "payment_method": "aitbc_token",
        "buyer_address": buyer_canon,
        "provider_address": provider_canon,
        "buyer_lock_signature": signature,
        "buyer_lock_nonce": nonce,
        "buyer_lock_fee": lock_tx["fee"],
        "escrow_timeout_seconds": 3600,
    }
    if offer_id:
        payload["offer_id"] = offer_id
    if offer_quantity is not None:
        payload["offer_quantity"] = str(offer_quantity)
    return coord_http_client.post("/v1/payments", json=payload)


def _wait_for_job(
    ctx,
    http_client: AITBCHTTPClient,
    job_id: str,
    payment_id: str | None,
    timeout: float,
    poll_interval: float,
    output_format: str,
) -> None:
    """Poll job status until terminal, then wait for payment release if needed."""
    click.echo(f"Waiting for job {job_id} (timeout: {timeout}s, poll: {poll_interval}s)")
    started = time.time()
    status: dict[str, Any] = {}
    state = "QUEUED"

    def _timed_out() -> bool:
        return time.time() - started >= timeout

    try:
        while state not in _TERMINAL_STATES:
            if _timed_out():
                abort(ctx, f"Timed out waiting for job {job_id}; last state: {state}")
            time.sleep(poll_interval)
            try:
                status = http_client.get(f"/v1/jobs/{job_id}")
            except NetworkError as e:
                abort(ctx, f"Network error while waiting for job {job_id}: {e}", from_exception=e)
            state = status.get("state", state)

        # For paid jobs, the miner triggers escrow release after submitting the
        # result. Allow a short extra window for payment_status to flip.
        if payment_id and state == "COMPLETED":
            while status.get("payment_status") != "released":
                if _timed_out():
                    abort(
                        ctx,
                        f"Job {job_id} completed but payment {payment_id} was not released within timeout",
                    )
                time.sleep(min(poll_interval, 2.0))
                try:
                    status = http_client.get(f"/v1/jobs/{job_id}")
                except NetworkError as e:
                    abort(ctx, f"Network error while waiting for payment release: {e}", from_exception=e)
                state = status.get("state", state)
                if state != "COMPLETED":
                    break

        if state == "COMPLETED":
            try:
                result_data = http_client.get(f"/v1/jobs/{job_id}/result")
            except NetworkError as e:
                result_data = None
                logger.warning("Could not fetch result for %s: %s", job_id, e)

            escrow_tx_hash: str | None = None
            if payment_id and status.get("payment_status") == "released":
                try:
                    payment = http_client.get(f"/v1/jobs/{job_id}/payment")
                    escrow_tx_hash = payment.get("transaction_hash")
                except NetworkError as e:
                    logger.warning("Could not fetch payment for %s: %s", job_id, e)
                except Exception:
                    pass

            completed_at: str | None = None
            if isinstance((result_data or {}).get("receipt"), dict):
                completed_at = result_data["receipt"].get("timestamp")  # type: ignore[index]

            output(
                {
                    "job_id": job_id,
                    "state": state,
                    "payment_id": payment_id,
                    "payment_status": status.get("payment_status"),
                    "escrow_tx_hash": escrow_tx_hash,
                    "result": result_data,
                    "receipt": (result_data or {}).get("receipt"),
                    "completed_at": completed_at,
                    "status": status,
                },
                output_format,
                title=f"Job completed: {job_id}",
            )
        else:
            output(
                {
                    "job_id": job_id,
                    "state": state,
                    "payment_id": payment_id,
                    "payment_status": status.get("payment_status"),
                    "status": status,
                },
                output_format,
                title=f"Job finished with {state}",
            )
    except KeyboardInterrupt:
        click.echo(f"\nInterrupted; cancelling job {job_id} if still active...")
        try:
            http_client.post(f"/v1/jobs/{job_id}/cancel")
        except Exception as e:
            logger.warning("Could not cancel job %s after interrupt: %s", job_id, e)
        abort(ctx, f"Wait for job {job_id} cancelled by user")


@click.group()
def ai():
    """AI job submission and inspection"""
    pass


@ai.command()
@click.option("--wallet", help="Wallet name")
@click.option("--type", "job_type", help="Job type")
@click.option("--prompt", help="Job prompt")
@click.option("--model", help="Ollama model to use")
@click.option("--payment", type=float, help="Payment amount")
@click.option("--currency", default=None, help="Payment currency (default: AITBC)")
@click.option("--buyer-address", help="Customer wallet address for escrow")
@click.option("--provider-address", help="Provider wallet address for escrow")
@click.option("--offer-id", help="Marketplace offer this job is bought against")
@click.option("--offer-quantity", type=Decimal, default=None, help="How many of the offer's price units to buy (default: 1)")
@click.option(
    "--acceptance-window", type=int, default=None, help="Seconds after completion before payment auto-releases (default: 0)"
)
@click.option("--min-reputation", type=float, help="Minimum provider reputation score (0-1) required for this job")
@click.option(
    "--zk-proof-required/--no-zk-proof-required", default=False, help="Require a ZK receipt proof before escrow release"
)
@click.option(
    "--tee-attestation-required/--no-tee-attestation-required",
    default=False,
    help="Require a TEE attestation before escrow release",
)
@click.option("--tee-enclave-id", default=None, help="Required TEE enclave identity")
@click.option("--confidential", is_flag=True, help="Mark this job as confidential (requires a TEE attestation)")
@click.option("--enclave-measurement", default=None, help="Required enclave measurement for a confidential job")
@click.option(
    "--auto-reinvest-pct", type=float, default=None, help="Percentage of released payment to auto-stake as reinvestment"
)
@click.option(
    "--bond-required/--no-bond-required",
    default=False,
    help="Require the provider to have an active performance bond",
)
@click.option("--min-bond-amount", type=float, default=None, help="Minimum bond amount required for provider eligibility")
@click.option("--input", "input_url", help="Input URL or path for transcribe/reencode jobs")
@click.option("--output-format", default=None, help="Output format for reencode jobs (e.g. mp4, mp3)")
@click.option("--classification", default=None, help="Data classification label (e.g. public, pii, phi)")
@click.option(
    "--compliance-framework", default=None, envvar="AITBC_COMPLIANCE_FRAMEWORK", help="Compliance framework to enforce"
)
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Password file")
@click.option("--chain-id", help="Chain ID")
@click.option("--rpc-url", help="RPC URL")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--wait", is_flag=True, help="Wait for the job to reach a terminal state")
@click.option("--timeout", type=float, default=300, help="Maximum seconds to wait for a terminal state (default: 300)")
@click.option("--poll-interval", type=float, default=5, help="Seconds between status polls (default: 5)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def submit(
    ctx,
    wallet,
    job_type,
    prompt,
    model,
    payment,
    currency,
    buyer_address,
    provider_address,
    offer_id,
    offer_quantity,
    acceptance_window,
    min_reputation,
    zk_proof_required,
    tee_attestation_required,
    tee_enclave_id,
    confidential,
    enclave_measurement,
    auto_reinvest_pct,
    bond_required,
    min_bond_amount,
    input_url,
    output_format,
    classification,
    compliance_framework,
    password,
    password_file,
    chain_id,
    rpc_url,
    coordinator_url,
    wait,
    timeout,
    poll_interval,
    format,
):
    """Submit an AI job"""
    config = get_config()

    try:
        # Get coordinator URL
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        rpc_url = rpc_url or config.blockchain_rpc_url or "http://localhost:8202"
        if not rpc_url:
            abort(ctx, "RPC URL not configured")

        if password_file:
            with open(password_file) as f:
                password = f.read().strip() or password

        wallet_address, private_key = _load_wallet(ctx, wallet, password)

        # Prepare job data in the JobCreate shape expected by coordinator-api
        job_type = job_type or "inference"
        payload = {
            "type": job_type,
        }

        if job_type == "inference":
            payload["prompt"] = prompt or ""
            if model:
                payload["model"] = model
        elif job_type in ("transcribe", "reencode"):
            if input_url:
                payload["url"] = input_url
            if model:
                payload["model"] = model
            if output_format:
                payload["output_format"] = output_format
            if prompt:
                payload["prompt"] = prompt
        else:
            if prompt:
                payload["prompt"] = prompt
            if model:
                payload["model"] = model

        job_data = {
            "payload": payload,
            "constraints": {},
            "ttl_seconds": 900,
        }

        # Compliance hook
        if compliance_framework:
            framework = compliance_framework
            policy = load_policy_template(framework)
            if classification:
                label = normalize_classification(classification)
                if not policy.allows_classification(label):
                    abort(ctx, f"Classification '{label.value}' is not allowed by framework '{framework}'")
                job_data["constraints"]["data_classification"] = label.value
            else:
                abort(ctx, f"--classification is required when --compliance-framework is set ({framework})")

        if min_reputation is not None:
            job_data["constraints"]["min_reputation"] = min_reputation

        if zk_proof_required:
            job_data["constraints"]["zk_proof_required"] = True

        if tee_attestation_required:
            job_data["constraints"]["tee_attestation_required"] = True
        if tee_enclave_id:
            job_data["constraints"]["tee_enclave_id"] = tee_enclave_id
        if confidential:
            job_data["constraints"]["confidential"] = True
            job_data["constraints"]["tee_attestation_required"] = True
        if enclave_measurement:
            job_data["constraints"]["required_enclave_measurement"] = enclave_measurement
            job_data["constraints"]["tee_enclave_id"] = enclave_measurement

        if auto_reinvest_pct is not None:
            job_data["constraints"]["auto_reinvest_pct"] = auto_reinvest_pct

        if bond_required:
            job_data["constraints"]["bond_required"] = True
        if min_bond_amount is not None:
            job_data["constraints"]["min_bond_amount"] = min_bond_amount

        if offer_id:
            job_data["offer_id"] = offer_id
            if offer_quantity is not None:
                job_data["offer_quantity"] = str(offer_quantity)
        if acceptance_window is not None:
            job_data["constraints"]["acceptance_window_seconds"] = acceptance_window

        if payment or offer_id:
            if not buyer_address and wallet_address:
                buyer_address = wallet_address
            if not buyer_address:
                abort(
                    ctx, "buyer_address is required for paid jobs: set --wallet, --buyer-address, or CUSTOMER_WALLET_ADDRESS"
                )
            job_data["buyer_address"] = buyer_address
            if payment:
                job_data["payment_amount"] = str(Decimal(str(payment)))
            job_data["payment_currency"] = currency or "AITBC"
            if provider_address or os.environ.get("SHOP_WALLET_ADDRESS"):
                job_data["provider_address"] = provider_address or os.environ.get("SHOP_WALLET_ADDRESS")

        # Submit to coordinator
        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post("/v1/jobs", json=job_data)

        job_id = result.get("job_id")
        payment_id = result.get("payment_id")
        success(f"Job submitted: {job_id}")

        # If the coordinator priced the job but did not secure an escrow, sign the
        # ESCROW_LOCK tx and create the payment in a second step.
        if not payment_id and result.get("payment_amount") and private_key:
            node_wallet_addr = result.get("node_wallet_address")
            if not node_wallet_addr:
                abort(ctx, "coordinator did not return node_wallet_address; cannot build ESCROW_LOCK")
            payment_amount = result.get("payment_amount")
            if payment_amount is None:
                abort(ctx, "coordinator did not return payment_amount")
            payment_token = str(result.get("payment_token") or currency or "AITBC")
            payment_result = _create_escrow_payment(
                ctx,
                http_client,
                rpc_url,
                job_id,
                str(payment_amount),
                payment_token,
                buyer_address,
                str(result.get("provider_address") or provider_address or os.environ.get("SHOP_WALLET_ADDRESS") or ""),
                private_key,
                str(node_wallet_addr),
                chain_id or config.chain_id,
                offer_id,
                offer_quantity,
            )
            payment_id = payment_result.get("payment_id")
            success(f"Escrow secured: {payment_id}")

        if not wait:
            output(result, ctx.obj.get("output_format", format))
            return

        _wait_for_job(
            ctx,
            http_client,
            job_id,
            payment_id,
            timeout,
            poll_interval,
            ctx.obj.get("output_format", format),
        )

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error submitting job: {e}", from_exception=e)


@ai.command(name="pay")
@click.option("--job-id", required=True, help="Job ID to pay for")
@click.option("--wallet", required=True, help="Wallet name to sign the escrow lock")
@click.option("--buyer-address", help="Override buyer/customer address")
@click.option("--provider-address", help="Override provider address")
@click.option("--offer-id", help="Marketplace offer this job is bought against")
@click.option("--offer-quantity", type=Decimal, default=None, help="How many of the offer's price units to buy")
@click.option("--currency", default=None, help="Payment currency (default: AITBC)")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--chain-id", help="Chain ID")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Password file")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def pay(
    ctx,
    job_id,
    wallet,
    buyer_address,
    provider_address,
    offer_id,
    offer_quantity,
    currency,
    coordinator_url,
    rpc_url,
    chain_id,
    password,
    password_file,
    format,
):
    """Create an escrow payment for an existing job (two-step payment flow)."""
    config = get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        rpc_url = rpc_url or config.blockchain_rpc_url or "http://localhost:8202"
        if not rpc_url:
            abort(ctx, "RPC URL not configured")

        if password_file:
            with open(password_file) as f:
                password = f.read().strip() or password

        wallet_address, private_key = _load_wallet(ctx, wallet, password)
        if not private_key:
            abort(ctx, f"Wallet {wallet} has no usable private key")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        job = http_client.get(f"/v1/jobs/{job_id}")
        if not isinstance(job, dict) or not job.get("job_id"):
            abort(ctx, f"Job {job_id} not found")

        if job.get("payment_id") and job.get("payment_status") not in ("pending", "skipped", None):
            abort(ctx, f"Job {job_id} already has payment_status={job.get('payment_status')}; not creating a second payment")

        payment_amount = job.get("payment_amount")
        if payment_amount is None:
            abort(ctx, "Job has no payment_amount; it may not be a paid job")

        node_wallet_addr = job.get("node_wallet_address") or _get_node_wallet(ctx, rpc_url)
        if not node_wallet_addr:
            abort(ctx, "Cannot determine node wallet address for ESCROW_LOCK")

        buyer_address = buyer_address or job.get("buyer_address") or wallet_address
        if not buyer_address:
            abort(ctx, "buyer_address is required: set --buyer-address, --wallet, or ensure the job has one")

        provider_address = provider_address or job.get("provider_address") or os.environ.get("SHOP_WALLET_ADDRESS")
        if not provider_address:
            abort(ctx, "provider_address is required: set --provider-address or ensure the job has one")

        offer_id = offer_id or job.get("offer_id")
        if offer_quantity is None:
            offer_quantity = job.get("offer_quantity")

        payment_result = _create_escrow_payment(
            ctx,
            http_client,
            rpc_url,
            job_id,
            str(payment_amount),
            currency or job.get("payment_token") or "AITBC",
            buyer_address,
            provider_address,
            private_key,
            str(node_wallet_addr),
            chain_id or config.chain_id,
            offer_id,
            Decimal(str(offer_quantity)) if offer_quantity is not None else None,
        )

        success(f"Escrow secured: {payment_result.get('payment_id')}")
        output(payment_result, ctx.obj.get("output_format", format))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error paying for job: {e}", from_exception=e)


@ai.command()
@click.option("--limit", type=int, default=10, help="Limit results")
@click.option("--status", help="Filter by status")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def jobs(ctx, limit, status, coordinator_url, format):
    """List AI jobs"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        params = {"limit": limit}
        if status:
            params["status"] = status

        result = http_client.get("/v1/jobs", params=params)
        output(result, ctx.obj.get("output_format", format), title="AI Jobs")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing jobs: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, job_id, coordinator_url, format):
    """Show AI job status"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}")

        output(result, ctx.obj.get("output_format", format), title=f"Job Status: {job_id}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting job status: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", required=True, help="Job ID to accept")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def accept(ctx, job_id, coordinator_url, format):
    """Accept a completed job and release the escrowed payment."""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/jobs/{job_id}/accept")

        success(f"Job {job_id} accepted and payment released")
        output(result, ctx.obj.get("output_format", format))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error accepting job: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", required=True, help="Job ID to refund")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.option("--coordinator-url", help="Coordinator URL")
@click.pass_context
def refund(ctx, job_id, reason, coordinator_url):
    """Refund an escrowed payment for a failed or cancelled job."""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        # Lookup payment_id for this job.
        job = http_client.get(f"/v1/jobs/{job_id}")
        payment_id = job.get("payment_id")
        if not payment_id:
            abort(ctx, f"Job {job_id} has no payment to refund")

        result = http_client.post(
            f"/v1/payments/{payment_id}/refund",
            json={"job_id": job_id, "payment_id": payment_id, "reason": reason},
        )
        success(f"Payment {payment_id} for job {job_id} refunded")
        output(result, ctx.obj.get("output_format", "table"))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error refunding job: {e}", from_exception=e)


@ai.command(name="refund-sweep")
@click.option("--limit", type=int, default=100, help="Maximum completed jobs to inspect")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.option("--dry-run", is_flag=True, help="Count candidates without refunding")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def refund_sweep(ctx, limit, reason, dry_run, coordinator_url, format):
    """Refund all client-owned jobs stuck in escrowed/pending_acceptance with failed ZK."""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        result = http_client.get("/v1/jobs", params={"status": "COMPLETED", "limit": limit})
        jobs = result.get("items") if isinstance(result, dict) else result
        if not isinstance(jobs, builtins.list):
            abort(ctx, "Unexpected response listing jobs")
        assert jobs is not None

        counts = {"candidates": 0, "refunded": 0, "failed": 0}
        for job in jobs:
            payment_status = job.get("payment_status")
            if payment_status not in ("escrowed", "pending_acceptance"):
                continue
            if job.get("zk_status") == "verified":
                continue
            payment_id = job.get("payment_id")
            job_id = job.get("job_id")
            if not payment_id or not job_id:
                continue
            counts["candidates"] += 1
            if dry_run:
                continue
            try:
                http_client.post(
                    f"/v1/payments/{payment_id}/refund",
                    json={"job_id": job_id, "payment_id": payment_id, "reason": reason},
                )
                counts["refunded"] += 1
                success(f"Refunded payment {payment_id} for job {job_id}")
            except NetworkError as e:
                counts["failed"] += 1
                warning(f"Failed to refund payment {payment_id} for job {job_id}: {e}")
            except Exception as e:
                counts["failed"] += 1
                warning(f"Failed to refund payment {payment_id} for job {job_id}: {e}")

        output(counts, ctx.obj.get("output_format", format), title="ZK refund sweep")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error running refund sweep: {e}", from_exception=e)


@ai.group()
def service():
    """AI service management"""
    pass


@service.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, coordinator_url, format):
    """List available AI services"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/services")

        output(result, ctx.obj.get("output_format", format), title="AI Services")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing services: {e}", from_exception=e)


@service.command()
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def service_status(ctx, name, coordinator_url, format):
    """Check AI service status"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not name:
            abort(ctx, "Service name required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/services/{name}")

        output(result, ctx.obj.get("output_format", format), title=f"Service Status: {name}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting service status: {e}", from_exception=e)


@service.command()
@click.option("--name", help="Service name")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def test(ctx, name, coordinator_url, format):
    """Test AI service endpoint"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not name:
            abort(ctx, "Service name required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/services/{name}/test")

        success(f"Service {name} test completed")
        output(result, ctx.obj.get("output_format", format), title=f"Service Test: {name}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error testing service: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def results(ctx, job_id, coordinator_url, format):
    """Show AI job results"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get(f"/v1/jobs/{job_id}/result")

        output(result, ctx.obj.get("output_format", format), title=f"Job Results: {job_id}")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting job results: {e}", from_exception=e)


@ai.command()
@click.option("--job-id", help="Job ID")
@click.option("--wallet", required=True, help="Wallet name")
@click.option("--password", help="Wallet password")
@click.option("--password-file", type=click.Path(exists=True), help="Password file")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def cancel(ctx, job_id, wallet, password, password_file, coordinator_url, format):
    """Cancel AI job"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        if not job_id:
            abort(ctx, "Job ID required")

        # Get password
        if password_file:
            with open(password_file) as f:
                _ = f.read().strip()

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.post(f"/v1/jobs/{job_id}/cancel")

        success(f"Job {job_id} cancelled")
        output(result, ctx.obj.get("output_format", format))

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error cancelling job: {e}", from_exception=e)


@ai.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def stats(ctx, coordinator_url, format):
    """AI service statistics"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/stats")

        output(result, ctx.obj.get("output_format", format), title="AI Service Statistics")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting statistics: {e}", from_exception=e)


@ai.command()
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def distribution_stats(ctx, coordinator_url, format):
    """Task distribution statistics from agent coordinator"""
    get_config()

    try:
        coord_url = _coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            abort(ctx, "Coordinator URL not configured")

        headers = _auth_headers(ctx)
        http_client = AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)
        result = http_client.get("/v1/agent/stats/distribution")

        output(result, ctx.obj.get("output_format", format), title="Task Distribution Statistics")

    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting distribution statistics: {e}", from_exception=e)
