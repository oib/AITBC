# Last Uncovered Options — economics + trade

**Level**: Advanced
**Prerequisites**: Scenario 58 Economics & OpenClaw DAO, Scenario 77 Trade CLI Options
**Estimated Time**: 5 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

breadcrumb: Home > Scenarios > Last Option Coverage

## Scenario Overview

> **Option-coverage scenario (LASTOPTS-FINAL-1, issue #563).** Plays the
> last 6 non-secret uncovered options plus the `unplayable:`-tagged
> `crosschain bridge --wait`. All refusals happen before any record can
> be written (auth layer, dead endpoint, or simulated path). Played on
> node0 (`aitbc 0.25.9`), `logger -t coderA`. Zero records created.

## Steps

### Step 1: `economics model --type` — simulated path

```bash
aitbc economics model --type probe
```

**Expected output (exit 0):** `status | simulated` — no coordinator client
configured, so the model is a local simulation; `--type` is exercised and
nothing is written.

### Step 2: `economics vote --voting-power` — auth refusal

```bash
aitbc economics vote --proposal-id nosuch --vote abstain --voting-power 0
```

**Expected output (exit 2):** `Coordinator API error: POST request failed: 401 Client Error: Unauthorized` — the coordinator's auth layer refuses before the vote record (no vote written).

### Step 3: `trade create --offer-id/--price/--quantity` — API-key refusal

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade create --source-chain a --dest-chain b --sender 0x0 --recipient 0x0 --amount 1 --offer-id nosuch --price 0 --quantity 0
```

**Expected output (exit 2):** `Network error: POST request failed: 401 Client Error: Unauthorized` — the trading service refuses before the trade record (no trade created).

### Step 4: `trade lock-escrow --node-url` — trade-lookup refusal

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade lock-escrow --trade-id nosuch --node-url http://127.0.0.1:9
```

**Expected output (exit 2):** `Network error: GET request failed: 401 Client Error: Unauthorized` — the trade GET refuses before the settlement POST; `--node-url` is named and never contacted.

### Step 5: `crosschain bridge --wait` — unplayable

No play: `unplayable:` per the Phase-0 binding (commit `06a9a86d6`) — a successful `--wait` would block on a real crosschain operation; no refusing argument set exists.

## Option coverage result

| Option | Command | Exit class |
|---|---|---|
| `--type` | `economics model` | ok (0, simulated) |
| `--voting-power` | `economics vote` | expected-refusal (2, 401) |
| `--offer-id/--price/--quantity` | `trade create` | expected-refusal (2, 401) |
| `--node-url` | `trade lock-escrow` | expected-refusal (2, 401) |
| `--wait` | `crosschain bridge` | unplayable: binding |

Census delta: **0 non-secret uncovered remaining** (258 🔒 secret-value
flags stay excluded by design).
