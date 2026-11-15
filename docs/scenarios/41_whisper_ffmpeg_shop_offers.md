# Scenario 41: Whisper and FFmpeg default shop offers

> **Fleet note (#1549):** `aitbc-whisper` and `aitbc-ffmpeg` units are **not
> deployed** on the public island. This play is **not** the default live customer
> path — use scenario **34** (Ollama / `aitbc ai submit`) for product validation.
> Run the steps below only on a shop node where whisper/ffmpeg units exist, or
> treat them as a design reference.

## Goal

Run non-inference jobs on a GPU shop **when** Whisper and FFmpeg services are
installed: audio transcription and media re-encoding. The shop advertises these
capabilities and market offers exist for them.

## Preconditions

- GPU shop has `aitbc-whisper` and `aitbc-ffmpeg` services running.
- Customer wallet has balance on the hub.
- `SHOP_WALLET_ADDRESS` is set to the provider address.

## Steps

1. Submit a transcription job:
   ```bash
   export CUSTOMER_WALLET_ADDRESS=<customer>
   export SHOP_WALLET_ADDRESS=<shop>
   aitbc ai submit --payment 3 --type transcribe \
     --input "https://github.com/openai/whisper/raw/main/tests/jfk.flac" \
     --model base
   ```

2. Wait for status. Expected result:
   - `state`: `COMPLETED`
   - `payment_status`: `released`
   - `result.output`: the transcribed text

3. Submit a re-encode job:
   ```bash
   aitbc ai submit --payment 3 --type reencode \
     --input "https://github.com/openai/whisper/raw/main/tests/jfk.flac" \
     --output-format mp3
   ```

4. Wait for status. Expected result:
   - `state`: `COMPLETED`
   - `payment_status`: `released`
   - `result.output_format`: `mp3`
   - `result.output_size_bytes`: > 0

5. Verify market service offers with the CLI (`aitbc market list` reads
   the same market service the curl call hit):
   ```bash
   aitbc market list --service-type whisper
   aitbc market list --service-type ffmpeg
   ```
   Look for active offers on the shop's provider address.

## Notes

- The miner advertises `transcribe` and `reencode` in its `supported_tasks`.
- The `aitbc-whisper` service runs on port `8110`; `aitbc-ffmpeg` runs on port
  `8230`.
- The canonical CLI `aitbc ai submit` accepts `--type`, `--input`, and
  `--output-format`.
- `aitbc market offer` on-chain listing currently requires a provider bond and
  correct `0x` address spelling; the service-level market offers in
  step 5 are a working default-shop alternative.
