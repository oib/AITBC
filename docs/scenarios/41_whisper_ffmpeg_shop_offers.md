# Scenario 41: Whisper and FFmpeg default shop offers

## Goal

Run non-inference jobs on the GPU shop: audio transcription with OpenAI Whisper
and media re-encoding with FFmpeg. The shop advertises these capabilities and
marketplace offers exist for them.

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

5. Verify marketplace service offers:
   ```bash
   curl -s http://<hub>:8102/v1/marketplace/offers?gpu_model=RTX+4060+Ti
   ```
   Look for offers whose `attributes.service_type` is `whisper` or `ffmpeg`.

## Notes

- The miner advertises `transcribe` and `reencode` in its `supported_tasks`.
- The `aitbc-whisper` service runs on port `8110`; `aitbc-ffmpeg` runs on port
  `8230`.
- The canonical CLI `aitbc ai submit` accepts `--type`, `--input`, and
  `--output-format`.
- `aitbc market offer` on-chain listing currently requires a provider bond and
  correct `0x` address spelling; the service-level marketplace offers in
  step 5 are a working default-shop alternative.
