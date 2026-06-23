"""
Job commands: run, transcribe, transcode, process
"""

import hashlib
import json
import os
from datetime import datetime

import click

from ...config import get_config
from ...utils import error, info, output, success, warning
from ...utils.http_client import AITBCHTTPClient, get_logger

# Initialize logger
logger = get_logger(__name__)

from . import get_chain_id, get_next_nonce, get_wallet_address, market
from .escrow import _escrow_create, _get_blockchain_rpc_url


@market.command(name="run")
@click.argument("offer_id")
@click.argument("prompt")
@click.option("--max-tokens", type=int, default=512, help="Max tokens to generate")
@click.option("--stream", is_flag=True, default=False, help="Stream the response")
@click.pass_context
def run_job(ctx, offer_id: str, prompt: str, max_tokens: int, stream: bool):
    """Run an inference job against a software offer and pay metered escrow"""
    try:
        config = get_config()
        _ = get_chain_id()
        wallet_address = get_wallet_address()

        # Resolve the offer from hub transactions
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get("payload", {})
                if p.get("action") == "software_offer" and p.get("offer_id") == offer_id:
                    offer = p
                    break
        if not offer:
            error(f"Software offer '{offer_id}' not found or not active on hub")
            raise click.Abort()

        service_type = offer.get("service_type")
        model = offer.get("model")
        price = float(offer.get("price", 0))
        price_unit = offer.get("price_unit", "per_1k_tokens")
        provider_address = offer.get("provider_address")

        info(f"Offer: {service_type} — {model} at {price} AIT/{price_unit}")
        info(f"Provider: {provider_address}")

        if service_type != "ollama":
            error(f"Service type '{service_type}' job execution not yet supported via CLI")
            raise click.Abort()

        # Lock escrow upfront (estimated max cost)
        estimated_tokens = max_tokens
        estimated_cost = (estimated_tokens / 1000) * price
        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        info(f"Locking escrow: ~{estimated_cost:.4f} AIT (est. {estimated_tokens} tokens)")
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Run inference via Ollama
        import urllib.request

        payload = json.dumps(
            {"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": max_tokens}}
        ).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        info("Running inference...")
        t_start = datetime.now()
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_data = json.loads(resp.read())
        elapsed = (datetime.now() - t_start).total_seconds()

        response_text = resp_data.get("response", "")
        tokens_used = resp_data.get("eval_count", len(response_text.split()) * 2)
        actual_cost = (tokens_used / 1000) * price

        info(f"Done in {elapsed:.2f}s — {tokens_used} tokens — actual cost: {actual_cost:.4f} AIT")
        click.echo(f"\n{response_text}\n")

        # Release metered escrow for actual tokens used
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(
                f"/rpc/escrow/{job_id}/release",
                json={
                    "amount": actual_cost,
                    "tokens_used": tokens_used,
                    "job_id": job_id,
                },
            )
            if release_result and release_result.get("tx_hash"):
                success(
                    f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
                )
            else:
                warning("Escrow release submitted but no tx_hash returned")
        else:
            warning("No escrow contract — payment not released")

        output(
            {
                "job_id": job_id,
                "offer_id": offer_id,
                "model": model,
                "tokens_used": tokens_used,
                "elapsed_seconds": round(elapsed, 2),
                "actual_cost_ait": round(actual_cost, 6),
                "contract_id": contract_id,
            },
            ctx.obj.get("output_format", "table"),
        )

    except Exception as e:
        error(f"Error running job: {e}")
        raise click.Abort() from e


@market.command(name="transcribe")
@click.argument("offer_id")
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("--language", default=None, help="Language code (e.g. en, de, fr). Auto-detect if omitted.")
@click.option(
    "--task", default="transcribe", type=click.Choice(["transcribe", "translate"]), help="transcribe or translate to English"
)
@click.option("--output-format", "fmt", default="text", type=click.Choice(["text", "srt", "json"]), help="Output format")
@click.pass_context
def transcribe_job(ctx, offer_id: str, audio_file: str, language: str | None, task: str, fmt: str):
    """Transcribe audio using a Whisper software offer and pay metered escrow"""
    import urllib.request as _urllib

    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get("payload", {})
                if (
                    p.get("action") == "software_offer"
                    and p.get("offer_id") == offer_id
                    and p.get("service_type") == "whisper"
                ):
                    offer = p
                    break
        if not offer:
            error(f"Whisper offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get("price", 0))
        price_unit = offer.get("price_unit", "per_audio_min")
        provider_address = offer.get("provider_address")
        model = offer.get("model", "base")
        # Use provider's public endpoint from offer; fall back to localhost for self-hosted
        whisper_endpoint = offer.get("endpoint", "http://localhost:8110")
        # Normalise: strip trailing /whisper path if present, add /transcribe
        whisper_base = whisper_endpoint.rstrip("/").removesuffix("/transcribe")
        whisper_transcribe_url = whisper_base + "/transcribe"
        info(f"Offer: whisper/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Whisper endpoint: {whisper_transcribe_url}")

        # Get audio duration via ffprobe for upfront escrow estimate
        import subprocess

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
            pass
        duration_minutes = duration_seconds / 60
        estimated_cost = duration_minutes * price if price_unit == "per_audio_min" else price

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        info(f"Audio duration: {duration_minutes:.2f} min — locking escrow: ~{estimated_cost:.4f} AIT")
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

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
            body += (
                b"--" + boundary + b'\r\nContent-Disposition: form-data; name="language"\r\n\r\n' + language.encode() + b"\r\n"
            )
        body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="task"\r\n\r\n' + task.encode() + b"\r\n"
        body += b"--" + boundary + b"--\r\n"

        req = _urllib.Request(
            whisper_transcribe_url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"}
        )
        with _urllib.urlopen(req, timeout=300) as resp:
            resp_data = json.loads(resp.read())

        elapsed = (datetime.now() - t_start).total_seconds()
        actual_duration_minutes = resp_data.get("duration_minutes", duration_minutes)
        actual_cost = actual_duration_minutes * price if price_unit == "per_audio_min" else price
        result_hash = resp_data.get("result_hash", "")

        info(
            f"Done in {elapsed:.1f}s — {resp_data.get('duration_seconds', 0):.1f}s audio — actual cost: {actual_cost:.4f} AIT"
        )

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
            job_data = {
                "from": wallet_address,
                "to": "0x0000000000000000000000000000000000000000",
                "amount": 0,
                "fee": 36,
                "nonce": get_next_nonce(),
                "type": "GPU_MARKETPLACE",
                "chain_id": chain_id,
                "payload": {
                    "action": "software_job",
                    "job_id": job_id,
                    "offer_id": offer_id,
                    "buyer_address": wallet_address,
                    "provider_address": provider_address or wallet_address,
                    "result_hash": result_hash,
                    "actual_duration_minutes": round(actual_duration_minutes, 4),
                    "actual_cost": round(actual_cost, 6),
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
                f"/rpc/escrow/{job_id}/release", json={"amount": actual_cost, "job_tx_hash": job_tx_hash}
            )
            if release_result and release_result.get("tx_hash"):
                success(
                    f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
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
                "actual_cost_ait": round(actual_cost, 6),
                "elapsed_seconds": round(elapsed, 2),
                "contract_id": contract_id,
            },
            ctx.obj.get("output_format", "table"),
        )

    except Exception as e:
        error(f"Error transcribing audio: {e}")
        raise click.Abort() from e


@market.command(name="transcode")
@click.argument("offer_id")
@click.argument("video_url")
@click.option("--resolution", default="1080p", help="Target resolution (e.g. 1080p, 720p, 480p)")
@click.option("--codec", default="h264", help="Target codec (e.g. h264, vp9, av1)")
@click.option("--format", default="mp4", help="Output format (e.g. mp4, webm)")
@click.pass_context
def transcode_job(ctx, offer_id: str, video_url: str, resolution: str, codec: str, format: str):
    """Transcode video using a peertube_transcoder software offer and pay metered escrow"""
    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get("payload", {})
                if (
                    p.get("action") == "software_offer"
                    and p.get("offer_id") == offer_id
                    and p.get("service_type") == "peertube_transcoder"
                ):
                    offer = p
                    break
        if not offer:
            error(f"PeerTube transcoder offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get("price", 0))
        price_unit = offer.get("price_unit", "per_video_min")
        provider_address = offer.get("provider_address")
        model = offer.get("model", "default")

        info(f"Offer: peertube_transcoder/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Video URL: {video_url}")

        # Estimate cost (assume 5 min default if unknown)
        transcode_endpoint = offer.get("endpoint", "http://localhost:8220")
        estimated_minutes = 5.0
        estimated_cost = estimated_minutes * price if price_unit == "per_video_min" else price
        info(f"Estimated duration: {estimated_minutes:.1f} min — locking escrow: ~{estimated_cost:.4f} AIT")

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

        # Run actual transcode
        info("Running PeerTube transcoding...")
        t_start = datetime.now()
        transcode_client = AITBCHTTPClient(base_url=transcode_endpoint, timeout=600)
        transcode_result = transcode_client.post(
            "/transcode",
            json={
                "video_url": video_url,
                "target_resolution": resolution,
                "target_codec": codec,
                "output_format": format,
            },
        )
        elapsed = (datetime.now() - t_start).total_seconds()

        actual_minutes = transcode_result.get("duration_seconds", estimated_minutes * 60) / 60
        actual_cost = actual_minutes * price if price_unit == "per_video_min" else price
        result_hash = transcode_result.get("result_hash", "")

        info(f"Done in {elapsed:.1f}s — {actual_minutes:.2f} min video — actual cost: {actual_cost:.4f} AIT")
        info(f"Transcoded URL: {transcode_result.get('transcoded_url')}")

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            job_data = {
                "from": wallet_address,
                "to": "0x0000000000000000000000000000000000000000",
                "amount": 0,
                "fee": 36,
                "nonce": get_next_nonce(),
                "type": "GPU_MARKETPLACE",
                "chain_id": chain_id,
                "payload": {
                    "action": "software_job",
                    "job_id": job_id,
                    "offer_id": offer_id,
                    "buyer_address": wallet_address,
                    "provider_address": provider_address or wallet_address,
                    "result_hash": result_hash,
                    "actual_video_minutes": round(actual_minutes, 4),
                    "actual_cost": round(actual_cost, 6),
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

        # Release metered escrow with job TX hash as proof
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(
                f"/rpc/escrow/{job_id}/release", json={"amount": actual_cost, "job_tx_hash": job_tx_hash}
            )
            if release_result and release_result.get("tx_hash"):
                success(
                    f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
                )
            else:
                warning("Escrow released (no on-chain tx — sub-threshold amount or same-wallet)")

        output(
            {
                "job_id": job_id,
                "offer_id": offer_id,
                "video_url": video_url,
                "transcoded_url": transcode_result.get("transcoded_url"),
                "duration_minutes": round(actual_minutes, 4),
                "actual_cost_ait": round(actual_cost, 6),
                "elapsed_seconds": round(elapsed, 2),
                "contract_id": contract_id,
            },
            ctx.obj.get("output_format", "table"),
        )

    except Exception as e:
        error(f"Error transcoding video: {e}")
        raise click.Abort() from e


@market.command(name="process")
@click.argument("offer_id")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", default="mp4", help="Output format (e.g. mp4, webm)")
@click.option("--codec", default="h264", help="Target codec (e.g. h264, vp9, av1)")
@click.option("--resolution", default="1080p", help="Target resolution (e.g. 1080p, 720p, 480p)")
@click.option("--bitrate", default="5M", help="Target bitrate (e.g. 5M, 10M)")
@click.pass_context
def process_video(ctx, offer_id: str, input_file: str, format: str, codec: str, resolution: str, bitrate: str):
    """Process video using FFmpeg software offer and pay metered escrow"""
    import urllib.request as _urllib

    try:
        config = get_config()
        wallet_address = get_wallet_address()
        chain_id = get_chain_id()

        # Resolve the offer from hub
        hub_url = f"http://{config.hub_discovery_url or 'hub.aitbc.bubuit.net'}"
        http_client = AITBCHTTPClient(base_url=hub_url, timeout=15)
        result = http_client.get("/rpc/transactions", params={"limit": 1000})
        offer = None
        if result and not isinstance(result, dict):
            for tx in result:
                p = tx.get("payload", {})
                if p.get("action") == "software_offer" and p.get("offer_id") == offer_id and p.get("service_type") == "ffmpeg":
                    offer = p
                    break
        if not offer:
            error(f"FFmpeg offer '{offer_id}' not found on hub")
            raise click.Abort()

        price = float(offer.get("price", 0))
        price_unit = offer.get("price_unit", "per_processing_hour")
        provider_address = offer.get("provider_address")
        model = offer.get("model", "default")

        info(f"Offer: ffmpeg/{model} at {price} AIT/{price_unit} — provider {provider_address}")
        info(f"Input file: {input_file}")

        # Use provider's public endpoint from offer; fall back to localhost for self-hosted
        ffmpeg_endpoint = offer.get("endpoint", "http://localhost:8230")
        # Normalise: strip trailing /process if present, add /process
        ffmpeg_base = ffmpeg_endpoint.rstrip("/").removesuffix("/process")
        ffmpeg_process_url = ffmpeg_base + "/process"
        info(f"FFmpeg endpoint: {ffmpeg_process_url}")

        # Estimate cost (assume 5 min default if unknown)
        estimated_hours = 0.1  # 6 minutes default
        estimated_cost = estimated_hours * price if price_unit == "per_processing_hour" else price
        info(f"Estimated duration: {estimated_hours:.2f} hours — locking escrow: ~{estimated_cost:.4f} AIT")

        job_id = f"sw_job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.sha256(f'{offer_id}{wallet_address}'.encode()).hexdigest()[:8]}"
        contract_id = _escrow_create(job_id, wallet_address, provider_address or wallet_address, estimated_cost, config)

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
            b"--" + boundary + b'\r\nContent-Disposition: form-data; name="output_format"\r\n\r\n' + format.encode() + b"\r\n"
        )
        body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="codec"\r\n\r\n' + codec.encode() + b"\r\n"
        body += (
            b"--" + boundary + b'\r\nContent-Disposition: form-data; name="resolution"\r\n\r\n' + resolution.encode() + b"\r\n"
        )
        body += b"--" + boundary + b'\r\nContent-Disposition: form-data; name="bitrate"\r\n\r\n' + bitrate.encode() + b"\r\n"
        body += b"--" + boundary + b"--\r\n"

        req = _urllib.Request(
            ffmpeg_process_url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"}
        )
        with _urllib.urlopen(req, timeout=3600) as resp:
            resp_data = json.loads(resp.read())

        elapsed = (datetime.now() - t_start).total_seconds()
        actual_hours = resp_data.get("processing_time_hours", estimated_hours)
        actual_cost = actual_hours * price if price_unit == "per_processing_hour" else price
        result_hash = resp_data.get("result_hash", "")

        info(f"Done in {elapsed:.1f}s — {actual_hours:.4f} hours processing — actual cost: {actual_cost:.4f} AIT")
        info(f"Output file: {resp_data.get('output_path')}")

        # Post software_job TX on-chain as proof of work
        job_tx_hash = None
        if result_hash:
            job_data = {
                "from": wallet_address,
                "to": "0x0000000000000000000000000000000000000000",
                "amount": 0,
                "fee": 36,
                "nonce": get_next_nonce(),
                "type": "GPU_MARKETPLACE",
                "chain_id": chain_id,
                "payload": {
                    "action": "software_job",
                    "job_id": job_id,
                    "offer_id": offer_id,
                    "buyer_address": wallet_address,
                    "provider_address": provider_address or wallet_address,
                    "result_hash": result_hash,
                    "actual_processing_hours": round(actual_hours, 4),
                    "actual_cost": round(actual_cost, 6),
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

        # Release metered escrow with job TX hash as proof
        if contract_id:
            rpc_url = _get_blockchain_rpc_url(config)
            rpc_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
            release_result = rpc_client.post(
                f"/rpc/escrow/{job_id}/release", json={"amount": actual_cost, "job_tx_hash": job_tx_hash}
            )
            if release_result and release_result.get("tx_hash"):
                success(
                    f"Payment released: {actual_cost:.4f} AIT → {provider_address} (tx: {release_result['tx_hash'][:18]}...)"
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
                "actual_cost_ait": round(actual_cost, 6),
                "elapsed_seconds": round(elapsed, 2),
                "contract_id": contract_id,
            },
            ctx.obj.get("output_format", "table"),
        )

    except Exception as e:
        error(f"Error processing video: {e}")
        raise click.Abort() from e
