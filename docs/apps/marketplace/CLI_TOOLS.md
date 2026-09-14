# AITBC CLI Marketplace Tools

## Overview

The `aitbc` CLI (0.10.18) exposes the marketplace through the top-level **`aitbc market`** group: GPU/software offers published by shop miners and backed by the coordinator, paid job execution with metered on-chain escrow, IPFS hosting rentals, protected fixed-duration GPU rentals, ratings, and the ETH↔AIT exchange bridge.

> **There is no `aitbc marketplace` command group.** The old global chain-listings group has been removed from the CLI; `aitbc market` is the only marketplace surface. The related `aitbc operations …` group still exists but is deprecated and hidden from `aitbc --help`.

All `aitbc market` subcommands share the group-level wallet options:

```bash
aitbc market --wallet <name> <command> …
aitbc market --wallet-path /path/to/wallet.json --password-file /path/to/pw <command> …
```

The global `--output table|json|yaml|csv` option applies to most commands.

## Marketplace Command Group (`aitbc market`)

### Offers (provider/shop side)

#### Publish an offer

`aitbc market offer` lists a hardware and software bundle offer. `--service-type` is one of `ollama`, `whisper`, `ffmpeg`, `ipfs`, `hermes`. GPU details are auto-detected from `nvidia-smi` when omitted; a `--model-or-variant` ending in `:cloud` marks a cloud deployment; `ipfs` offers need no GPU.

```bash
# Ollama inference offer, priced per 1k tokens (default unit)
aitbc market offer --service-type ollama --model-or-variant llama3 --price 1.0

# Whisper transcription offer, priced per audio minute
aitbc market offer --service-type whisper --model-or-variant base --price 0.5 --unit per_audio_min

# Hermes agent offer, priced per minute
aitbc market offer --service-type hermes --model-or-variant default --price 0.1 --unit per_minute

# IPFS hosting offer with a per-customer disk quota
aitbc market offer --service-type ipfs --model-or-variant ipfs-host --price 0.2 --unit per_day --disk-quota-mb 100
```

Other options: `--unit` (`per_1k_tokens`, `per_audio_min`, `per_gb`, `per_processing_hour`, `per_minute`, `per_day`), `--description`, `--context-window`, `--gpu-name`, `--gpu-device`, `--gpu-offer-id`.

#### List and manage offers

```bash
# List all marketplace offers (optionally filtered / sorted)
aitbc market list
aitbc market list --service-type ollama --status active
aitbc market list --provider 0x…
aitbc market list --sort reputation        # also: price | availability | default
aitbc market list --mine                   # only offers from the local wallet/node

# List software offers published by this provider
aitbc market offer-list
aitbc market offer-list --service-type ipfs --status active

# Disable/unregister an offer by plugin ID
aitbc market offer-disable --plugin-id ipfs-ipfs-host
```

There is no CLI command to re-enable a disabled offer or to update pricing in place — publish a new offer and disable the old one.

### Running paid jobs (buyer side)

#### `aitbc market run` — one command per service type

Runs a software offer and pays metered escrow. What `--prompt` means depends on the offer's `service_type`: a text prompt for `ollama`, an audio file path for `whisper`, a video file path for `ffmpeg`, a prompt for `hermes`, and a CID-or-file for `ipfs` hosting.

```bash
# Ollama inference
aitbc market run --offer-id-or-plugin-id offer-1 --prompt 'hello' --max-tokens 256 --stream

# Whisper transcription (prompt is an audio file path)
aitbc market run --offer-id-or-plugin-id offer-1 --prompt /tmp/audio.mp3 --language en --task transcribe --transcript-format srt

# FFmpeg video processing (prompt is a video file path)
aitbc market run --offer-id-or-plugin-id offer-1 --prompt /tmp/in.mp4 --media-format webm --codec vp9 --resolution 720p --bitrate 10M

# Hermes agent prompt
aitbc market run --offer-id-or-plugin-id offer-1 --prompt 'explain quantum computing' --max-time 120

# IPFS hosting (prompt is a CID or local file)
aitbc market run --offer-id-or-plugin-id ipfs-ipfs-host --prompt Qm… --days 7 --pin

# Record the job on the coordinator after a successful run
aitbc market run --offer-id-or-plugin-id offer-1 --prompt 'hello' --track --proposer 0x…
```

#### Convenience wrappers

```bash
# Whisper transcription
aitbc market transcribe --offer-id-or-plugin-id offer-1 --audio-file /tmp/audio.mp3 \
  [--language en] [--task translate] [--output-format text|srt|json]

# FFmpeg video processing
aitbc market process --offer-id-or-plugin-id offer-1 --input-file /tmp/in.mp4 \
  [--output-container webm] [--codec vp9] [--resolution 720p] [--bitrate 10M]

# Hermes one-shot prompt
aitbc market hermes --offer-id-or-plugin-id hermes-default --prompt 'write a python fibonacci function' \
  [--max-time 120] [--track] [--proposer 0x…]
```

### IPFS hosting rentals

```bash
# Host a CID or local file through an ipfs offer for N days
aitbc market host --offer-id-or-plugin-id ipfs-ipfs-host --cid-or-file Qm… --days 7 [--no-pin]

# Retrieve hosted content by rental job, access token, or free CID
aitbc market download --rental-id <job-id>
aitbc market download --access-key <key> --access-secret <secret> --output-path /tmp/data.txt
aitbc market download --cid Qm… --wait
```

### Job and order bookkeeping

```bash
# List marketplace jobs (filterable)
aitbc market jobs [--service-type ipfs] [--state active] [--buyer-address 0x…] [--offer-id …] [--limit 100]

# Check an order/job including its on-chain escrow state
aitbc market status --order-id <order-or-job-id>

# Cancel an active marketplace job and request a refund
aitbc market cancel --job-id <job-id> [--reason buyer_requested]
```

### Price discovery

```bash
# Match GPU bids with offers for price discovery
aitbc market match [--output json]
```

`aitbc market providers` exists but is a stub: it prints "GPU provider query via P2P network to be implemented" and suggests `aitbc gpu list-gpus` for local GPUs and `aitbc market list` for published offers.

## Protected GPU Rentals (`aitbc market gpu`)

Fixed-duration GPU rentals priced by an operator-signed energy quote (energy floor). Settlement rail is `native` (on-chain escrow) or `evm` (AIPowerRental contract).

```bash
# Request an operator-signed quote (verified locally before display)
aitbc market gpu quote --gpu-id <gpu-id> --buyer-id <client-id> \
  [--duration-hours 4] [--gpu-count 1] [--max-ait 10] [--settlement native|evm] [--json-output]

# Fund a quoted rental (requires the saved quote JSON and a signing wallet)
aitbc market gpu buy --gpu-id <gpu-id> --buyer-id <client-id> --job-id <job-id-from-quote> \
  --duration-hours 4 --energy-quote quote.json [--wallet <name>] [--yes] [--json-output]

# Inspect / settle / refund a rental
aitbc market gpu status --job-id <job-id>
aitbc market gpu release --job-id <job-id> [--yes]
aitbc market gpu refund --job-id <job-id> [--reason …] [--wallet <name>] [--yes]
```

## On-Chain Escrow (`aitbc market escrow`)

Escrow is created automatically when a paid marketplace job is funded (`market run`, `market host`, `market gpu buy`); these commands inspect or settle it manually.

```bash
# Show on-chain escrow state for a job
aitbc market escrow status --job-id job-123

# Release escrowed funds to the provider after job completion
aitbc market escrow release --job-id job-123

# Refund escrowed funds back to the buyer
aitbc market escrow refund --job-id job-123 --reason "provider_failed"

# Create an escrow manually (signs the escrow lock with a wallet)
aitbc market escrow create --job-id job-123 --buyer 0x… --provider 0x… [--amount 100] [--wallet <name>]
```

Escrow lifecycle:

```
market run / host / gpu buy
      │
      ├─→ marketplace tx + POST /rpc/escrow/create
      │          │
      │          ▼
      │     state: created (funds locked)
      │          │
      ┌─────────┴─────────┐
      ▼                   ▼
market escrow       market escrow
  release             refund
      │                   │
  provider             buyer
  receives             refunded
```

## Ratings

```bash
# Rate a service offer on a 1–5 scale (reviewer defaults to wallet address)
aitbc market rate --service-id offer-1 --rating 5 [--comment 'great service']

# View ratings for an offer
aitbc market ratings --service-id offer-1 [--limit 20] [--offset 0]

# Sync ratings to/from a remote marketplace node (URL via --remote-url or AITBC_MARKETPLACE_URL)
aitbc market sync-ratings --remote-url https://<remote-host>
```

## ETH↔AIT Exchange (`aitbc market exchange`)

Bridge operations for marketplace payments:

```bash
aitbc market exchange price                          # current ETH–AIT rate
aitbc market exchange status                         # bridge service status
aitbc market exchange list-deposits [--status confirmed] [--limit 50]
aitbc market exchange mint-ait --deposit-id dep-123  # mint AIT for a verified ETH deposit
aitbc market exchange deposit-eth --amount 0.1 [--ait-address 0x…] [--bridge-address 0x…] [--gas 30000]
aitbc market exchange withdraw-eth --amount 0.1 --address 0x…   # admin only
```

## Related Command Groups

- `aitbc gpu` — **local** GPU inventory on this node: `discover`, `register`, `update`, `unregister`, `list-gpus`.
- `aitbc gpu-onchain` — on-chain GPU registry records (`query`, `list`, `allocations`).
- `aitbc http call marketplace <path>` — raw marketplace service (port 8102) API for anything the CLI does not wrap.
- `aitbc dispute` — separate top-level group for dispute filing, evidence, arbitration, and payment rulings.

## Not in the CLI

Some capabilities described by older versions of this guide have **no CLI equivalent** today:

- An order-acceptance workflow (`accept`/`reject`/`complete` lifecycle) — providers fulfill jobs through the coordinator/miner pipeline; buyers track them with `aitbc market jobs` and `aitbc market status`.
- Marketplace analytics, personal spending/earnings reports, regional filters, and price-trend reports.
- CLI-managed notification/alert rules, batch offer files, auto-renew/auto-accept automation, and data export/import — use `--output json` and standard tools for export.
- Two-sided (renter→miner and miner→renter) review management — `aitbc market rate` only rates service offers, and there is no review update command.
- The `aitbc marketplace` chain-listings group (`list`/`search`/`buy`/`complete`) — removed from the CLI entirely; the `GlobalChainMarketplace` core module remains in `cli/aitbc_cli/core/marketplace.py` with no command surface.

## Best Practices

### For Providers

1. **Competitive pricing**: check `aitbc market list --sort price` and `aitbc market match` before publishing.
2. **Keep offers accurate**: `aitbc market offer-list` + `offer-disable` to prune stale listings.
3. **Reputation matters**: `aitbc market list --sort reputation` ranks by coordinator trust score — good ratings win jobs.

### For Buyers

1. **Compare before buying**: `aitbc market list --sort reputation` then `aitbc market ratings --service-id <id>`.
2. **Track jobs**: `aitbc market jobs` / `aitbc market status --order-id <id>` / `aitbc market escrow status --job-id <id>`.
3. **Verify escrow settlement**: `ESCROW_RELEASE` transactions settle on-chain; check with `aitbc market escrow status`.

## Command Help

```bash
aitbc market --help
aitbc market escrow --help
aitbc market gpu --help
aitbc market exchange --help
aitbc market run --help
```

---

*This guide covers the real `aitbc market` surface in CLI 0.10.18. If `aitbc market --help` does not list a command, it does not exist.*
