# Trade CLI Options

**Level**: Advanced
**Prerequisites**: Scenario 62 Interchain Trade
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Trade CLI Options

---

## Scenario Overview

> **Option-coverage scenario (TRADE-OPTS-1).** This play walks the
> previously unexercised `aitbc trade` options — read-only query flags
> plus the mutating/settlement commands exercised only as far as they are
> free: a refused API key (`401`), an unknown trade id (`404`), and an
> unknown chain that reports `not_registered`. Nothing is signed, nothing
> is spent, and no trade record is created.
>
> Played on node0 (checkout `59fcb78e1`) against the live trading service
> on `localhost:8104`. The settlement commands
> (`lock-escrow`/`settle`/`refund`/`settlement-status`) all look the trade
> up on the trading service **before** any settlement call, so a
> nonexistent `--trade-id` refuses for free.

### What You'll Learn

- Which `aitbc trade` queries are free read-only calls
- How a bogus `TRADING_API_KEY` stops every mutating POST at a `401`
- How the settlement family refuses on an unknown `--trade-id` before
  touching escrow
- Two live drifts: array-shaped list responses abort with exit 5, and a
  per-command `--format json` is silently ignored (only the top-level
  `aitbc --output json` switch takes effect)

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A trading service reachable (default `http://localhost:8104`) with
  `TRADING_API_KEY` configured for the read-only queries
- A deliberately wrong key (`nosuch-tradeopts1` below) for the mutating
  commands — never a real key

---

## Steps

### Step 1: Read-only queries

`health` answers for any chain id — an unknown one is a clean
`not_registered`, not an error:

```bash
aitbc trade health --chain-id nosuch-chain --format json
```

**Expected output (exit 0):**

```
+----------+----------------+
| Field    | Value          |
+==========+================+
| chain_id | nosuch-chain   |
+----------+----------------+
| status   | not_registered |
+----------+----------------+
```

> **Drift:** the `--format json` flag is parsed but silently ignored —
> the global `ctx.obj["output_format"]` default (`table`) wins inside
> every trade command. `aitbc --output json trade health --chain-id
> nosuch-chain` does print
> `{"chain_id": "nosuch-chain", "status": "not_registered"}`. Recorded
> under TRADE-OPTS-1.

`discover` is a POST but semantically a filtered search — it runs live
against the trading service:

```bash
aitbc trade discover --region eu-west --gpu-model rtx4090 --format json
```

**Expected output (exit 0):**

```json
{
  "offers": [],
  "total_count": 0,
  "chains_searched": [],
  "stale_count": 0,
  "sync_triggered": false
}
```

(Empty result on node0; any offers would be listed instead.)

A `get`/`status`/`match` on a trade id that does not exist refuses with
`404` before anything else happens:

```bash
aitbc trade get tradeopts1-probe --format json
```

**Expected output:** `Network error: GET request failed: 404 Client
Error: Not Found for url: http://localhost:8104/v1/trading/inter-chain/tradeopts1-probe`
(exit 2 — nothing written).

```bash
aitbc trade status --trade-id tradeopts1-probe --format json
```

**Expected output:** same 404 shape on
`/v1/trading/inter-chain/tradeopts1-probe/status` (exit 2).

### Step 2: List endpoints — array-shape drift (exit 5)

Several `trade` list endpoints return a bare JSON array, which the CLI's
object-expecting response check refuses. The flags are still exercised —
the refusal is the endpoint/CLI drift, not a usage error:

```bash
aitbc trade chains --format json
```

**Expected output (exit 5):**
`Error listing chains: http://localhost:8104/v1/trading/chains returned a JSON array, not an object. Use get_json() and handle both shapes if this endpoint can return either.`

```bash
aitbc trade list --dest-chain nosuch-dest --limit 5 --format json
```

**Expected output (exit 5):** same drift text on `/v1/trading/inter-chain`.

```bash
aitbc trade history --dest-chain nosuch-dest --format json
```

**Expected output (exit 5):** same drift text on
`/v1/trading/inter-chain/history`.

```bash
aitbc trade search --service-type gpu_market --min-price 0.1 --max-price 5 --format json
```

**Expected output (exit 5):** same drift text on `/v1/trading/offers/search`.

```bash
aitbc trade sync-status --format json
```

**Expected output (exit 5):** same drift text on
`/v1/trading/offers/sync-status`.

```bash
aitbc trade subscription-status --format json
```

**Expected output (exit 5):** same drift text on
`/v1/trading/offers/subscription-status`.

### Step 3: Mutating commands — refused for free on a bad key (exit 2)

`create`, `register-chain`, `match-all`, and `sync` all POST to the
trading service. With a deliberately wrong `TRADING_API_KEY` the service
refuses `401` before any effect — no record is created, no chain is
registered, nothing is matched or synced:

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade create --source-chain ait-mainnet --dest-chain ait-side --sender 0x0000000000000000000000000000000000000001 --recipient 0x0000000000000000000000000000000000000002 --amount 1 --format json
```

**Expected output (exit 2):**
`Network error: POST request failed: 401 Client Error: Unauthorized for url: http://localhost:8104/v1/trading/inter-chain/create`

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade register-chain --chain-id nosuch-chain --endpoint http://localhost:1 --format json
```

**Expected output (exit 2):** 401 on `/v1/trading/chains/register`.

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade match-all --format json
```

**Expected output (exit 2):** 401 on `/v1/trading/inter-chain/match-all`
— do **not** run this with a real key, `match-all` acts on every open
trade.

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade sync --format json
```

**Expected output (exit 2):** 401 on `/v1/trading/offers/sync`.

`match` needs only a nonexistent trade id to refuse (real key in use):

```bash
aitbc trade match tradeopts1-probe --format json
```

**Expected output (exit 2):** 404 on
`/v1/trading/inter-chain/tradeopts1-probe/match` — refused before any
matching occurs.

### Step 4: Settlement family — refuses on the trade lookup (exit 2)

`lock-escrow`, `settle`, `refund`, and `settlement-status` each fetch the
trade from the trading service first, so a nonexistent `--trade-id`
refuses with `404` **before** any escrow or settlement RPC is attempted —
`--node-url`, `--api-key`, `--timeout`, and `--format` are exercised for
free:

```bash
aitbc trade lock-escrow --trade-id tradeopts1-probe --api-key nosuch-tradeopts1 --timeout 60 --format json
```

**Expected output (exit 2):** 404 on
`/v1/trading/inter-chain/tradeopts1-probe` — no escrow created.

```bash
aitbc trade settle --trade-id tradeopts1-probe --secret deadbeef --node-url http://localhost:8202 --api-key nosuch-tradeopts1 --format json  # check-ports: ignore — node-url flag default host:port, never reached (trade lookup 404s first)
```

**Expected output (exit 2):** 404 on the trade lookup — no settlement
attempted. (`--secret` takes a throwaway value; never a real HTLC secret.)

```bash
aitbc trade refund --trade-id tradeopts1-probe --node-url http://localhost:8202 --api-key nosuch-tradeopts1 --format json
```

**Expected output (exit 2):** 404 on the trade lookup — no refund
attempted.

```bash
aitbc trade settlement-status --trade-id tradeopts1-probe --node-url http://localhost:8202 --api-key nosuch-tradeopts1 --format json
```

**Expected output (exit 2):** 404 on the trade lookup.

### Step 5: Watch filters — refused for free on a bad key (exit 5)

`watch` opens a subscription stream. With a real key it streams events
until interrupted (verified: silent stream, `timeout` kill, exit 124).
With a deliberately wrong key the offer lease is refused up front:

```bash
TRADING_API_KEY=nosuch-tradeopts1 aitbc trade watch --min-price 0.1 --max-price 5 --region eu-west --gpu-model rtx4090 --format json
```

**Expected output (exit 5):**

```
Offer lease request rejected with HTTP 401 for ait-hub — check the trading API key
Error watching offers: Client error '401 Unauthorized' for url 'http://localhost:8104/v1/trading/offers/subscribe'
```

---

## Exit-class table

| Class | Plays |
|---|---|
| ok (exit 0) | `health --chain-id` (not_registered), `discover --region/--gpu-model` |
| expected-refusal 401 (exit 2) | `create`, `register-chain`, `match-all`, `sync` (bad `TRADING_API_KEY`) |
| expected-refusal 404 (exit 2) | `get`, `status`, `match`, `lock-escrow`, `settle`, `refund`, `settlement-status` (unknown trade id) |
| drift: array-shaped response (exit 5) | `chains`, `list`, `history`, `search`, `sync-status`, `subscription-status` |
| drift: offer-lease refusal (exit 5) | `watch` with bad key; real key streams (exit 124 under `timeout`) |

## Coverage notes

All 40 previously unexercised `trade` options pass through a command line
above. Two defects recorded during the play, to be registered as their
own rows (not folded into this one):

1. **Array-drift:** six `trade` endpoints return bare JSON arrays and the
   CLI aborts with the same `get_json()` message class fixed for
   `market jobs` under Refs #490 — the `trade` group needs the same
   treatment.
2. **`--format` ignored:** per-command `--format json` is overridden by
   `ctx.obj["output_format"]` (always populated, default `table`); only
   `aitbc --output json` works. Verified on `trade health`.
