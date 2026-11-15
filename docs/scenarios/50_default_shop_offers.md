# Scenario 50: Default Whisper, FFmpeg, and Ollama shop offers

> **Fleet note (#1549):** on the public island, `aitbc-whisper`, `aitbc-ffmpeg`,
> and `aitbc-hermes` shop units are **not deployed** — their `/etc/aitbc` env
> files are orphans. The **live default product path** is Ollama inference via
> scenario **34** (`aitbc ai submit` / `aitbc market run` against shop Ollama
> offers). Whisper and FFmpeg steps below are an **optional appendix** for nodes
> where those units exist; do not treat them as the default customer journey on
> pub island. Hermes is not a default shop offer — omit `aitbc market hermes`
> unless an operator explicitly restores that unit.

## Goal

The shop (`<node2>`) can publish default software offers for Ollama inference
(and, when the optional units are installed, Whisper transcription and FFmpeg
video processing) when the miner starts. A customer on the hub discovers active
offers with `aitbc market list`, then runs paid jobs with `aitbc market run`
(Ollama — live path) and, where deployed, `aitbc market transcribe` /
`aitbc market process`.

This closes the P2.5 documentation gap: Whisper and FFmpeg were written into
the miner's default-offer loop before the fleet retired those units.

## Preconditions

- `<node2>` has `aitbc-miner` running and an Ollama model such as `llama3.2:3b`
  (required on pub island).
- Optional: `aitbc-whisper` (port 8110) and `aitbc-ffmpeg` (port 8230) only when
  those units are installed on the shop node.
- Nginx on `<node2>` exposes `/whisper/`, `/ffmpeg/`, and `/ollama/` to the
  public hostname.
- The customer wallet on `<hub-node>` has a non-zero `AIT` balance.

## Steps

### 1. Verify the shop published default offers

On `<node2>`, restart or watch the miner logs:

```bash
ssh <node2>
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

On `<hub-node>`:

```bash
aitbc market list
```

Expected output includes active offers:

- `whisper-base` — `0.02000000 per_audio_min`
- `ffmpeg-h264-transcode` — `0.00500000 per_processing_hour`
- `ollama-llama3.2-3b` — `0.00100000 per_1k_tokens`

### 3. Run an Ollama inference job (live default)

```bash
aitbc market run --offer-id-or-plugin-id <ollama-offer-id> --prompt "What is AITBC?"
```

Expected result:

- `Running inference...`
- A generated response is printed.
- `Payment released: ... AIT`

### 4. (Optional appendix) Run a Whisper transcription job

Create or copy a short audio file and run:

```bash
# on <hub-node>
ffmpeg -f lavfi -i "sine=frequency=1000:duration=30" -ac 1 /tmp/test_audio.wav -y
aitbc market transcribe --offer-id-or-plugin-id <whisper-offer-id> --audio-file /tmp/test_audio.wav
```

Expected result:

- `Escrow created`
- `Sending audio to Whisper service...`
- `Payment released: ... AIT`
- `actual_cost_ait` is based on the audio duration and the price.

### 5. (Optional appendix) Run a FFmpeg re-encode job

Create or copy a short video and run:

```bash
# on <hub-node>
ffmpeg -f lavfi -i testsrc=duration=10:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=10 \
       -c:v libx264 -c:a aac /tmp/test_video.mp4 -y
aitbc market process --offer-id-or-plugin-id <ffmpeg-offer-id> --input-file /tmp/test_video.mp4 \
       --resolution 720p --output-container mp4 --codec h264
```

Expected result:

- `Escrow created`
- `Sending video to FFmpeg service...`
- `Output file: ...`
- `Payment released: ... AIT`

<!-- COVERAGE-LEFT-1: market leaves that lost their home when scenario 08 was archived (issue #445) -->

### 6. Read-only market views

These only read the marketplace service or chain state:

```bash
aitbc market providers
aitbc market jobs
aitbc market match
aitbc market offer-list
aitbc market payment
aitbc market status --order-id <order-id>
aitbc market ratings --service-id <service-id>
aitbc market gpu status --job-id <job-id>
aitbc market gpu quote --gpu-id <gpu-id> --buyer-id <buyer-id>
aitbc market exchange price
aitbc market exchange status
aitbc market exchange list-deposits
```

### 7. Fund-moving and state-changing market calls

Documented for coverage; each moves funds or mutates market/service state — not played, needs the operator's line.

- `aitbc market cancel --job-id <job-id>` — cancels a market job.
- `aitbc market escrow create --job-id <job-id> --buyer <addr> --provider <addr>` — locks buyer funds in escrow.
- `aitbc market escrow release --job-id <job-id>` — releases escrowed funds to the provider.
- `aitbc market gpu buy --gpu-id <id> --buyer-id <id> --job-id <id> --duration-hours <n>` — paid GPU purchase.
- `aitbc market gpu refund --job-id <job-id>` — refunds a GPU job payment.
- `aitbc market gpu release --job-id <job-id>` — releases a GPU job payment.
- `aitbc market exchange deposit-eth --amount <units>` — deposits ETH into the exchange.
- `aitbc market exchange mint-ait --deposit-id <id>` — mints AIT against a deposit.
- `aitbc market exchange withdraw-eth --amount <units> --address <addr>` — withdraws ETH from the exchange.
- `aitbc market hermes --offer-id-or-plugin-id <id> --prompt <text>` — paid Hermes job (unit not deployed on pub island; documented for coverage only).
- `aitbc market offer-cancel --order-ids <ids>` — cancels published offers.
- `aitbc market offer-disable --plugin-id <id>` — disables an offer plugin.
- `aitbc market rate --service-id <id> --rating <n>` — writes a service rating.
- `aitbc market sync-ratings --remote-url <url>` — pulls/pushes rating state.

## Validation

- `aitbc market list` shows the default offers with `Status: active`.
- The miner logs show the default offer publishes on startup and every
  `OFFER_PUBLISH_INTERVAL` (default 300 s).
- Each CLI job ends with a released payment and a non-empty result.

## Notes

- The `aitbc-miner` default offer set is configured in
  `apps/miner/production_miner.py` (`DEFAULT_SOFTWARE_OFFERS`).
- The CLI resolves the offer on-chain, then calls the provider's public
  endpoint (e.g. `https://shop.example.net/whisper`).
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
