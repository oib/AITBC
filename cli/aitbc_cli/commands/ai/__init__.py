"""AI job submission and inspection commands for AITBC CLI"""

import base64
import builtins
import mimetypes
import os
import time
import uuid
from decimal import Decimal, InvalidOperation

from typing import Any, cast

import click

from aitbc.compliance.policies import (
    load_policy_template,
    normalize_classification,
)
from aitbc.exceptions import AITBCError
from eth_keys.exceptions import BadSignature
from eth_utils.exceptions import ValidationError as EthValidationError

from ...config import get_config
from ...utils import resolve_output_format, success, warning
from ...utils.output import output as _utils_output
from ...utils.redact import redact_secrets
from ...utils.chain_id import resolve_chain_id
from ...utils.agent_identity_resolve import resolve_escrow_parties
from ...utils.escrow import create_signed_escrow_lock, get_buyer_nonce, get_node_wallet
from ...utils.error_handling import CLIError, LOGIN_HINT, LOGIN_REJECTED_HINT, abort, is_unauthorized
from ...utils.http_client import (
    AITBCHTTPClient,
    NetworkError,
    auth_client_kwargs,
    get_logger,
    http_error_detail,
    http_response_status,
    looks_like_jwt,
    origin_base_url,
    service_root_url,
)
from ...utils.wallet_loader import load_wallet_for_payment
from ...utils.wallet_secret import wallet_password_options

logger = get_logger(__name__)

# Expected failure surface for the AI job helpers/handlers: filesystem/JSON,
# data-shape, runtime and both error hierarchies (CLIError, aitbc_errors).
# RuntimeError covers generic runtime failures; abort() raises CLIError
# (already listed), preserving the previous re-abort behaviour.
# BaseExceptions still propagate (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    CLIError,
    AITBCError,
    BadSignature,
    EthValidationError,
)


def output(message, format=None, title=None, *, disable_numparse: bool = False, **kwargs):
    """``utils.output`` with credential fields masked before rendering (#2355).

    Coordinator job records embed the per-job shop-gate credential pair
    (``payload.access_key``/``payload.access_secret``); ``redact_secrets``
    masks secret-named keys in the structured payload up front, so every
    renderer — including the table path, which falls back to JSON for nested
    records — is covered.
    """
    return _utils_output(redact_secrets(message), format, title, disable_numparse=disable_numparse, **kwargs)


def _post_idempotent(
    http_client: AITBCHTTPClient,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    idempotency_key: str,
    in_progress_retries: int = 5,
    in_progress_delay: float = 2.0,
) -> dict[str, Any]:
    """POST with an Idempotency-Key, waiting out in-progress duplicates.

    The client's retry policy already replays ambiguous 5xx/network
    failures when a key is set. One gap remains: a replay that arrives
    while the *first* attempt is still executing gets a 409 "already in
    progress" from the operation ledger — an answer that is neither a
    success nor a real conflict. Poll through that bounded number of times
    so a slow first attempt still resolves to its recorded outcome.
    """
    for attempt in range(in_progress_retries + 1):
        try:
            return http_client.post(path, json=json, idempotency_key=idempotency_key)
        except NetworkError as e:
            if http_response_status(e) == 409 and "in progress" in (http_error_detail(e) or "").lower():
                if attempt < in_progress_retries:
                    time.sleep(in_progress_delay)
                    continue
            raise
    raise AssertionError("unreachable")


def _new_idempotency_key(prefix: str) -> str:
    """Client-generated Idempotency-Key for one logical CLI operation."""
    return f"{prefix}-{uuid.uuid4()}"


def _auth_headers(ctx) -> dict[str, str] | None:
    """Return auth headers from --api-key, the stored credential, or config.api_key.

    A JWT-shaped token goes in ``Authorization: Bearer``; anything else is
    an API key and goes in ``X-API-Key`` (same split as confidential.py and
    the coordinator's ApiKeyAuth scheme).
    """
    token = ctx.obj.get("api_key")
    if not token:
        from ...auth import AuthManager

        token = AuthManager().get_credential("client", quiet=True)
    if not token:
        # #2246: last resort is the configured API key — same tail as
        # ``auth_client_kwargs``' explicit > store > config precedence.
        token = getattr(get_config(), "api_key", None)
    if not token:
        return None
    if looks_like_jwt(token):
        return {"Authorization": f"Bearer {token}"}
    return {"X-API-Key": token}


def _require_auth_headers(ctx) -> dict[str, str]:
    """_auth_headers, or abort with the login hint for commands that mutate."""
    headers = _auth_headers(ctx)
    if not headers:
        abort(ctx, LOGIN_HINT)
        raise AssertionError("unreachable: abort always raises")
    return headers


def _login_hint(ctx) -> str:
    """Pick the 401 hint: rejected-credential vs never-logged-in.

    ``LOGIN_HINT`` ("No login for this environment") is wrong when a
    credential exists but the server rejected it — the fleet's stale-JWT
    401s (#2090/#2094/#2095) sent operators chasing a login they already
    had. A stored client credential or ``--api-key`` means the token was
    refused, so point at ``auth login`` as a refresh instead.
    """
    obj = getattr(ctx, "obj", None) or {}
    if obj.get("api_key"):
        return LOGIN_REJECTED_HINT
    try:
        from ...auth import AuthManager

        if AuthManager().get_credential("client", quiet=True):
            return LOGIN_REJECTED_HINT
    except Exception:  # noqa: BLE001,S110 - credential probe must never mask the 401 hint
        pass
    return LOGIN_HINT


def _abort_for_network(ctx, e: NetworkError) -> None:
    """Abort with the login hint on a 401, else the usual network error."""
    if is_unauthorized(e):
        abort(ctx, _login_hint(ctx))
    abort(ctx, f"Network error: {e}", from_exception=e)


def _coordinator_base_url(ctx, coordinator_url: str | None = None) -> str:
    """Return the coordinator base URL without a trailing /v1 path.

    The coordinator routers are mounted under /v1, and the endpoints below
    use /v1/... paths. If the configured URL already ends in /v1, strip it
    to avoid doubling the path.
    """
    config = get_config()
    return service_root_url(coordinator_url or ctx.obj.get("url") or config.coordinator_api_url, "http://localhost:8203")


def _media_url(input_url: str, http_client: AITBCHTTPClient | None = None) -> tuple[str, str | None]:
    """Return a worker-safe URL and optional original filename.

    Remote http(s) and data: URIs are passed through unchanged. A local
    filesystem path is uploaded to the coordinator media endpoint if a client
    is available; otherwise it falls back to an inline data: URI so the worker
    never receives an arbitrary local path.
    """
    if not input_url:
        return "", None
    if input_url.startswith(("http://", "https://", "data:")):
        return input_url, None
    path = os.path.expanduser(input_url)
    if not os.path.isfile(path):
        return input_url, None
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    filename = os.path.basename(path)

    if http_client is None:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}", filename

    try:
        with open(path, "rb") as f:
            response = http_client.session.post(
                http_client._build_url("/v1/media/upload"),
                files={"file": (filename, f, mime)},
                timeout=300,
            )
        response.raise_for_status()
        result = response.json()
        return result.get("download_url", ""), result.get("filename", filename)
    except _OPS_ERRORS as e:
        logger.warning("Media upload failed for %s: %s", path, e)
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}", filename


def _report_escrow_outcome(ctx, job_id: str, payment_result: dict[str, Any]) -> None:
    """#2358: only claim 'Escrow secured' when the coordinator confirms the
    escrow (``status == "escrowed"``/``"confirmed"`` — the token path waits
    for the lock to seal before returning). A failed or still-pending
    payment must surface its reason, not a false success."""
    pay_status = str(payment_result.get("status") or "")
    payment_id = payment_result.get("payment_id")
    if pay_status in ("escrowed", "confirmed"):
        success(f"Escrow secured: {payment_id}")
        return
    if pay_status == "failed":
        reason = payment_result.get("payment_error") or "the escrow lock did not secure"
        warning(
            f"Escrow NOT secured for job {job_id}: payment {payment_id} {reason}. "
            f"The job stays queued until paid — retry with 'aitbc ai pay --job-id {job_id}' "
            f"or close it with 'aitbc ai cancel --job-id {job_id}'"
        )
        return
    warning(
        f"Escrow not yet confirmed for job {job_id}: payment {payment_id} "
        f"status={pay_status or 'unknown'}. Check 'aitbc ai status --job-id {job_id}'."
    )


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
    idempotency_key: str | None = None,
    buyer_agent_id: str | None = None,
    provider_agent_id: str | None = None,
    market_job_id: str | None = None,
) -> dict[str, Any]:
    from ...utils.address import to_canonical

    try:
        amount_ait = Decimal(str(amount))
    except InvalidOperation:
        abort(ctx, f"Invalid payment amount: {amount}")
    buyer = to_canonical(str(buyer_address or ""))
    if not buyer:
        abort(ctx, "buyer_address is required to secure escrow: set --wallet, --buyer-address, or CUSTOMER_WALLET_ADDRESS")
    provider = to_canonical(str(provider_address or ""))
    if not provider:
        abort(ctx, "provider_address is required to secure escrow: set --provider-address or SHOP_WALLET_ADDRESS")
    # Resolve only when an escrow will actually be signed: submit paths that
    # skip payment must not depend on the blockchain RPC being reachable.
    chain_id = chain_id or resolve_chain_id(ctx, rpc_url)
    lock_tx, signature = create_signed_escrow_lock(
        ctx,
        rpc_url,
        job_id,
        buyer,
        provider,
        amount_ait,
        private_key,
        chain_id=chain_id,
        node_wallet=node_wallet,
        market_job_id=market_job_id,
    )
    payload: dict[str, Any] = {
        "job_id": job_id,
        "amount": str(amount_ait),
        "currency": token,
        "payment_method": "aitbc_token",
        "buyer_address": lock_tx["from"],
        "provider_address": lock_tx["payload"]["provider"],
        "buyer_lock_signature": signature,
        "buyer_lock_nonce": lock_tx["nonce"],
        "buyer_lock_fee": lock_tx["fee"],
        "escrow_timeout_seconds": 3600,
    }
    if offer_id:
        payload["offer_id"] = offer_id
    if offer_quantity is not None:
        payload["offer_quantity"] = str(offer_quantity)
    if buyer_agent_id:
        payload["buyer_agent_id"] = buyer_agent_id
    if provider_agent_id:
        payload["provider_agent_id"] = provider_agent_id
    if idempotency_key:
        return _post_idempotent(coord_http_client, "/v1/payments", json=payload, idempotency_key=idempotency_key)
    return coord_http_client.post("/v1/payments", json=payload)


from ._group import ai

# Import submodules to register all commands. Order matches the original
# single-module declaration order so ``ai.commands`` insertion order is
# unchanged; names are re-bound to the click Command objects they decorate.
from .submit import submit
from .pay import pay
from .jobs import accept, jobs, status
from .refunds import refund, refund_sweep
from .service import service
from .results import cancel, results
from .stats import distribution_stats, stats
