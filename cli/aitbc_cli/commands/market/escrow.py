"""
Escrow subgroup and escrow-related helpers
"""

import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import click

from aitbc.config.hub import normalize_hub_base
from aitbc.utils.units import units_to_ait

from ...auth import AuthManager
from ...utils.wallet_secret import wallet_password_options
from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.http_client import AITBCHTTPClient, get_logger, http_error_detail, http_response_status
from ...utils.error_handling import abort

# Initialize logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------


def escrow_group():
    """Create and return the escrow group"""

    @click.group(
        epilog="""Examples:

  aitbc market escrow status --job-id job-123

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x..."""
    )
    def escrow():
        """Manage on-chain escrow for GPU jobs."""
        pass

    return escrow


escrow = escrow_group()


def _hub_base_url(config) -> str:
    """Resolve the hub base URL — self/scheme-aware via aitbc.config.hub."""
    raw = config.hub_discovery_url or "hub.aitbc.invalid"
    return normalize_hub_base(raw) or raw


def _get_rpc_client(config, base_url: str, timeout: int = 10) -> AITBCHTTPClient:
    """Return an HTTP client for blockchain RPC calls, with the API key if configured."""
    return AITBCHTTPClient(
        base_url=base_url,
        timeout=timeout,
        api_key=getattr(config, "blockchain_rpc_api_key", None),
    )


def _get_blockchain_rpc_url(config) -> str:
    """Return local blockchain RPC base URL (no trailing /rpc — callers add the path)."""
    url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")
    # Normalise to port 8202 if the stored URL points to localhost
    if "localhost" in url or "127.0.0.1" in url:
        url = re.sub(r":\d+", ":8202", url)
    # Strip trailing /rpc so callers that use /rpc/... paths don't double up
    url = url.rstrip("/")
    if url.endswith("/rpc"):
        url = url[:-4]
    return url


def _http_503_detail(exc: BaseException) -> str | None:
    """Return the node's ``detail`` text when ``exc`` carries an HTTP 503 reply, else None."""
    if http_response_status(exc) != 503:
        return None
    return http_error_detail(exc)


def _settlement_node_url(detail: str) -> str | None:
    """Extract the settlement-node URL the node names in its 503 detail.

    The node appends ``"; the settlement node is at <url>"`` when it knows
    the settlement-capable RPC (``HUB_RPC_URL``). Return None when the
    detail names none.
    """
    marker = "the settlement node is at "
    idx = detail.find(marker)
    if idx < 0:
        return None
    url = detail[idx + len(marker) :].strip().rstrip(".")
    # The named URL may carry a trailing /rpc — strip it like
    # _get_blockchain_rpc_url does, or callers double the path segment.
    url = url.rstrip("/")
    if url.endswith("/rpc"):
        url = url[:-4]
    return url or None


def _describe_rpc_failure(base: str, exc: BaseException) -> str:
    """One-line description of an RPC failure, including the status code.

    A 401/403 names the API-key cause so a refused release/refund never
    reads like an unreachable node.
    """
    status = http_response_status(exc)
    detail = http_error_detail(exc) or str(exc)
    hint = " (RPC requires an API key — set blockchain_rpc_api_key)" if status in (401, 403) else ""
    return f"{base}: HTTP {status} {detail}{hint}" if status is not None else f"{base}: {exc}"


def _post_escrow_rpc(config, path: str, payload: dict[str, Any], timeout: int = 10) -> tuple[dict[str, Any] | None, list[str]]:
    """POST an escrow RPC to the local node, then the hub fallback.

    Returns ``(result, failures)`` — ``failures`` names each endpoint that
    refused and why, so callers surface a real error instead of silently
    returning None (a 403 API-key refusal used to read exactly like a
    missing escrow).
    """
    failures: list[str] = []
    rpc_url = _get_blockchain_rpc_url(config)
    hub_url = _hub_base_url(config)
    for base in dict.fromkeys(b for b in (rpc_url, hub_url) if b):
        try:
            result = _get_rpc_client(config, base, timeout=timeout).post(path, json=payload)
            return result, failures
        except Exception as exc:
            logger.debug("Escrow RPC %s failed on %s", path, base, exc_info=True)
            failures.append(_describe_rpc_failure(base, exc))
    return None, failures


def _escrow_locked_amount(config, job_id: str, timeout: int = 10) -> str | None:
    """Read the escrow's locked AIT amount via the local→hub GET.

    The release relay requires an explicit ``amount`` where the chain route
    treats a missing amount as "pay the whole lock". GET endpoints are not
    nginx-allowlisted, so a customer node can read the row even when it
    cannot POST the release itself.
    """
    for base in dict.fromkeys(b for b in (_get_blockchain_rpc_url(config), _hub_base_url(config)) if b):
        try:
            row = _get_rpc_client(config, base, timeout=timeout).get(f"/rpc/escrow/{job_id}")
        except Exception:
            logger.debug("Escrow GET %s failed on %s", job_id, base, exc_info=True)
            continue
        if isinstance(row, dict) and row.get("amount") is not None:
            return str(row["amount"])
    return None


def _resolve_release_amount(config, job_id: str, amount: Any) -> tuple[str | None, str | None]:
    """Return ``(amount_str, skip_reason)`` for the release relay body.

    ``skip_reason`` set → the relay cannot accept this amount (unreadable,
    non-numeric or non-positive — it would answer a terminal 400) and the
    caller should use the rpc path directly.
    """
    if amount is None:
        amount = _escrow_locked_amount(config, job_id)
        if amount is None:
            return None, "escrow amount unreadable for the release relay body"
    try:
        amount_dec = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        return None, f"amount {amount!r} is not a number the release relay accepts"
    if not amount_dec.is_finite() or amount_dec <= 0:
        return None, f"amount {amount!r} is not positive — the release relay requires > 0"
    return str(amount), None


# Bounded wait for a relay 425 "lock not yet sealed": the ESCROW_LOCK is
# still in mempool and seals within a block or two. Each wait honours the
# response's Retry-After (default 5 s, the chain's own hint), capped per
# wait and in total so the whole retry stays under ~30 s.
_SEAL_WAIT_DEFAULT = 5.0
_SEAL_WAIT_CAP = 10.0
_SEAL_WAIT_TOTAL = 24.0


def _http_response_header(exc: BaseException, name: str) -> str | None:
    """Return one response header from a wrapped HTTP error, or None."""
    seen: BaseException | None = exc
    while seen is not None:
        response = getattr(seen, "response", None)
        if response is not None:
            headers = getattr(response, "headers", None) or {}
            try:
                return headers.get(name)
            except AttributeError:
                return None
        seen = seen.__cause__ or seen.__context__
    return None


def _seal_wait_seconds(exc: BaseException, wait_seconds_left: float) -> float:
    """Seconds to wait before reposting after a 425 — Retry-After, bounded.

    Returns 0 when the wait allowance is exhausted (the caller stops retrying).
    """
    raw = _http_response_header(exc, "Retry-After")
    wait = _SEAL_WAIT_DEFAULT
    if raw is not None:
        try:
            wait = float(raw)
        except (TypeError, ValueError):
            pass  # HTTP-date Retry-After: fall back to the default wait
    if wait <= 0:
        wait = _SEAL_WAIT_DEFAULT
    return max(0.0, min(wait, _SEAL_WAIT_CAP, wait_seconds_left))


def _classify_relay_error(exc: BaseException, job_id: str) -> tuple[None, str | None, str | None]:
    """Map a relay POST failure to (result, terminal_refusal, skip_reason).

    425 is a named retryable condition (the lock had not sealed inside the
    bounded wait); other business 4xx are terminal; transport failures and
    401/404/bare-Forbidden 403 are skips that allow the rpc fallback.
    """
    status = http_response_status(exc)
    detail = http_error_detail(exc) or str(exc)
    if status == 425:
        return (
            None,
            (
                f"coordinator release relay: HTTP 425 {detail} — the escrow lock is not yet sealed "
                f"(retryable; rerun `aitbc market escrow release --job-id {job_id}` once the "
                "ESCROW_LOCK seals)"
            ),
            None,
        )
    # A bare {"detail": "Forbidden"} 403 is the middleware deny-by-default
    # on an older coordinator missing the route's security-matrix entry —
    # a deployment gap, not a business refusal: fall back like a 404.
    middleware_deny = status == 403 and detail.strip() == "Forbidden"
    if status is not None and 400 <= status < 500 and status not in (401, 404) and not middleware_deny:
        return None, f"coordinator release relay refused: HTTP {status} {detail}", None
    label = f"HTTP {status} {detail}" if status is not None else str(exc)
    return None, None, f"coordinator release relay unavailable ({label})"


def _release_via_relay(
    ctx,
    config,
    job_id: str,
    *,
    amount: Any = None,
    job_tx_hash: str | None = None,
    timeout: int = 30,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Try the coordinator ``POST /v1/escrow/release`` relay.

    Returns ``(result, terminal_refusal, skip_reason)``:

    - ``result`` set → the relay released the escrow; done.
    - ``terminal_refusal`` set → the relay refused on business grounds
      (buyer mismatch 403, already refunded 409, amount over the lock or
      invalid 400, or any other 4xx except 401/404 and a bare
      ``{"detail": "Forbidden"}`` 403). Do NOT fall back to the rpc —
      retrying a business refusal on the unauthenticated rpc path would
      bypass the JWT binding that is the relay's purpose.
    - ``(None, None, skip_reason)`` → the relay could not answer: no
      stored credential, escrow amount unreadable or not positive, 401
      (JWT rejected), 404 (relay not deployed or escrow absent — the rpc
      retry reports an absent escrow identically), bare-Forbidden 403
      (middleware deny-by-default on a coordinator missing the matrix
      entry), 5xx or a connection failure. Transport failures get one
      retry first — the relay dedups on job_id so a repost cannot
      double-release. The caller may fall back to
      :func:`_post_escrow_rpc`; ``skip_reason`` names why.

    One status class is neither refusal nor skip: the chain answers
    ``425`` "lock not yet sealed" (``Retry-After: 5``) while the
    ESCROW_LOCK is still in mempool. That is retryable by definition, so
    the helper waits and reposts the same body a bounded number of times
    (budget under ~30 s). If the bound is exhausted the refusal slot
    carries a named *retryable* message — still no rpc fallback (the rpc
    would 425 identically and a customer node cannot authenticate it),
    but it is not reported as a business refusal.
    """
    token = _client_token(ctx)
    if not token:
        return (
            None,
            None,
            (
                "no stored client credential for the coordinator release relay "
                "(`aitbc auth login` as the escrow buyer enables it)"
            ),
        )
    # The relay requires a positive amount (400 'escrow amount must be
    # positive' — a terminal refusal). A zero or unparseable metered amount
    # must go straight to the rpc path, which reports the same refusal
    # without a pointless relay round-trip.
    amount_str, skip = _resolve_release_amount(config, job_id, amount)
    if skip is not None:
        return None, None, skip
    body: dict[str, Any] = {"job_id": job_id, "amount": amount_str}
    if job_tx_hash:
        body["job_tx_hash"] = job_tx_hash
    client = AITBCHTTPClient(
        base_url=_coordinator_base_url(ctx),
        timeout=timeout,
        headers={"Authorization": f"Bearer {token}"},
    )
    result: Any = None
    last_exc: Exception | None = None
    # Retries: one retry on a transport failure (timeout/connection — no
    # HTTP status), and a bounded wait+repost loop on a 425 "lock not yet
    # sealed". The relay POST is idempotent (the coordinator dedups on
    # job_id and an already-released escrow returns its stored tx_hash),
    # so neither repost can double-release.
    wait_seconds_left = _SEAL_WAIT_TOTAL
    transport_retried = False
    while True:
        try:
            result = client.post("/v1/escrow/release", json=body)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            status = http_response_status(exc)
            if status == 425:
                wait = _seal_wait_seconds(exc, wait_seconds_left)
                if wait > 0:
                    wait_seconds_left -= wait
                    time.sleep(wait)
                    continue
            elif status is None and not transport_retried:
                transport_retried = True
                continue
            break
    if last_exc is not None:
        return _classify_relay_error(last_exc, job_id)
    return (result if isinstance(result, dict) else {"success": True}), None, None


def _post_escrow_release(
    ctx,
    config,
    job_id: str,
    *,
    amount: Any = None,
    job_tx_hash: str | None = None,
    timeout: int = 10,
    relay_timeout: int = 30,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Release an escrow: coordinator JWT relay first, local→hub rpc fallback.

    Same ``(result, failures)`` contract as :func:`_post_escrow_rpc`. A
    relay business refusal is terminal — the failures list carries the
    relay's detail and the rpc is never tried, so a refusal is never
    laundered through a weaker-auth path.
    """
    result, refusal, skip_reason = _release_via_relay(
        ctx, config, job_id, amount=amount, job_tx_hash=job_tx_hash, timeout=relay_timeout
    )
    if refusal is not None:
        return None, [refusal]
    if result is not None:
        return result, []
    failures: list[str] = [skip_reason] if skip_reason else []
    payload: dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = str(amount)
    if job_tx_hash:
        payload["job_tx_hash"] = job_tx_hash
    rpc_result, rpc_failures = _post_escrow_rpc(config, f"/rpc/escrow/{job_id}/release", payload, timeout=timeout)
    return rpc_result, failures + rpc_failures


def _settlement_url_allowed(url: str, config) -> bool:
    """Allow the retry only against the configured hub or a loopback host.

    The settlement URL arrives in a server-supplied 503 detail inside
    fund-moving code — it must never redirect a signed escrow lock to a
    foreign host.
    """
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    hub = _hub_base_url(config).rstrip("/")
    # `url` already had a trailing /rpc stripped by _settlement_node_url.
    return url.rstrip("/") == hub or url.rstrip("/") == hub.removesuffix("/rpc")


def _escrow_create(
    ctx,
    job_id: str,
    buyer: str,
    provider: str,
    amount: Decimal | None,
    config,
    private_key: str | None = None,
    node_wallet: str | None = None,
) -> str | None:
    """Create an on-chain escrow for a paid job.

    If ``private_key`` is provided, the ESCROW_LOCK transaction is signed by
    the buyer and the blockchain RPC can settle it on-chain.  Without it, the
    helper aborts because the chain refuses to lock escrow without a buyer
    signature.

    The chain's smallest unit is the compute-unit (1 AIT = 36_000_000).
    Estimates that round to zero compute-units are rounded up to one compute-unit
    so the lock transaction is valid and the provider can be paid.

    ``node_wallet`` is the settlement node's custody address the lock pays
    to — deliberately not the consensus proposer id. Resolution order: an
    explicit ``--proposer``/``node_wallet`` argument, then the node's own
    ``/health`` ``node_wallet`` (customer nodes already advertise the
    settlement wallet there), with ``HUB_PROPOSER_ID`` only as a warned
    fallback.
    """
    from . import get_chain_id
    from ...utils.escrow import create_signed_escrow_lock

    if not private_key:
        error("Escrow creation requires a buyer-signed transaction. Use --wallet to select a wallet with a private key.")
        raise click.Abort()

    if not amount or amount <= 0:
        error("Escrow amount must be positive")
        raise click.Abort()

    # 1 AIT = 36_000_000 compute-units; 0.0000000277... AIT = 1 compute-unit.
    min_escrow_ait = units_to_ait(1)
    if amount < min_escrow_ait:
        info(f"Rounding escrow up to minimum {min_escrow_ait} AIT (1 compute-unit)")
        amount = min_escrow_ait

    # The escrow `to` is the settlement node's *node wallet* (the custody
    # address) — deliberately NOT the consensus proposer id. Prefer the
    # node's own /health advertisement: on customer nodes it already names
    # the settlement wallet (node0 and hub share it). HUB_PROPOSER_ID is a
    # different identity and only a warned fallback.
    if not node_wallet:
        # Local /health discovery names the node wallet (settlement custody).
        from ...utils.escrow import get_node_wallet

        try:
            node_wallet = get_node_wallet(ctx, _get_blockchain_rpc_url(config))
        except Exception:
            pass
    if not node_wallet:
        node_wallet = getattr(config, "hub_proposer_id", None) or None
        if node_wallet:
            warning(
                "Using HUB_PROPOSER_ID as escrow destination — it is the consensus proposer, "
                "not the node wallet; the settlement chain may reject the lock"
            )
    if not node_wallet:
        error("No escrow node-wallet address available. Run on a node whose /health advertises node_wallet.")
        raise click.Abort()

    rpc_url = _get_blockchain_rpc_url(config)
    try:
        lock_tx, signature = create_signed_escrow_lock(
            ctx,
            rpc_url,
            job_id,
            buyer,
            provider,
            amount,
            private_key,
            chain_id=get_chain_id(),
            node_wallet=node_wallet,
        )
    except Exception as e:
        error(f"Failed to build escrow lock transaction: {e}")
        raise click.Abort() from e

    payload = {
        "job_id": job_id,
        "buyer": buyer,
        "provider": provider,
        "amount": str(amount) if amount else "0",
        "lock_tx": {**lock_tx, "signature": signature},
        "lock_signature": signature,
    }
    try:
        http_client = _get_rpc_client(config, rpc_url, timeout=10)
        result = http_client.post("/rpc/escrow/create", json=payload)
        contract_id = result.get("contract_id") if isinstance(result, dict) else None
        if contract_id:
            success(f"Escrow created: contract_id={contract_id}")
        return contract_id
    except Exception as e:
        # Customer route: the hub nginx allowlist 403s external
        # /rpc/escrow/create, so a customer node cannot reach a
        # settlement-capable RPC directly. Relay the buyer-signed lock
        # through the coordinator instead — it submits from the hub,
        # inside the allowlist. Older coordinators do not serve the relay
        # endpoint (404) — fall through to the settlement-node retry.
        try:
            relayed = _coordinator_escrow_create(ctx, payload)
        except Exception as relay_exc:
            warning(f"Coordinator escrow relay failed ({relay_exc}) — trying direct node routes")
            relayed = None
        if relayed is not None:
            contract_id = relayed.get("contract_id") if isinstance(relayed, dict) else None
            if contract_id:
                success(f"Escrow created via coordinator relay: contract_id={contract_id}")
            return contract_id
        detail = _http_503_detail(e)
        # A settlement-incapable node names its settlement node in the 503
        # detail ("the settlement node is at <url>"). Retry the create there
        # once — the same refusal is already encoded in the response, so the
        # retry can only help a wrong-routed caller.
        if detail:
            settlement_url = _settlement_node_url(detail)
            if settlement_url and settlement_url.rstrip("/") != rpc_url.rstrip("/"):
                # The named URL is server-supplied text in fund-moving client
                # code: only ever retry against the configured hub or a
                # loopback address — anything else could redirect a signed
                # escrow lock to a foreign host.
                if not _settlement_url_allowed(settlement_url, config):
                    error(
                        f"Escrow creation refused: settlement retry target {settlement_url} "
                        "is not the configured hub or a loopback address — not retrying"
                    )
                    raise click.Abort() from e
                warning(f"Escrow creation refused locally ({detail}) — retrying on the settlement node")
                try:
                    result = _get_rpc_client(config, settlement_url, timeout=10).post("/rpc/escrow/create", json=payload)
                    contract_id = result.get("contract_id") if isinstance(result, dict) else None
                    if contract_id:
                        success(f"Escrow created: contract_id={contract_id}")
                    return contract_id
                except Exception as e2:
                    error(f"Escrow creation failed on the settlement node: {e2}")
                    raise click.Abort() from e2
            error(f"Escrow creation refused: {detail}")
        else:
            error(f"Escrow creation failed: {e}")
        raise click.Abort() from e


@escrow.command(
    name="release",
    epilog="""Examples:

  aitbc market escrow release --job-id job-123""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.pass_context
def escrow_release(ctx, job_id: str):
    """Release escrow funds to the provider after job completion."""
    try:
        config = get_config()
        result, failures = _post_escrow_release(ctx, config, job_id)
        if result:
            success(f"Escrow released for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
        else:
            suffix = f": {'; '.join(failures)}" if failures else ""
            error(f"Failed to release escrow for job {job_id}{suffix}")
    except Exception as e:
        error(f"Error releasing escrow: {e}")
        raise click.Abort() from e


def _coordinator_base_url(ctx) -> str:
    """Return coordinator base URL with any trailing /v1 stripped."""
    url = ctx.obj.get("url")
    if not url:
        url = get_config().coordinator_api_url or "http://localhost:8203"
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return cast(str, url)


def _client_token(ctx) -> str | None:
    """Return API key from --api-key, then the stored client credential."""
    token = ctx.obj.get("api_key")
    if not token:
        token = AuthManager().get_credential("client")
    return cast(str | None, token)


def _coordinator_escrow_create(ctx, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Relay a buyer-signed escrow create through the coordinator.

    Market escrows carry a locally-minted job_id with no coordinator job
    row, so ``POST /v1/payments`` cannot serve them (it requires an owned
    job). The JWT-gated relay endpoint ``POST /v1/escrow/relay`` accepts
    the raw ``/rpc/escrow/create`` payload and submits it from the hub —
    inside the nginx allowlist that blocks external callers.

    Returns the relayed response, or ``None`` when no relay is possible:
    no client credential, or a coordinator that does not serve the relay
    endpoint yet (HTTP 404). Other failures propagate so the caller can
    warn and fall back to direct node routes.
    """
    token = _client_token(ctx)
    if not token:
        return None
    base_url = _coordinator_base_url(ctx)
    client = AITBCHTTPClient(base_url=base_url, timeout=30, headers={"Authorization": f"Bearer {token}"})
    try:
        return client.post("/v1/escrow/relay", json=payload)
    except Exception as exc:
        if http_response_status(exc) == 404:
            return None
        raise


def _coordinator_refund(ctx, job_id: str, reason: str) -> dict[str, Any] | None:
    """Ask the coordinator to refund the payment (which also refunds the on-chain escrow)."""
    token = _client_token(ctx)
    if not token:
        return None
    base_url = _coordinator_base_url(ctx)
    try:
        client = AITBCHTTPClient(base_url=base_url, timeout=30, headers={"Authorization": f"Bearer {token}"})
        job = client.get(f"/v1/jobs/{job_id}")
        payment_id = job.get("payment_id") if isinstance(job, dict) else None
        if not payment_id:
            return None
        return client.post(f"/v1/payments/{payment_id}/refund", json={"job_id": job_id, "reason": reason})
    except Exception:
        logger.debug("Coordinator refund request failed", exc_info=True)
        return None


def refund_escrow(ctx: click.Context, job_id: str, reason: str) -> dict[str, Any] | None:
    """Refund escrow back to the buyer (coordinator first, then blockchain fallback)."""
    try:
        config = get_config()
        coordinator_result = _coordinator_refund(ctx, job_id, reason)
        if coordinator_result:
            success(f"Coordinator refund accepted for job {job_id}")
            output(coordinator_result, ctx.obj.get("output_format", "table"))
            return coordinator_result
        info(f"Coordinator refund unavailable for job {job_id} (no coordinator payment) — falling back to the chain rpc")
        result, failures = _post_escrow_rpc(config, f"/rpc/escrow/{job_id}/refund", {"reason": reason})
        if result:
            success(f"Escrow refunded for job {job_id}")
            output(result, ctx.obj.get("output_format", "table"))
            return result
        # Never return silently: name each refusal so a 403 API-key or a 503
        # settlement refusal is diagnosable instead of reading as "no escrow".
        # And never exit 0 after the error — the exit-code guard requires a
        # nonzero exit on a failed refund.
        suffix = f": {'; '.join(failures)}" if failures else ""
        error(f"Failed to refund escrow for job {job_id}{suffix}")
        raise click.Abort()
    except Exception as e:
        error(f"Error refunding escrow: {e}")
        raise click.Abort() from e


@escrow.command(
    name="refund",
    epilog="""Examples:

  aitbc market escrow refund --job-id job-123

  aitbc market escrow refund --job-id job-123 --reason 'job_failed'""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.option("--reason", default="buyer_requested", help="Reason for refund")
@click.pass_context
def escrow_refund(ctx, job_id: str, reason: str):
    """Refund escrow back to the buyer."""
    refund_escrow(ctx, job_id, reason)


@escrow.command(
    name="status",
    epilog="""Examples:

  aitbc market escrow status --job-id job-123

  aitbc market escrow status --job-id job-123 --output json""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.pass_context
def escrow_status(ctx, job_id: str):
    """Check the on-chain escrow state for a job."""
    try:
        config = get_config()
        rpc_url = _get_blockchain_rpc_url(config)
        hub_url = _hub_base_url(config)
        result = None
        failures: list[str] = []
        for base in dict.fromkeys(b for b in (rpc_url, hub_url) if b):
            try:
                http_client = _get_rpc_client(config, base, timeout=10)
                result = http_client.get(f"/rpc/escrow/{job_id}")
                if result:
                    break
            except Exception as exc:
                logger.debug("Escrow request failed", exc_info=True)
                status = http_response_status(exc)
                # 404 is a real answer — the job has no escrow row; the hub
                # fallback may still know it, so keep going.
                if status == 404:
                    continue
                detail = http_error_detail(exc) or str(exc)
                failures.append(f"{base}: HTTP {status} {detail}" if status is not None else f"{base}: {exc}")
        if result:
            output(result, ctx.obj.get("output_format", "table"), title=f"Escrow: {job_id}")
        elif failures:
            # Surface the actual failure — the old code folded every error into
            # "No escrow found", so a missing RPC API key (403) read exactly
            # like an absent row. Name the response so the fix is obvious.
            abort(None, f"Escrow status query failed for job {job_id}: " + "; ".join(failures))
        else:
            abort(None, f"No escrow found for job {job_id}")
    except Exception as e:
        error(f"Error checking escrow status: {e}")
        raise click.Abort() from e


@escrow.command(
    name="create",
    epilog="""Examples:

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x...

  aitbc market escrow create --job-id job-123 --buyer 0x... --provider 0x... --amount 100""",
)
@click.option("--job-id", "job_id", required=True, help="Coordinator job ID.")
@click.option("--buyer", "buyer", required=True, help="The Buyer.")
@click.option("--provider", "provider", required=True, help="The Provider.")
@click.option("--amount", "amount", required=False, help="Amount of AIT.")
@click.option("--wallet", "wallet_name", help="Wallet name to sign the escrow lock")
@wallet_password_options
@click.pass_context
def escrow_create_cmd(ctx, job_id, buyer, provider, amount, wallet_name, password, password_file, password_stdin):
    """Create an on-chain escrow for a job with buyer, provider, and optional amount."""
    try:
        from decimal import Decimal as _Decimal
        from ...utils.money import wallet_amount
        from ...utils.wallet_loader import load_wallet_for_payment

        config = get_config()
        amt = _Decimal(wallet_amount(amount)) if amount is not None else None
        _, private_key, _ = load_wallet_for_payment(
            ctx, wallet_name=wallet_name, password=password, password_file=password_file, password_stdin=password_stdin
        )
        contract_id = _escrow_create(ctx, job_id, buyer, provider, amt, config, private_key=private_key)
        output(
            {"contract_id": contract_id, "job_id": job_id, "buyer": buyer, "provider": provider},
            ctx.obj.get("output_format", "table"),
        )
    except click.Abort:
        raise
    except Exception as e:
        abort(None, f"Error creating escrow: {e}")
