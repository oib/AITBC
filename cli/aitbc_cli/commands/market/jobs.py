"""
Job commands: run, transcribe, process
"""

import hashlib
import json
import os
import urllib.request
from datetime import datetime
from decimal import Decimal
from typing import Any

import click

from aitbc.utils.units import DEFAULT_TX_FEE_UNITS

from ...config import get_config
from ...utils import OUTPUT_FORMAT_OPTION, error, info, output, resolve_output_format, success, warning
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)

from ...auth import AuthManager

from . import get_chain_id, get_market_wallet, get_next_nonce, market
from .escrow import _escrow_create, _get_blockchain_rpc_url


def _compute_plugin_id(service_type: str, model: str) -> str:
    """Derive the plugin_id used by the marketplace service."""
    return f"{service_type}-{model.replace(':', '-')}"


def _resolve_offer_from_marketplace(http_client: AITBCHTTPClient, offer_id_or_plugin_id: str) -> dict[str, Any] | None:
    """Resolve an offer from the marketplace service by offer_id or plugin_id."""
    try:
        result = http_client.get("/v1/marketplace/offer")
        offers = result.get("offers", []) if result else []
    except Exception:
        return None

    # First pass: exact offer_id match.
    for offer in offers:
        if offer.get("offer_id") == offer_id_or_plugin_id:
            return offer

    # Second pass: plugin_id match.
    for offer in offers:
        if offer.get("plugin_id") == offer_id_or_plugin_id:
            return offer

    # Third pass: derive plugin_id from service_type-model and match.
    for offer in offers:
        st = offer.get("service_type", "")
        model = offer.get("model", "")
        if _compute_plugin_id(st, model) == offer_id_or_plugin_id:
            return offer

    return None


def _resolve_offer_from_blockchain(http_client: AITBCHTTPClient, offer_id_or_plugin_id: str) -> dict[str, Any] | None:
    """Resolve an offer from on-chain GPU_MARKETPLACE transactions."""
    try:
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
    except Exception:
        return None

    if isinstance(result, dict):
        return None

    for tx in result:  # type: ignore[unreachable]
        if not isinstance(tx, dict):
            continue
        payload = tx.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if payload.get("action") != "software_offer":
            continue
        if payload.get("offer_id") == offer_id_or_plugin_id:
            return payload
        st = payload.get("service_type", "")
        model = payload.get("model", "")
        if _compute_plugin_id(st, model) == offer_id_or_plugin_id:
            return payload
    return None


def _resolve_offer(ctx, offer_id_or_plugin_id: str) -> dict[str, Any]:
    """Resolve an offer by on-chain offer_id or marketplace plugin_id."""
    config = get_config()
    hub_host = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    if hub_host.startswith(("http://", "https://")):
        hub_url = hub_host.rstrip("/")
    elif "localhost" in hub_host or "127.0.0.1" in hub_host:
        hub_url = f"http://{hub_host}"
    else:
        # Public hubs are exposed over HTTPS.
        hub_url = f"https://{hub_host}"
    http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)

    # Prefer the marketplace service, which has the liveliest view and plugin_id.
    offer = _resolve_offer_from_marketplace(http_client, offer_id_or_plugin_id)
    if offer:
        return offer

    # Fall back to on-chain transactions.
    offer = _resolve_offer_from_blockchain(http_client, offer_id_or_plugin_id)
    if offer:
        return offer

    error(f"Offer '{offer_id_or_plugin_id}' not found on hub")
    raise click.Abort()


def _track_coordinator_job(
    ctx: click.Context,
    job_id: str,
    offer: dict[str, Any],
    wallet_address: str,
    provider_address: str,
    actual_cost: Decimal,
    service_type: str,
    result_hash: str = "",
) -> dict[str, Any] | None:
    """Create a lightweight coordinator job record for a direct market-run job."""
    if not ctx.obj:
        return None
    token = ctx.obj.get("api_key")
    if not token:
        try:
            token = AuthManager().get_credential("client")
        except Exception:
            token = None
    if not token:
        warning("Job tracking skipped: no client token. Run `aitbc auth login --wallet <name>` first.")
        return None

    config = get_config()
    coord_url = config.coordinator_api_url or "http://localhost:8203"
    if coord_url.endswith("/v1"):
        coord_url = coord_url[:-3]
    coord_url = coord_url.rstrip("/")

    payload: dict[str, Any] = {
        "type": service_type,
        "model": offer.get("model", ""),
        "source": "market_run",
        "market_job_id": job_id,
        "offer_id": offer.get("offer_id", ""),
        "result_hash": result_hash,
        "actual_cost_ait": str(round(actual_cost, 6)),
        "buyer_address": wallet_address,
        "provider_address": provider_address or wallet_address,
    }
    job_data = {
        "payload": payload,
        "constraints": {},
        "ttl_seconds": 86400,
        "payment_amount": 0,
        "payment_currency": "AITBC",
        "buyer_address": wallet_address,
        "provider_address": provider_address or wallet_address,
    }

    try:
        client = AITBCHTTPClient(base_url=coord_url, timeout=10, headers={"Authorization": f"Bearer {token}"})
        result = client.post("/v1/jobs", json=job_data)
        info(f"Tracked market-run job with coordinator: {result.get('job_id')}")
        return result
    except Exception as e:
        warning(f"Failed to track market-run job with coordinator: {e}")
        return None


def _run_ollama(
    ctx: click.Context,
    offer: dict[str, Any],
    prompt: str,
    wallet_address: str,
    private_key: str,
    max_tokens: int,
    stream: bool,
    output_format: str,
    track: bool = False,
    node_wallet: str | None = None,
) -> None:
    """Run an Ollama inference job against a software offer and pay metered escrow."""
    config = get_config()
    get_chain_id()

    service_type = offer.get("service_type", "")
    model = offer.get("model", "")
    price = Decimal(str(offer.get("price", 0)))
    price_unit = offer.get("price_unit", "per_1k_tokens")
    provider_address = offer.get("provider_address", "")

    info(f"Offer: {service_type} — {model} at {price} AIT/{price_unit}")
    info(f"Provider: {provider_address}")

    # Lock escrow upfront (estimated max cost)
    estimated_tokens = max_tokens
    estimated_cost = (Decimal(estimated_tokens) / 1000) * price
    job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer.get("offer_id")}{wallet_address}'.encode()).hexdigest()[:8]}"
    info(f"Locking escrow: ~{estimated_cost:.8f} AIT (est. {estimated_tokens} tokens)")
    contract_id = _escrow_create(
        ctx,
        job_id,
        wallet_address,
        provider_address or wallet_address,
        estimated_cost,
        config,
        private_key=private_key,
        node_wallet=node_wallet,
    )

    # Resolve the Ollama endpoint. Customers always reach the public endpoint.
    ollama_endpoint = offer.get("public_endpoint") or offer.get("endpoint") or "http://localhost:11434"
    if not ollama_endpoint.startswith(("http://", "https://")):
        error(f"Rejecting offer with unsafe endpoint scheme: {ollama_endpoint}")
        raise click.Abort()
    ollama_base = ollama_endpoint.rstrip("/")

    # Run inference via Ollama
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens}}).encode()
    req = urllib.request.Request(
        f"{ollama_base}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    info("Running inference...")
    t_start = datetime.now()
    with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310 - URL validated
        resp_data = json.loads(resp.read())
    elapsed = (datetime.now() - t_start).total_seconds()

    response_text = resp_data.get("response", "")
    tokens_used = resp_data.get("eval_count", len(response_text.split()) * 2)
    actual_cost = (Decimal(tokens_used) / 1000) * price

    info(f"Done in {elapsed:.2f}s — {tokens_used} tokens — actual cost: {actual_cost:.8f} AIT")
    click.echo(f"\n{response_text}\n")

    # Release metered escrow for actual tokens used
    if contract_id:
        rpc_url = _get_blockchain_rpc_url(config)
        rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        release_result = rpc_client.post(
            f"/rpc/escrow/{job_id}/release",
            json={
                "amount": str(actual_cost),
                "tokens_used": tokens_used,
                "job_id": job_id,
            },
        )
        if release_result and release_result.get("tx_hash"):
            released_amount = Decimal(release_result.get("released_amount", str(actual_cost)))
            success(
                f"Payment released: {released_amount:.8f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
            )
        else:
            warning("Escrow release submitted but no tx_hash returned")
    else:
        warning("No escrow contract — payment not released")

    output(
        {
            "job_id": job_id,
            "offer_id": offer.get("offer_id"),
            "model": model,
            "tokens_used": tokens_used,
            "elapsed_seconds": round(elapsed, 2),
            "actual_cost_ait": str(round(actual_cost, 6)),
            "contract_id": contract_id,
        },
        output_format,
    )
    if track:
        result_hash = hashlib.sha256(response_text.encode()).hexdigest()[:32]
        _track_coordinator_job(ctx, job_id, offer, wallet_address, provider_address, actual_cost, service_type, result_hash)


def _run_whisper(
    ctx: click.Context,
    offer: dict[str, Any],
    audio_file: str,
    wallet_address: str,
    private_key: str,
    language: str | None,
    task: str,
    fmt: str,
    output_format: str,
    track: bool = False,
    node_wallet: str | None = None,
) -> None:
    """Transcribe audio using a Whisper software offer and pay metered escrow."""
    import subprocess
    import urllib.request as _urllib

    config = get_config()
    chain_id = get_chain_id()

    offer.get("service_type", "")
    price = Decimal(str(offer.get("price", 0)))
    price_unit = offer.get("price_unit", "per_audio_min")
    provider_address = offer.get("provider_address", "")
    model = offer.get("model", "base")
    offer_id = offer.get("offer_id", "")

    whisper_endpoint = offer.get("public_endpoint") or offer.get("endpoint") or "http://localhost:8110"
    if not whisper_endpoint.startswith(("http://", "https://")):
        error(f"Rejecting offer with unsafe endpoint scheme: {whisper_endpoint}")
        raise click.Abort()
    whisper_base = whisper_endpoint.rstrip("/").removesuffix("/transcribe")
    whisper_transcribe_url = whisper_base + "/transcribe"
    info(f"Offer: whisper/{model} at {price} AIT/{price_unit} — provider {provider_address}")
    info(f"Whisper endpoint: {whisper_transcribe_url}")

    # Get audio duration for upfront escrow estimate
    duration_seconds = 0.0
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_file,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        duration_seconds = float(probe.stdout.strip() or 0)
    except Exception:
        logger.debug("ffprobe duration probe failed", exc_info=True)
        pass
    duration_minutes = duration_seconds / 60
    estimated_cost = Decimal(str(duration_minutes)) * price if price_unit == "per_audio_min" else price

    job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
    info(f"Audio duration: {duration_minutes:.2f} min — locking escrow: ~{estimated_cost:.8f} AIT")
    contract_id = _escrow_create(
        ctx,
        job_id,
        wallet_address,
        provider_address or wallet_address,
        estimated_cost,
        config,
        private_key=private_key,
        node_wallet=node_wallet,
    )

    # Submit audio to Whisper service
    info("Sending audio to Whisper service...")
    t_start = datetime.now()
    with open(audio_file, "rb") as af:
        audio_bytes = af.read()
    filename = os.path.basename(audio_file)
    boundary = b"----WhisperBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n" + audio_bytes + b"\r\n"
    )
    if language:
        body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="language"\r\n\r\n' + language.encode() + b"\r\n"
    body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="task"\r\n\r\n' + task.encode() + b"\r\n"
    body += b"--" + boundary + b"--\r\n"

    req = _urllib.Request(
        whisper_transcribe_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )
    with _urllib.urlopen(req, timeout=300) as resp:  # nosec B310 - endpoint scheme validated
        resp_data = json.loads(resp.read())

    elapsed = (datetime.now() - t_start).total_seconds()
    actual_duration_minutes = resp_data.get("duration_minutes", duration_minutes)
    actual_cost = Decimal(str(actual_duration_minutes)) * price if price_unit == "per_audio_min" else price
    result_hash = resp_data.get("result_hash", "")

    info(f"Done in {elapsed:.1f}s — {resp_data.get('duration_seconds', 0):.1f}s audio — actual cost: {actual_cost:.8f} AIT")

    # Post software_job TX as proof of work
    job_tx_hash = None
    if result_hash:
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        job_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": get_next_nonce(wallet_address),
            "type": "GPU_MARKETPLACE",
            "chain_id": chain_id,
            "payload": {
                "action": "software_job",
                "job_id": job_id,
                "offer_id": offer_id,
                "buyer_address": wallet_address,
                "provider_address": provider_address or wallet_address,
                "result_hash": result_hash,
                "actual_duration_minutes": float(round(actual_duration_minutes, 4)),
                "actual_cost": str(round(actual_cost, 6)),
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
            },
        }
        try:
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            job_result = http_client.post("/rpc/transactions/marketplace", json=job_data)
            job_tx_hash = job_result.get("transaction_hash")
            info(f"Job recorded on-chain: {job_tx_hash}")
        except Exception as e:
            warning(f"Failed to record job on-chain: {e} — continuing with escrow release")

    # Print transcript
    transcript = resp_data.get("text", "")
    if fmt == "text":
        click.echo(f"\n{transcript}\n")
    elif fmt == "srt":
        for i, seg in enumerate(resp_data.get("segments", []), 1):

            def _ts(s):
                return f"{int(s // 3600):02d}:{int((s % 3600) // 60):02d}:{s % 60:06.3f}".replace(".", ",")

            click.echo(f"{i}\n{_ts(seg['start'])} --> {_ts(seg['end'])}\n{seg['text']}\n")
    elif fmt == "json":
        click.echo(json.dumps(resp_data, indent=2))

    # Release metered escrow with job TX hash as proof
    if contract_id:
        rpc_url = _get_blockchain_rpc_url(config)
        rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        release_result = rpc_client.post(
            f"/rpc/escrow/{job_id}/release", json={"amount": str(actual_cost), "job_tx_hash": job_tx_hash}
        )
        if release_result and release_result.get("tx_hash"):
            released_amount = Decimal(release_result.get("released_amount", str(actual_cost)))
            success(
                f"Payment released: {released_amount:.8f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
            )
        else:
            warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

    output(
        {
            "job_id": job_id,
            "offer_id": offer_id,
            "model": model,
            "language": resp_data.get("language"),
            "duration_minutes": round(actual_duration_minutes, 4),
            "actual_cost_ait": str(round(actual_cost, 6)),
            "elapsed_seconds": round(elapsed, 2),
            "contract_id": contract_id,
        },
        output_format,
    )
    if track:
        _track_coordinator_job(ctx, job_id, offer, wallet_address, provider_address, actual_cost, "whisper", result_hash)


def _run_ffmpeg(
    ctx: click.Context,
    offer: dict[str, Any],
    input_file: str,
    wallet_address: str,
    private_key: str,
    output_container: str,
    codec: str,
    resolution: str,
    bitrate: str,
    output_format: str,
    track: bool = False,
    node_wallet: str | None = None,
) -> None:
    """Process video using an FFmpeg software offer and pay metered escrow."""
    import urllib.request as _urllib

    config = get_config()
    chain_id = get_chain_id()

    offer.get("service_type", "")
    price = Decimal(str(offer.get("price", 0)))
    price_unit = offer.get("price_unit", "per_processing_hour")
    provider_address = offer.get("provider_address", "")
    model = offer.get("model", "default")
    offer_id = offer.get("offer_id", "")

    info(f"Offer: ffmpeg/{model} at {price} AIT/{price_unit} — provider {provider_address}")
    info(f"Input file: {input_file}")

    ffmpeg_endpoint = offer.get("public_endpoint") or offer.get("endpoint") or "http://localhost:8230"
    if not ffmpeg_endpoint.startswith(("http://", "https://")):
        error(f"Rejecting offer with unsafe endpoint scheme: {ffmpeg_endpoint}")
        raise click.Abort()
    ffmpeg_base = ffmpeg_endpoint.rstrip("/").removesuffix("/process")
    ffmpeg_process_url = ffmpeg_base + "/process"
    info(f"FFmpeg endpoint: {ffmpeg_process_url}")

    # Estimate cost (assume 6 min default if unknown)
    estimated_hours = Decimal("0.1")
    estimated_cost = estimated_hours * price if price_unit == "per_processing_hour" else price
    info(f"Estimated duration: {estimated_hours:.2f} hours — locking escrow: ~{estimated_cost:.8f} AIT")

    job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
    contract_id = _escrow_create(
        ctx,
        job_id,
        wallet_address,
        provider_address or wallet_address,
        estimated_cost,
        config,
        private_key=private_key,
        node_wallet=node_wallet,
    )

    # Submit video to FFmpeg service
    info("Sending video to FFmpeg service...")
    t_start = datetime.now()
    with open(input_file, "rb") as af:
        video_bytes = af.read()
    filename = os.path.basename(input_file)
    boundary = b"----FFmpegBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n" + video_bytes + b"\r\n"
    )
    body += (
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="output_format"\r\n\r\n'
        + output_container.encode()
        + b"\r\n"
    )
    body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="codec"\r\n\r\n' + codec.encode() + b"\r\n"
    body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="resolution"\r\n\r\n' + resolution.encode() + b"\r\n"
    body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="bitrate"\r\n\r\n' + bitrate.encode() + b"\r\n"
    body += b"--" + boundary + b"--\r\n"

    req = _urllib.Request(
        ffmpeg_process_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )
    with _urllib.urlopen(req, timeout=3600) as resp:  # nosec B310 - endpoint scheme validated
        resp_data = json.loads(resp.read())

    elapsed = (datetime.now() - t_start).total_seconds()
    actual_hours = resp_data.get("processing_time_hours", estimated_hours)
    actual_cost = Decimal(str(actual_hours)) * price if price_unit == "per_processing_hour" else price
    result_hash = resp_data.get("result_hash", "")

    info(f"Done in {elapsed:.1f}s — {actual_hours:.4f} hours processing — actual cost: {actual_cost:.8f} AIT")
    info(f"Output file: {resp_data.get('output_path')}")

    # Post software_job TX as proof of work
    job_tx_hash = None
    if result_hash:
        job_data = {
            "from": wallet_address,
            "to": "0x0000000000000000000000000000000000000000",
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": get_next_nonce(wallet_address),
            "type": "GPU_MARKETPLACE",
            "chain_id": chain_id,
            "payload": {
                "action": "software_job",
                "job_id": job_id,
                "offer_id": offer_id,
                "buyer_address": wallet_address,
                "provider_address": provider_address or wallet_address,
                "result_hash": result_hash,
                "actual_processing_hours": float(round(actual_hours, 4)),
                "actual_cost": str(round(actual_cost, 6)),
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
            },
        }
        try:
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            http_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
            job_result = http_client.post("/rpc/transactions/marketplace", json=job_data)
            job_tx_hash = job_result.get("transaction_hash")
            info(f"Job recorded on-chain: {job_tx_hash}")
        except Exception as e:
            warning(f"Failed to record job on-chain: {e} — continuing with escrow release")

    # Release metered escrow with job TX hash as proof
    if contract_id:
        rpc_url = _get_blockchain_rpc_url(config)
        rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        release_result = rpc_client.post(
            f"/rpc/escrow/{job_id}/release", json={"amount": str(actual_cost), "job_tx_hash": job_tx_hash}
        )
        if release_result and release_result.get("tx_hash"):
            released_amount = Decimal(release_result.get("released_amount", str(actual_cost)))
            success(
                f"Payment released: {released_amount:.8f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
            )
        else:
            warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

    output(
        {
            "job_id": job_id,
            "offer_id": offer_id,
            "input_file": input_file,
            "output_path": resp_data.get("output_path"),
            "processing_hours": round(actual_hours, 4),
            "actual_cost_ait": str(round(actual_cost, 6)),
            "elapsed_seconds": round(elapsed, 2),
            "contract_id": contract_id,
        },
        output_format,
    )
    if track:
        _track_coordinator_job(ctx, job_id, offer, wallet_address, provider_address, actual_cost, "ffmpeg", result_hash)


@market.command(name="run")
@click.argument("offer_id_or_plugin_id")
@click.argument("prompt")
@click.option("--max-tokens", type=int, default=512, help="Max tokens to generate (Ollama)")
@click.option("--stream", is_flag=True, default=False, help="Stream the response (Ollama)")
@click.option("--language", default=None, help="Language code for Whisper (e.g. en, de)")
@click.option("--task", default="transcribe", type=click.Choice(["transcribe", "translate"]), help="Whisper task")
@click.option(
    "--transcript-format", "fmt", default="text", type=click.Choice(["text", "srt", "json"]), help="Whisper output format"
)
@click.option("--media-format", default="mp4", help="FFmpeg output container (e.g. mp4, webm)")
@click.option("--codec", default="h264", help="FFmpeg target codec (e.g. h264, vp9)")
@click.option("--resolution", default="1080p", help="FFmpeg target resolution (e.g. 1080p, 720p)")
@click.option("--bitrate", default="5M", help="FFmpeg target bitrate (e.g. 5M, 10M)")
@click.option("--track", is_flag=True, default=False, help="Create a coordinator job record after a successful run")
@click.option("--proposer", "proposer_id", default=None, help="Hub proposer address for escrow (defaults to HUB_PROPOSER_ID)")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def run_job(
    ctx: click.Context,
    offer_id_or_plugin_id: str,
    prompt: str,
    max_tokens: int,
    stream: bool,
    language: str | None,
    task: str,
    fmt: str,
    media_format: str,
    codec: str,
    resolution: str,
    bitrate: str,
    track: bool,
    proposer_id: str | None,
    output_format: str,
) -> None:
    """Run a software offer (Ollama/Whisper/FFmpeg) and pay metered escrow."""
    try:
        output_format = resolve_output_format(ctx, output_format)
        offer = _resolve_offer(ctx, offer_id_or_plugin_id)
        service_type = offer.get("service_type", "")

        wallet_address, private_key, _ = get_market_wallet(ctx, require_private_key=True)

        # Use explicit --proposer, then HUB_PROPOSER_ID, then local RPC proposer discovery.
        config = get_config()
        node_wallet = proposer_id or config.hub_proposer_id or None

        if service_type == "ollama":
            _run_ollama(
                ctx,
                offer,
                prompt,
                wallet_address,
                private_key,
                max_tokens,
                stream,
                output_format,
                track,
                node_wallet=node_wallet,
            )
        elif service_type == "whisper":
            if not os.path.exists(prompt):
                error(f"Whisper jobs require an audio file. File not found: {prompt}")
                raise click.Abort()
            _run_whisper(
                ctx,
                offer,
                prompt,
                wallet_address,
                private_key,
                language,
                task,
                fmt,
                output_format,
                track,
                node_wallet=node_wallet,
            )
        elif service_type == "ffmpeg":
            if not os.path.exists(prompt):
                error(f"FFmpeg jobs require a video file. File not found: {prompt}")
                raise click.Abort()
            _run_ffmpeg(
                ctx,
                offer,
                prompt,
                wallet_address,
                private_key,
                media_format,
                codec,
                resolution,
                bitrate,
                output_format,
                track,
                node_wallet=node_wallet,
            )
        elif service_type == "ipfs":
            error("IPFS hosting jobs are not supported via 'market run'. Use 'aitbc ipfs host' instead.")
            raise click.Abort()
        else:
            error(f"Service type '{service_type}' not yet supported via 'market run'")
            raise click.Abort()

    except Exception as e:
        error(f"Error running job: {e}")
        raise click.Abort() from e


@market.command(name="transcribe")
@click.argument("offer_id_or_plugin_id")
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("--language", default=None, help="Language code (e.g. en, de, fr). Auto-detect if omitted.")
@click.option(
    "--task", default="transcribe", type=click.Choice(["transcribe", "translate"]), help="transcribe or translate to English"
)
@click.option("--output-format", "fmt", default="text", type=click.Choice(["text", "srt", "json"]), help="Output format")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def transcribe_job(
    ctx,
    offer_id_or_plugin_id: str,
    audio_file: str,
    language: str | None,
    task: str,
    fmt: str,
    output_format: str,
):
    """Transcribe audio using a Whisper software offer and pay metered escrow"""
    try:
        output_format = resolve_output_format(ctx, output_format)
        offer = _resolve_offer(ctx, offer_id_or_plugin_id)
        wallet_address, private_key, _ = get_market_wallet(ctx, require_private_key=True)
        _run_whisper(ctx, offer, audio_file, wallet_address, private_key, language, task, fmt, output_format)
    except Exception as e:
        error(f"Error transcribing audio: {e}")
        raise click.Abort() from e


@market.command(name="process")
@click.argument("offer_id_or_plugin_id")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "output_container", default="mp4", help="Output format (e.g. mp4, webm)")
@click.option("--codec", default="h264", help="Target codec (e.g. h264, vp9, av1)")
@click.option("--resolution", default="1080p", help="Target resolution (e.g. 1080p, 720p, 480p)")
@click.option("--bitrate", default="5M", help="Target bitrate (e.g. 5M, 10M)")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def process_video(
    ctx,
    offer_id_or_plugin_id: str,
    input_file: str,
    output_container: str,
    codec: str,
    resolution: str,
    bitrate: str,
    output_format: str,
):
    """Process video using FFmpeg software offer and pay metered escrow"""
    try:
        output_format = resolve_output_format(ctx, output_format)
        offer = _resolve_offer(ctx, offer_id_or_plugin_id)
        wallet_address, private_key, _ = get_market_wallet(ctx, require_private_key=True)
        _run_ffmpeg(
            ctx, offer, input_file, wallet_address, private_key, output_container, codec, resolution, bitrate, output_format
        )
    except Exception as e:
        error(f"Error processing video: {e}")
        raise click.Abort() from e
