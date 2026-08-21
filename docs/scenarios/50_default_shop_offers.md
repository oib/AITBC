# Scenario 50: Default Whisper, FFmpeg, and Ollama shop offers

## Goal

The shop (`aitbc3`) publishes default software offers for Whisper transcription,
FFmpeg video processing, and Ollama inference automatically when the miner
starts. A customer on the hub can discover them with `aitbc market list`, then
run paid jobs with `aitbc market transcribe`, `aitbc market process`, and
`aitbc market run`.

This closes the P2.5 gap: the Whisper and FFmpeg services already existed, but
they were not in the miner's default shop loop.

## Preconditions

- `aitbc3` has `aitbc-whisper` (port 8110), `aitbc-ffmpeg` (port 8230), and
  `aitbc-miner` running.
- `aitbc3` has an Ollama model such as `llama3.2:3b`.
- Nginx on `aitbc3` exposes `/whisper/`, `/ffmpeg/`, and `/ollama/` to the
  public hostname.
- The customer wallet on `hub.aitbc` has a non-zero `AIT` balance.

## Steps

### 1. Verify the shop published default offers

On `aitbc3`, restart or watch the miner logs:

```bash
ssh aitbc3
sudo systemctl restart aitbc-miner
journalctl -u aitbc-miner -n 40 --no-pager
```

Expected log lines:

```text
Published default offer: whisper/base
Published default offer: ffmpeg/h264-transcode
Published default offer: ollama/llama3.2:3b
```

### 2. List the default offers from the hub

On `hub.aitbc`:

```bash
aitbc market list
```

Expected output includes active offers:

- `whisper-base` — `0.02000000 per_audio_min`
- `ffmpeg-h264-transcode` — `0.00500000 per_processing_hour`
- `ollama-llama3.2-3b` — `0.00100000 per_1k_tokens`

### 3. Run a Whisper transcription job

Create or copy a short audio file and run:

```bash
# on hub.aitbc
ffmpeg -f lavfi -i "sine=frequency=1000:duration=30" -ac 1 /tmp/test_audio.wav -y
aitbc market transcribe <whisper-offer-id> /tmp/test_audio.wav
```

Expected result:

- `Escrow created`
- `Sending audio to Whisper service...`
- `Payment released: ... AIT`
- `actual_cost_ait` is based on the audio duration and the price.

### 4. Run a FFmpeg re-encode job

Create or copy a short video and run:

```bash
# on hub.aitbc
ffmpeg -f lavfi -i testsrc=duration=10:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=10 \
       -c:v libx264 -c:a aac /tmp/test_video.mp4 -y
aitbc market process <ffmpeg-offer-id> /tmp/test_video.mp4 \
       --resolution 720p --format mp4 --codec h264
```

Expected result:

- `Escrow created`
- `Sending video to FFmpeg service...`
- `Output file: ...`
- `Payment released: ... AIT`

### 5. Run an Ollama inference job

```bash
aitbc market run <ollama-offer-id> "What is AITBC?"
```

Expected result:

- `Running inference...`
- A generated response is printed.
- `Payment released: ... AIT`

## Validation

- `aitbc market list` shows the default offers with `Status: active`.
- The miner logs show the default offer publishes on startup and every
  `OFFER_PUBLISH_INTERVAL` (default 300 s).
- Each CLI job ends with a released payment and a non-empty result.

## Notes

- The `aitbc-miner` default offer set is configured in
  `apps/miner/production_miner.py` (`DEFAULT_SOFTWARE_OFFERS`).
- The CLI resolves the offer on-chain, then calls the provider's public
  endpoint (e.g. `https://aitbc3.aitbc.bubuit.net/whisper`).
- `aitbc market offer` no longer requires an on-chain bond for software-only
  listings (hardware GPU bundles still require one if `MARKET_BOND_MIN_AMOUNT` is
  set above 0).
- The on-chain `software_job` proof-of-work transaction currently requires a
  signature and may return `400`; the escrow release still happens and the job
  succeeds.

## Related files

- `apps/miner/production_miner.py` — default shop offer loop
- `cli/aitbc_cli/commands/market/__init__.py` — wallet selection and island
  fallback for shop nodes
- `cli/aitbc_cli/commands/market/offers.py` — `aitbc market offer` command
- `cli/aitbc_cli/commands/market/jobs.py` — `transcribe`, `process`, and `run`
- `apps/ffmpeg/main.py` — FFmpeg service codec mapping
- `examples/nginx/nginx-aitbc.conf.example` — service routing template
