"""``aitbc ai submit`` — job submission, payload/constraint builders, and the --wait poller."""

import os
import time
import uuid
from decimal import Decimal
from typing import Any, cast

import click

import aitbc_cli.commands.ai as _ai

from ...utils.http_client import get_logger

from ._group import ai

logger = get_logger(__name__.rpartition(".")[0])

_TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED", "EXPIRED"}

# Statuses that mean "try again" rather than "the request was wrong": no
# response at all (DNS/TCP/timeout — the gateway or upstream is down), the
# whole 5xx range (gateway blips, upstream restarts), and the few 4xx that
# are explicitly transient (408 timeout, 425 too early, 429 rate limited).
_TRANSIENT_STATUSES = {408, 425, 429}


def _is_transient_error(e: _ai.NetworkError) -> bool:
    """True when the failure is a gateway/network blip worth retrying."""
    status = _ai.http_response_status(e)
    return status is None or status >= 500 or status in _TRANSIENT_STATUSES


def _abort_network_error(ctx, e: _ai.NetworkError) -> None:
    """Label submit failures honestly: server answered vs unreachable.

    A 4xx/5xx means the coordinator evaluated and rejected the request —
    reporting that as "Network error" misleads operators into checking
    connectivity for what is a client-input problem (#2216).
    """
    if _ai.is_unauthorized(e):
        _ai.abort(ctx, _ai._login_hint(ctx))
    status = _ai.http_response_status(e)
    detail = _ai.http_error_detail(e)
    if status is not None:
        _ai.abort(ctx, f"Server rejected the request (HTTP {status}): {detail or e}", from_exception=e)
    _ai.abort(ctx, f"Network error: {detail or e}", from_exception=e)


def _try_auto_accept(http_client: _ai.AITBCHTTPClient, job_id: str, accept_key: str) -> bool:
    """Attempt one idempotent accept; returns True if no retry is wanted."""
    try:
        _ai._post_idempotent(http_client, f"/v1/jobs/{job_id}/accept", idempotency_key=accept_key)
    except _ai.NetworkError as e:
        if _is_transient_error(e):
            # Gateway blip: retry the accept on the next poll — the
            # Idempotency-Key makes the replay safe.
            logger.warning("Transient error accepting job %s (will retry): %s", job_id, e)
            return False
        logger.warning("Could not auto-accept job %s: %s", job_id, e)
    except _ai._OPS_ERRORS as e:
        logger.warning("Could not auto-accept job %s: %s", job_id, e)
    return True


def _await_payment_release(
    ctx,
    http_client: _ai.AITBCHTTPClient,
    job_id: str,
    payment_id: str,
    status: dict[str, Any],
    state: str,
    timed_out,
    poll_interval: float,
) -> tuple[dict[str, Any], str]:
    """Wait briefly for the escrow release to land after job completion.

    For paid jobs, the miner triggers escrow release after submitting the
    result. Allow a short extra window for payment_status to flip; if the
    coordinator is holding the payment for customer acceptance, accept it
    on behalf of the customer so a --wait invocation runs end-to-end.
    """
    accept_attempted = False
    accept_key = _ai._new_idempotency_key(f"ai-accept-{job_id}")
    while status.get("payment_status") != "released":
        if timed_out():
            _ai.abort(
                ctx,
                f"Job {job_id} completed but payment {payment_id} was not released within timeout",
            )
        if not accept_attempted and status.get("payment_status") in ("escrowed", "pending_acceptance"):
            accept_attempted = _try_auto_accept(http_client, job_id, accept_key)
        time.sleep(min(poll_interval, 2.0))
        try:
            status = http_client.get(f"/v1/jobs/{job_id}")
        except _ai.NetworkError as e:
            if _is_transient_error(e):
                _ai.warning(f"Transient error polling job {job_id} (still waiting): {e}")
                continue
            _ai.abort(ctx, f"Network error while waiting for payment release: {e}", from_exception=e)
        state = status.get("state", state)
        if state != "COMPLETED":
            break
    return status, state


def _completed_job_payload(
    http_client: _ai.AITBCHTTPClient,
    job_id: str,
    payment_id: str | None,
    status: dict[str, Any],
    state: str,
) -> dict[str, Any]:
    """Fetch result and payment details for a completed job into the output dict."""
    try:
        result_data = http_client.get(f"/v1/jobs/{job_id}/result")
    except _ai.NetworkError as e:
        result_data = None
        logger.warning("Could not fetch result for %s: %s", job_id, e)

    escrow_tx_hash: str | None = None
    if payment_id and status.get("payment_status") == "released":
        try:
            payment = http_client.get(f"/v1/jobs/{job_id}/payment")
            escrow_tx_hash = payment.get("transaction_hash")
        except _ai.NetworkError as e:
            logger.warning("Could not fetch payment for %s: %s", job_id, e)
        except _ai._OPS_ERRORS:
            logger.debug("Could not fetch payment for %s", job_id, exc_info=True)

    completed_at: str | None = None
    if isinstance((result_data or {}).get("receipt"), dict):
        completed_at = result_data["receipt"].get("timestamp")  # type: ignore[index]

    return {
        "job_id": job_id,
        "state": state,
        "payment_id": payment_id,
        "payment_status": status.get("payment_status"),
        "escrow_tx_hash": escrow_tx_hash,
        "result": result_data,
        "receipt": (result_data or {}).get("receipt"),
        "completed_at": completed_at,
        "status": status,
    }


def _wait_for_job(
    ctx,
    http_client: _ai.AITBCHTTPClient,
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
                _ai.abort(ctx, f"Timed out waiting for job {job_id}; last state: {state}")
            time.sleep(poll_interval)
            try:
                status = http_client.get(f"/v1/jobs/{job_id}")
            except _ai.NetworkError as e:
                if _is_transient_error(e):
                    # A gateway 502/timeout must not abandon --wait: the job
                    # may still be sealing. Keep polling until the timeout.
                    _ai.warning(f"Transient error polling job {job_id} (still waiting): {e}")
                    continue
                _ai.abort(ctx, f"Network error while waiting for job {job_id}: {e}", from_exception=e)
            state = status.get("state", state)

        if payment_id and state == "COMPLETED":
            status, state = _await_payment_release(
                ctx, http_client, job_id, payment_id, status, state, _timed_out, poll_interval
            )

        if state == "COMPLETED":
            _ai.output(
                _completed_job_payload(http_client, job_id, payment_id, status, state),
                output_format,
                title=f"Job completed: {job_id}",
            )
        else:
            _ai.output(
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
            _ai._post_idempotent(
                http_client,
                f"/v1/jobs/{job_id}/cancel",
                idempotency_key=_ai._new_idempotency_key(f"ai-cancel-{job_id}"),
            )
        except _ai._OPS_ERRORS as e:
            logger.warning("Could not cancel job %s after interrupt: %s", job_id, e)
        _ai.abort(ctx, f"Wait for job {job_id} cancelled by user")


def _fill_media_payload(
    payload: dict[str, Any], http_client: _ai.AITBCHTTPClient, input_url, model, output_format, prompt
) -> None:
    """Fill transcribe/reencode payload fields, uploading local input first."""
    if input_url:
        media_url, filename = _ai._media_url(input_url, http_client)
        if media_url:
            payload["url"] = media_url
        if filename:
            payload["filename"] = filename
    if model:
        payload["model"] = model
    if output_format:
        payload["output_format"] = output_format
    if prompt:
        payload["prompt"] = prompt


def _submit_payload(
    http_client: _ai.AITBCHTTPClient,
    job_type: str,
    prompt: str | None,
    model: str | None,
    input_url: str | None,
    output_format: str | None,
) -> dict[str, Any]:
    """Build the job payload in the shape the coordinator expects per job type."""
    payload: dict[str, Any] = {"type": job_type}
    if job_type == "inference":
        payload["prompt"] = prompt or ""
        if model:
            payload["model"] = model
    elif job_type in ("transcribe", "reencode"):
        _fill_media_payload(payload, http_client, input_url, model, output_format, prompt)
    else:
        if prompt:
            payload["prompt"] = prompt
        if model:
            payload["model"] = model
    return payload


def _apply_compliance(ctx, constraints: dict[str, Any], compliance_framework, classification) -> None:
    """Validate and apply the data-classification constraint for a framework."""
    if not compliance_framework:
        return
    policy = _ai.load_policy_template(compliance_framework)
    if not classification:
        _ai.abort(ctx, f"--classification is required when --compliance-framework is set ({compliance_framework})")
    label = _ai.normalize_classification(classification)
    if not policy.allows_classification(label):
        _ai.abort(ctx, f"Classification '{label.value}' is not allowed by framework '{compliance_framework}'")
    constraints["data_classification"] = label.value


def _apply_simple_constraints(
    constraints: dict[str, Any],
    *,
    min_reputation,
    zk_proof_required,
    auto_reinvest_pct,
    bond_required,
    min_bond_amount,
    deterministic_decoding,
    decode_seed,
    acceptance_window,
) -> None:
    """Copy the flag/value options into the job's constraints dict."""
    if min_reputation is not None:
        constraints["min_reputation"] = min_reputation
    if zk_proof_required:
        constraints["zk_proof_required"] = True
    if auto_reinvest_pct is not None:
        constraints["auto_reinvest_pct"] = auto_reinvest_pct
    if bond_required:
        constraints["bond_required"] = True
    if min_bond_amount is not None:
        constraints["min_bond_amount"] = min_bond_amount
    if deterministic_decoding:
        constraints["deterministic_decoding"] = True
        if decode_seed is not None:
            constraints["decode_seed"] = decode_seed
    if acceptance_window is not None:
        constraints["acceptance_window_seconds"] = acceptance_window


def _apply_tee_constraints(
    ctx,
    constraints: dict[str, Any],
    config,
    *,
    tee_attestation_required,
    tee_enclave_id,
    confidential,
    enclave_measurement,
) -> None:
    """Apply TEE/confidentiality constraints after checking the feature flag."""
    tee_requested = tee_attestation_required or tee_enclave_id or confidential or enclave_measurement
    if tee_requested and not config.tee_attestation_enabled:
        _ai.abort(
            ctx,
            "TEE attestation is not enabled. Remove --confidential, --tee-attestation-required, "
            "--tee-enclave-id, and --enclave-measurement, or set TEE_ATTESTATION_ENABLED=true.",
        )
    if tee_attestation_required:
        constraints["tee_attestation_required"] = True
    if tee_enclave_id:
        constraints["tee_enclave_id"] = tee_enclave_id
    if confidential:
        constraints["confidential"] = True
        constraints["tee_attestation_required"] = True
    if enclave_measurement:
        constraints["required_enclave_measurement"] = enclave_measurement
        constraints["tee_enclave_id"] = enclave_measurement


def _apply_payment_fields(
    ctx,
    job_data: dict[str, Any],
    *,
    payment,
    currency,
    buyer_address,
    wallet_address,
    provider_address,
    offer_id,
    offer_quantity,
) -> None:
    """Attach offer reference and escrow fields for paid/bought jobs."""
    if offer_id:
        job_data["offer_id"] = offer_id
        if offer_quantity is not None:
            job_data["offer_quantity"] = str(offer_quantity)
    if not (payment or offer_id):
        return
    if not buyer_address and wallet_address:
        buyer_address = wallet_address
    if not buyer_address:
        _ai.abort(ctx, "buyer_address is required for paid jobs: set --wallet, --buyer-address, or CUSTOMER_WALLET_ADDRESS")
    job_data["buyer_address"] = buyer_address
    if payment:
        job_data["payment_amount"] = str(Decimal(str(payment)))
    job_data["payment_currency"] = currency or "AITBC"
    resolved_provider = provider_address or os.environ.get("SHOP_WALLET_ADDRESS")
    if resolved_provider:
        job_data["provider_address"] = resolved_provider
    elif not offer_id:
        # A paid job without an offer has no server-side provider
        # resolution — it would be created and queue forever.
        _ai.abort(
            ctx,
            "provider_address is required for paid jobs without --offer-id: set --provider-address or SHOP_WALLET_ADDRESS",
        )


def _attach_shop_access(ctx, job_data: dict[str, Any], *, model, payment, offer_id=None) -> None:
    """Mint a market-service access token for gated-shop job types (#2316).

    ``ai submit --type transcribe`` lands on the miner's whisper call, which
    is gated by per-job tokens only the market service can verify — and only
    the buyer-side CLI holds the user-tier key that mints them
    (``POST /v1/market/jobs``). Embed the credential triple in the payload so
    the miner forwards it verbatim (#1612). The market job id is deliberately
    distinct from the coordinator job id: it is a pure token record whose
    escrow binding can never alias the coordinator escrow.

    Paid submissions only (#2321): an unpaid transcribe job is dispatchable
    (``_payment_blocks_dispatch`` returns None when no payment is priced),
    so minting here would hand a free job a valid shop token. The predicate
    ``payment or offer_id`` matches the escrow path — an offer-bound submit
    is priced from the quote server-side — and mirrors the pre-flight check
    at the call site. The plaintext ``access_secret`` must stay in the
    payload: the miner has no market credential of its own and forwards the
    triple verbatim to the gated endpoint, which verifies it against the
    market service; the market row stores only the digest.
    """
    if job_data["payload"].get("type") != "transcribe":
        return
    if not (payment or offer_id):
        return
    from ..market.jobs import _register_paid_market_job

    market_job_id = f"ai_job_{uuid.uuid4().hex[:16]}"
    access = _register_paid_market_job(
        ctx,
        market_job_id,
        {"model": model or ""},
        str(job_data.get("buyer_address") or ""),
        str(job_data.get("provider_address") or ""),
        "whisper",
        Decimal(str(payment)) if payment else Decimal("0"),
    )
    if not access:
        _ai.warning("Shop access token unavailable — the transcribe job will likely fail at the gated whisper endpoint")
        return
    access_key, access_secret = access
    payload = job_data["payload"]
    payload["access_key"] = access_key
    payload["access_secret"] = access_secret
    payload["market_job_id"] = market_job_id


def _secure_escrow(
    ctx,
    http_client: _ai.AITBCHTTPClient,
    rpc_url: str,
    result: dict[str, Any],
    job_id: str,
    *,
    currency,
    buyer_address,
    provider_address,
    private_key,
    chain_id,
    offer_id,
    offer_quantity,
    idempotency_key=None,
    buyer_agent_id=None,
    provider_agent_id=None,
):
    """If the coordinator priced the job but did not secure an escrow, sign the
    ESCROW_LOCK tx and create the payment in a second step."""
    payment_id = result.get("payment_id")
    if payment_id or not result.get("payment_amount") or not private_key:
        return payment_id
    node_wallet_addr = result.get("node_wallet_address")
    if not node_wallet_addr:
        _ai.abort(ctx, "coordinator did not return node_wallet_address; cannot build ESCROW_LOCK")
    payment_amount = result.get("payment_amount")
    if payment_amount is None:
        _ai.abort(ctx, "coordinator did not return payment_amount")
    payment_token = str(result.get("payment_token") or currency or "AITBC")
    # Resolve the chain id in its own try: only this failure gets the
    # CHAIN_ID hint; other errors (amount, nonce, coordinator) get the bare
    # recovery hint. Resolution stays lazy — it runs only when an escrow is
    # actually needed, never for already-paid submissions.
    try:
        resolved_chain_id = chain_id or _ai.resolve_chain_id(ctx, rpc_url)
    except _ai.CLIError as e:
        _ai.abort(
            ctx,
            f"{e} — job {job_id} was accepted but its escrow could not be secured; "
            f"set CHAIN_ID and fund it with 'aitbc ai pay --job-id {job_id}'",
            from_exception=e,
        )
    try:
        payment_result = _ai._create_escrow_payment(
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
            resolved_chain_id,
            offer_id,
            offer_quantity,
            idempotency_key=idempotency_key,
            buyer_agent_id=buyer_agent_id,
            provider_agent_id=provider_agent_id,
        )
    except _ai.CLIError as e:
        # The job was already accepted by the coordinator; name it so the
        # operator can fund it instead of resubmitting.
        _ai.abort(
            ctx,
            f"{e} — job {job_id} was accepted but its escrow could not be secured; fund it with 'aitbc ai pay --job-id {job_id}'",
            from_exception=e,
        )
    payment_id = payment_result.get("payment_id")
    _ai.success(f"Escrow secured: {payment_id}")
    return payment_id


@ai.command(
    epilog="""Examples:

  aitbc ai submit --prompt 'transcribe audio'

  aitbc ai submit --prompt 'generate summary' --model gpt-4o --wallet genesis"""
)
@click.option("--wallet", help="Wallet name")
@click.option("--type", "job_type", help="Job type")
@click.option("--prompt", help="Job prompt")
@click.option("--model", help="Ollama model to use")
@click.option("--payment", type=float, help="Payment amount")
@click.option("--currency", default=None, help="Payment currency (default: AITBC)")
@click.option("--buyer-address", help="Customer wallet address for escrow")
@click.option("--provider-address", help="Provider wallet address for escrow")
@click.option("--buyer-agent-id", help="Buyer agent id; payment address resolved via coordinator")
@click.option("--provider-agent-id", help="Provider agent id; payment address resolved via coordinator")
@click.option("--offer-id", help="Market offer this job is bought against")
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
@click.option(
    "--deterministic-decoding/--no-deterministic-decoding",
    default=False,
    help="Use deterministic decoding for reproducible verification",
)
@click.option("--decode-seed", type=int, default=None, help="Seed for deterministic decoding (auto-assigned if unset)")
@click.option("--input", "input_url", help="Input URL or path for transcribe/reencode jobs")
@click.option("--output-format", default=None, help="Output format for reencode jobs (e.g. mp4, mp3)")
@click.option("--classification", default=None, help="Data classification label (e.g. public, pii, phi)")
@click.option(
    "--compliance-framework", default=None, envvar="AITBC_COMPLIANCE_FRAMEWORK", help="Compliance framework to enforce"
)
@_ai.wallet_password_options
@click.option("--chain-id", help="Chain ID")
@click.option("--rpc-url", help="RPC URL")
@click.option("--coordinator-url", help="Coordinator URL")
@click.option("--wait", is_flag=True, help="Wait for the job to reach a terminal state")
@click.option("--timeout", type=float, default=300, help="Maximum seconds to wait for a terminal state (default: 300)")
@click.option("--poll-interval", type=float, default=5, help="Seconds between status polls (default: 5)")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
    buyer_agent_id,
    provider_agent_id,
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
    deterministic_decoding,
    decode_seed,
    input_url,
    output_format,
    classification,
    compliance_framework,
    password,
    password_file,
    password_stdin,
    chain_id,
    rpc_url,
    coordinator_url,
    wait,
    timeout,
    poll_interval,
    format,
):
    """Submit a new AI job to the coordinator with a prompt and optional model."""
    config = _ai.get_config()

    try:
        # Get coordinator URL
        coord_url = _ai._coordinator_base_url(ctx, coordinator_url)
        if not coord_url:
            _ai.abort(ctx, "Coordinator URL not configured")

        rpc_url = rpc_url or config.blockchain_rpc_url or "http://localhost:8202"
        if not rpc_url:
            _ai.abort(ctx, "RPC URL not configured")

        wallet_address, private_key, _ = _ai.load_wallet_for_payment(
            ctx, wallet_name=wallet, password=password, password_file=password_file, password_stdin=password_stdin
        )
        # Resolve the buyer once: the job POST and the escrow lock must pay
        # from the same address, so the lock falls back to the wallet the
        # same way _apply_payment_fields does for the POST.
        buyer_address = buyer_address or wallet_address

        if buyer_agent_id or provider_agent_id:
            if not (payment or offer_id):
                _ai.abort(ctx, "--buyer-agent-id / --provider-agent-id require a paid submission (--payment or --offer-id)")
            bind_chain = int(chain_id) if chain_id else _ai.resolve_chain_id(ctx, rpc_url)
            buyer_address, provider_address, buyer_agent_id, provider_agent_id = _ai.resolve_escrow_parties(
                ctx,
                buyer=buyer_address,
                provider=provider_address or os.environ.get("SHOP_WALLET_ADDRESS"),
                buyer_agent_id=buyer_agent_id,
                provider_agent_id=provider_agent_id,
                chain_id=int(bind_chain),
            )

        # Auth once and reuse for media upload and job submission.
        headers = _ai._require_auth_headers(ctx)
        http_client = _ai.AITBCHTTPClient(base_url=coord_url, timeout=30, headers=headers)

        # Prepare job data in the JobCreate shape expected by coordinator-api
        job_type = job_type or "inference"
        job_data: dict[str, Any] = {
            "payload": _submit_payload(http_client, job_type, prompt, model, input_url, output_format),
            "constraints": {},
            "ttl_seconds": 900,
        }
        _apply_compliance(ctx, job_data["constraints"], compliance_framework, classification)
        _apply_simple_constraints(
            job_data["constraints"],
            min_reputation=min_reputation,
            zk_proof_required=zk_proof_required,
            auto_reinvest_pct=auto_reinvest_pct,
            bond_required=bond_required,
            min_bond_amount=min_bond_amount,
            deterministic_decoding=deterministic_decoding,
            decode_seed=decode_seed,
            acceptance_window=acceptance_window,
        )
        _apply_tee_constraints(
            ctx,
            job_data["constraints"],
            config,
            tee_attestation_required=tee_attestation_required,
            tee_enclave_id=tee_enclave_id,
            confidential=confidential,
            enclave_measurement=enclave_measurement,
        )
        _apply_payment_fields(
            ctx,
            job_data,
            payment=payment,
            currency=currency,
            buyer_address=buyer_address,
            wallet_address=wallet_address,
            provider_address=provider_address,
            offer_id=offer_id,
            offer_quantity=offer_quantity,
        )
        _attach_shop_access(ctx, job_data, model=model, payment=payment, offer_id=offer_id)

        # Pre-flight the chain round-trips the escrow step needs anyway when
        # we will sign it ourselves: an unreachable RPC or a missing buyer
        # account aborts here, before the coordinator holds an
        # accepted-but-unfunded job until TTL.
        if (payment or offer_id) and private_key:
            chain_id = chain_id or _ai.resolve_chain_id(ctx, rpc_url)
            _ai.get_buyer_nonce(ctx, rpc_url, buyer_address)

        # Submit to coordinator. The Idempotency-Key binds every retry of
        # this submission to one server-side operation (CLI-IDEMPOTENCY-1):
        # a gateway 502 after the job landed replays the recorded response
        # instead of creating a duplicate job.
        submit_key = _ai._new_idempotency_key("ai-submit")
        result = _ai._post_idempotent(http_client, "/v1/jobs", json=job_data, idempotency_key=submit_key)

        job_id = cast(str, result.get("job_id"))
        _ai.success(f"Job submitted: {job_id}")

        payment_id = _secure_escrow(
            ctx,
            http_client,
            rpc_url,
            result,
            job_id,
            currency=currency,
            buyer_address=buyer_address,
            provider_address=provider_address,
            private_key=private_key,
            chain_id=chain_id,
            offer_id=offer_id,
            offer_quantity=offer_quantity,
            idempotency_key=f"{submit_key}-escrow",
            buyer_agent_id=buyer_agent_id,
            provider_agent_id=provider_agent_id,
        )

        # A paid job whose escrow could not be secured can never be dispatched --
        # the coordinator holds it out of the queue until TTL expiry. Surface
        # that as a failure instead of letting it look like a normal submission.
        # Deliberately-unpaid jobs (no --payment/--offer-id) still succeed.
        if not payment_id and (payment or offer_id or result.get("payment_amount")):
            _ai.abort(
                ctx,
                f"Job {job_id} was accepted but its escrow could not be secured "
                f"(payment_status={result.get('payment_status', 'pending')}); it "
                "would never be dispatched. Resubmit with --provider-address and "
                f"a signing --wallet, or fund it with 'aitbc ai pay --job-id {job_id}'.",
            )

        if not wait:
            _ai.output(result, _ai.resolve_output_format(ctx, format))
            return

        _wait_for_job(
            ctx,
            http_client,
            job_id,
            payment_id,
            timeout,
            poll_interval,
            _ai.resolve_output_format(ctx, format),
        )

    except _ai.NetworkError as e:
        _abort_network_error(ctx, e)
    except _ai._OPS_ERRORS as e:
        _ai.abort(ctx, f"Error submitting job: {e}", from_exception=e)
