# Marketplace Offers and Price Discovery

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 07 AI Job Submission
**Estimated Time**: 20 minutes
**Last Updated**: 2026-09-15
**Version**: 2.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Marketplace Offers and Price Discovery

---

> **Renamed.** This file was *Marketplace Bidding* and drove the `aitbc marketplace`
> group (`list`/`search`/`buy`/`complete`) against a chain-for-sale marketplace. That
> group was removed from the CLI and never replaced. The live surface is `aitbc
> market`, which sells **compute services**, not chains, and the scenario below has
> been rewritten against it. The filename is unchanged so existing links keep working.

## See Also

- **Previous Scenario**: [AI Job Submission](./07_ai_job_submission.md)
- **Next Scenario**: [GPU Listing](./09_gpu_listing.md)
- **End-to-end paid flow**: [Hub ↔ Customer Node E2E](./34_hub_customer_node_e2e.md)
- **Feature Documentation**: [Marketplace CLI Tools](../apps/marketplace/CLI_TOOLS.md)

---

## Scenario Overview

This scenario covers the buyer's half of the AITBC marketplace: how offers reach the
network, how to discover and rank them by price and reputation, how to cap what you
are willing to pay, and how to settle and rate the result.

### Use Case

A shop miner with a GPU publishes what it can sell — Ollama inference, Whisper
transcription, FFmpeg transcoding, Hermes agent runs, IPFS hosting. A buyer agent has
to decide *which* of those offers to spend on. That decision is the whole scenario:
list, rank, cap, run, rate.

### A note on "bidding"

The scenario title promised a competitive auction. **The live system does not have
one.** Nothing in the codebase emits a buyer-side bid transaction: the string `bid`
survives only as an accepted `action` value in `aitbc market list`'s blockchain
fallback filter, and no command produces such a payload. There is no bid book, no
clearing round, and no `aitbc market bid`.

What exists instead is one-sided price discovery plus a buyer price cap:

- **Providers post asks.** `aitbc market offer` writes a `software_offer` transaction
  with a price and a unit.
- **Buyers rank the asks.** `aitbc market list --sort` and `aitbc market match` order
  them by reputation, price, or availability.
- **Buyers cap what they will pay.** `aitbc market gpu quote --max-ait` is the only
  buyer-supplied number that can refuse a price — it bounds an operator-signed energy
  quote for a fixed-duration GPU rental.

Treat this document as describing that mechanism. If a real auction lands later, it
belongs in a new scenario rather than in this one's history.

### What You'll Learn

- How offers get published and what a published offer carries
- How to discover offers and rank them by reputation or price
- How to read `aitbc market match` price discovery
- How to cap your spend on a GPU rental with a signed quote
- How to pay for a service, settle escrow, and rate the provider

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — purchases settle as on-chain transactions
- Scenario 07 (AI Job Submission) — coordinator-mediated job flow

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A funded wallet (marketplace prices are quoted in **AIT**, not ETH)
- Network reach to the hub, which fronts the marketplace service

### Setup Required

- A configured `hub_discovery_url`; `aitbc market list` queries `https://<hub>/v1/marketplace/offer`
  and falls back to the blockchain RPC if that service is unreachable
- A wallet selected via the group-level options: `aitbc market --wallet <name> --password-file <path> <command>`

---

## Step-by-Step Workflow

### Step 1: See what is on offer

```bash
aitbc market list
```

**Expected output** (one entry per active offer; addresses and endpoints elided here):

```json
[
  {
    "Offer ID": "sw_offer_20260914195725_84ec042f",
    "Plugin ID": "ollama-llama3.2-3b",
    "Service Type": "ollama",
    "Model": "llama3.2:3b",
    "Price": "0.00100000 per_1k_tokens",
    "Provider": "<provider-address>",
    "Node ID": "<provider-node-id>",
    "GPU": "NVIDIA GeForce RTX 4060 Ti (0)",
    "Memory (GB)": 15,
    "Disk Quota (MB)": "N/A",
    "Endpoint": "<provider-endpoint>",
    "Status": "active",
    "Rating": "5.0 (2 reviews)"
  }
]
```

> **`--format table` does not produce a table.** Every `--format` / `--output` choice
> renders structured data as JSON: `output()` in `cli/aitbc_cli/utils/output.py` has a
> single branch for non-string values, marked `# Table format — just JSON for now`.
> Only `json` is honest about what you get; `table`, `yaml`, and `csv` are accepted and
> ignored. Parse the JSON rather than expecting columns.

> **`Circuit breaker opened after 5 failures`** may precede the output. That is the
> reputation enrichment giving up on the coordinator, not a failure of the listing —
> affected offers simply fall back to their average rating.

### Step 2: Rank the offers

Sorting is the buyer's substitute for an auction. `--sort` is applied server-side
against live reputation data before the list is printed.

```bash
# Cheapest first
aitbc market list --sort price

# Best-rated first, price breaking ties — the default ordering
aitbc market list --sort reputation

# Active offers with spare capacity first
aitbc market list --sort availability

# Narrow to one service type or one provider
aitbc market list --service-type whisper
aitbc market list --provider <provider-address>

# Only your own published offers
aitbc market list --mine
```

The `Rating` field shows `N.NN trust` when the coordinator returned a trust score, and
falls back to `N.N (K reviews)` from the marketplace service otherwise.

### Step 3: Read the price-discovery view

`aitbc market match` joins GPU-backed offers to the hardware behind them, which is the
view to use when the GPU matters as much as the price.

```bash
aitbc market match
```

**Expected output:**

```
GPU Market Matches
+-----------+----------------+------------------------------------+---------------+-------------------------------+
| Service   | Model          | GPU                                | Memory (GB)   | Price                         |
+===========+================+====================================+===============+===============================+
| ffmpeg    | h264-transcode | NVIDIA GeForce RTX 4060 Ti [GPU 0] | 15            | 0.005 AIT/per_processing_hour |
| whisper   | base           | NVIDIA GeForce RTX 4060 Ti [GPU 0] | 15            | 0.02 AIT/per_audio_min        |
| hermes    | default        | NVIDIA GeForce RTX 4060 Ti [GPU 0] | 15            | 0.1 AIT/per_minute            |
| ollama    | llama3.2:3b    | NVIDIA GeForce RTX 4060 Ti [GPU 0] | 15            | 0.001 AIT/per_1k_tokens       |
| ipfs      | ipfs-host      | N/A (IPFS) [GPU N/A]               | N/A           | 0.01 AIT/per_day              |
+-----------+----------------+------------------------------------+---------------+-------------------------------+
Total: 5 offer(s)
```

> Until 2026-09-15 this view also listed settled jobs. `GPU_MARKETPLACE` carries
> both listings and settlements, and the endpoint selected on the transaction type
> alone, so those rows came back with an empty service and `0 AIT` and the footer
> counted them — `Total: 8 offer(s)` where five were purchasable. Both the node and
> the CLI now filter on the payload action, so a node still running the old code
> does not put phantom rows back in the total.

### Step 3b: See who is selling, not what is for sale

`aitbc market match` and `aitbc market list` are per-offer views. When the question
is which provider to buy from, `aitbc market providers` collapses the same
population to one row per seller.

```bash
aitbc market providers
```

**Expected output:**

```
Marketplace Providers
=====================
+---------------------+---------------------+---------------------------------------+----------+----------+-----------------+
| Provider            | Node ID             | Services                              |   Offers |   Active | Rating          |
+=====================+=====================+=======================================+==========+==========+=================+
| <provider-address>  | <provider-node-id>  | ffmpeg, hermes, ipfs, ollama, whisper |        5 |        5 | 5.0 (4 reviews) |
| <miner-id>          | <miner-id>          | gpu_marketplace                       |        1 |        1 | unrated         |
| <miner-id>          | <miner-id>          | gpu_marketplace                       |        5 |        5 | unrated         |
+---------------------+---------------------+---------------------------------------+----------+----------+-----------------+
Total: 3 provider(s), 11 offer(s)
```

The `GPU` and `Endpoint` columns are omitted above for width; the command prints them.
`Rating` prefers the coordinator trust score and falls back to the marketplace star
average weighted by review count, so one 5-star listing cannot outvote a well-reviewed
one. `Active` counts only offers whose status is live — a provider with `5` offers and
`1` active has disabled the rest.

This command was a stub until 2026-09-15: it printed
`GPU provider query via P2P network to be implemented` and sent you to
`aitbc gpu list`, which lists locally registered GPUs rather than marketplace sellers.

### Step 4: Cap your spend on a GPU rental

For fixed-duration GPU rentals, `--max-ait` is the buyer's price limit: the operator
signs a quote only if the energy-floor price fits under your cap.

```bash
aitbc market gpu quote \
  --gpu-id <gpu-registry-id> \
  --buyer-id <buyer-client-id> \
  --duration-hours 2 \
  --gpu-count 1 \
  --max-ait 5.0 \
  --settlement native
```

The quote is signed by the operator and carries an energy floor, so a provider cannot
quote below cost and you cannot be charged above your cap. Redeem it with
`aitbc market gpu buy`, then `status`, `release`, or `refund`.

### Step 5: Pay for a service offer

Per-use software offers are paid with metered escrow. Each service has a typed command
that knows its own parameters:

```bash
# Inference
aitbc market run --offer-id-or-plugin-id <offer-id> --prompt 'Summarise this paragraph'

# Transcription
aitbc market transcribe --offer-id-or-plugin-id <offer-id> --audio-file interview.mp3

# Transcoding
aitbc market process --offer-id-or-plugin-id <offer-id> --input clip.mov --codec h264

# One-shot agent run
aitbc market hermes --offer-id-or-plugin-id <offer-id> --prompt 'check the chain height' --max-time 60
```

Escrow locks at submission and releases on completion. The full paid round trip —
escrow lock, completion, explicit acceptance, on-chain settlement — is walked through
in [scenario 34](./34_hub_customer_node_e2e.md); it is not repeated here because it
moves real funds.

Add `--track` to create a coordinator job record, then follow it with
`aitbc market jobs` and `aitbc market cancel` if you need a refund.

### Step 6: Rate what you bought

Ratings are the only input to the reputation half of `--sort`, so this step is what
makes step 2 work for the next buyer.

```bash
aitbc market rate --service-id <offer-id> --rating 5 --comment 'fast, matched the quoted price'
aitbc market ratings --service-id <offer-id> --limit 20
```

---

## Code Example: choose an offer by price and reputation

```python
import json
import subprocess


def market(*args: str) -> list[dict]:
    """Run an aitbc market subcommand and parse its JSON output."""
    proc = subprocess.run(
        ["aitbc", "market", *args, "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    # The reputation enricher may print a circuit-breaker warning before the payload,
    # so start at the first '[' rather than assuming the stream is pure JSON.
    start = proc.stdout.index("[")
    return json.loads(proc.stdout[start:])


def cheapest_acceptable(service_type: str, max_price: float, min_rating: float = 4.0) -> dict | None:
    """Pick the cheapest active offer that clears a reputation floor.

    This is the whole of buyer-side price discovery in the current system: there is
    no bid to place, so choosing well is a client-side filter over the ask list.
    """
    offers = market("list", "--service-type", service_type, "--sort", "price")

    def price_of(offer: dict) -> float:
        return float(offer["Price"].split()[0])

    def rating_of(offer: dict) -> float:
        # "4.8 trust" or "5.0 (2 reviews)"; both lead with the number.
        return float(offer["Rating"].split()[0])

    for offer in offers:
        if offer.get("Status") != "active":
            continue
        if price_of(offer) > max_price:
            break  # sorted ascending, so nothing further can fit
        if rating_of(offer) >= min_rating:
            return offer
    return None


chosen = cheapest_acceptable("whisper", max_price=0.05)
if chosen:
    print(f"Using {chosen['Offer ID']} at {chosen['Price']}")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Explain why the marketplace has asks and caps but no bids
- Discover active offers and rank them by price, reputation, or availability
- Read `aitbc market match` and tell purchasable rows from empty ones
- Bound a GPU rental with `--max-ait` and an operator-signed quote
- Pay for a service offer through metered escrow and rate the provider afterwards

---

## Validation

```bash
# Offers are reachable and at least one is active
aitbc market list --status active

# Price ordering is applied
aitbc market list --sort price

# GPU-backed offers resolve to real hardware
aitbc market match

# Your rating landed
aitbc market ratings --service-id <offer-id>
```

---

## Known Gaps

- **No buyer-side bid.** `bid` is an accepted action value in `market list`'s
  blockchain fallback and nothing writes it. Price is set entirely by providers.
- **`market list` truncates before it serializes.** The provider address and endpoint
  are shortened to `0x1234...`-style stubs for the table, and `--format json|csv|yaml`
  emit those same truncated values, so the machine-readable output of that one command
  is not round-trippable. `match` and `providers` are unaffected.

Closed 2026-09-15: `--format table|yaml|csv` rendered JSON for every command in the
CLI; `market providers` was a stub; `match` counted rows that carried no offer.

---

## Related Resources

- Source: `cli/aitbc_cli/commands/market/` (`offers.py`, `gpu.py`, `escrow.py`, `jobs.py`, `ratings.py`)
- Removed: `cli/aitbc_cli/commands/marketplace_cmd.py` and the `aitbc marketplace` group
- Vestigial: `cli/aitbc_cli/core/marketplace.py` (`GlobalChainMarketplace`, `ChainType`) — still present, wired to nothing
- [Whisper offer walkthrough](../apps/marketplace/HOWTO_WHISPER_OFFER.md)
- [Next Scenario: GPU Listing](./09_gpu_listing.md)

---

*Last updated: 2026-09-15*
*Version: 2.1*
