# Exchange CLI Options

**Level**: Advanced
**Prerequisites**: Scenario 62 Interchain Trade
**Estimated Time**: 20 minutes
**Last Updated**: 2026-10-26
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Exchange CLI Options

---

## Scenario Overview

> **Option-coverage scenario (EXCHANGE-OPTS-1).** This play walks the
> previously unexercised `aitbc exchange` + `aitbc exchange-island`
> options — the local-file integration commands, the hub-exchange
> signed-envelope family, the prepaid-ETH lane, the read-only verifier,
> and the exchange-island buy/sell wallet flag.
>
> Played on node0 against the live hub exchange at
> `https://hub.aitbc.bubuit.net` (the exchange service itself is
> loopback-bound on hub; nginx serves the public `/api/exchange/*`
> reads). Every signed or money-moving command stops at a free refusal —
> a nonexistent `--wallet nosuch-exchopts1`, a positivity guard, a
> per-call cap, or a missing island-credentials file. Nothing is signed
> by a real wallet, nothing is spent, no exchange order or chain
> transaction is created.
>
> The `aitbc exchange` integration commands (`register`, `create-pair`,
> `start-trading`, `add-liquidity`, `monitor`) read and write only the
> local file `~/.aitbc/exchanges.json` — they touch neither the chain
> nor any service. They are played under a throwaway
> `HOME=/tmp/exchopts1-home` so the only "record" created is a scratch
> file that is deleted at the end of the step.

### What You'll Learn

- Which `aitbc exchange` commands are local-file only (no network)
- How the signed hub-exchange family refuses on an unknown wallet
  before any signature or HTTP POST
- How `prepay deposit`'s `--max-eth` cap refuses before the wallet is
  even resolved
- That `order book` requires credentials on the hub (401) while
  `node list`, `order my`, and `sell_admin status` are public reads
- A verifier drift: `exchange verify` crashes with an unhandled
  `sqlite3.OperationalError` traceback when `--rpc-url` is passed on a
  DB without the exchange tables

---

## Prerequisites

- AITBC CLI (`aitbc`) installed and on `$PATH`
- For the live reads: the hub exchange reachable at
  `https://hub.aitbc.bubuit.net`
- No wallet named `nosuch-exchopts1` (the refusing argument)

---

## Steps

### Step 1: Local-file exchange integrations (scratch HOME)

`register`, `create-pair`, `start-trading`, `add-liquidity` and
`monitor` operate solely on `~/.aitbc/exchanges.json`. Point `HOME` at
a scratch directory so the file written is throwaway:

```bash
export HOME=/tmp/exchopts1-home && mkdir -p $HOME
aitbc exchange register --name fixturex --api-key nosuch-key --sandbox --description "EXCHANGE-OPTS-1 scratch fixture"
```

**Expected output (exit 0):**

```
Exchange 'fixturex' registered successfully
+------------+----------------------------------+
| Field      | Value                            |
+============+==================================+
| exchange   | fixturex                         |
+------------+----------------------------------+
| status     | registered                       |
+------------+----------------------------------+
| sandbox    | True                             |
+------------+----------------------------------+
| created_at | <timestamp>                      |
+------------+----------------------------------+
```

```bash
aitbc exchange create-pair --base-asset AIT --quote-asset ETH --exchange fixturex --min-order-size 0.5 --price-precision 3 --quantity-precision 2
```

**Expected output (exit 0):** `Trading pair 'AIT/ETH' created on
fixturex` plus a table echoing `min_order_size 0.5`,
`price_precision 3`, `quantity_precision 2`.

```bash
aitbc exchange start-trading --pair AIT/ETH --price 0.0001 --base-liquidity 5000 --quote-liquidity 0.5 --exchange fixturex
```

**Expected output (exit 0):** `Trading started for pair 'AIT/ETH' on
fixturex` plus `status trading_active`, `initial_price 0.0001`.

```bash
aitbc exchange add-liquidity --pair AIT/ETH --amount 100 --side buy --exchange fixturex
```

**Expected output (exit 0):** `Added 100 liquidity to AIT/ETH on
fixturex (buy side)` — the buy side adds to `quote_liquidity`
(`0.5` → `100.5`).

```bash
aitbc exchange monitor --real-time --interval 30
```

**Expected output (exit 0):** a JSON document with
`"monitoring_active": true`, `"real_time": true`, `"interval": 30`
and the pair listed `status: active`, followed by the warning line
`Real-time monitoring enabled. Updates every 30 seconds.` (the flag
prints the warning; there is no update loop).

```bash
aitbc exchange monitor --pair AIT/ETH --exchange fixturex --interval 15
```

**Expected output (exit 0):** same JSON shape, `"real_time": false`,
`"interval": 15` — `--exchange` filters to the named integration.

Clean up the scratch home afterwards:

```bash
rm -rf /tmp/exchopts1-home
```

### Step 2: Hub-exchange reads (live, public)

The hub's nginx serves the exchange's public GETs. `node list` is the
participants board — every island node is `seeded`, none registered:

```bash
aitbc exchange node list --exchange-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 0):** JSON `{"nodes": [...]}` — seven seeded
rows (`bridge`, `bridge-old`, `hub`, `hub1`, `node0`, `node1`,
`node2`), all `"status": "seeded"`, `"registered_at": null`.

`order my` needs no wallet when a plain `--address` is passed — an
address with no registry row reads back unregistered:

```bash
aitbc exchange order my --address 0x0000000000000000000000000000000000000001 --exchange-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 0):**

```
My exchange orders
==================
{
  "address": "0x0000000000000000000000000000000000000001",
  "label": null,
  "registered": false,
  "next_nonce": 0,
  "orders": []
}
```

`order book` is **not** a public route on the hub — nginx/upstream
demands credentials, so the flag is exercised as a refusal:

```bash
aitbc exchange order book --exchange-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 2):**
`Cannot reach exchange: Missing authentication credentials`

`sell_admin status` reads the sell-lane config on the hub's bridge
mount — public, live, and free:

```bash
aitbc exchange sell_admin status --hub-url https://hub.aitbc.bubuit.net
```

**Expected output (exit 0):** JSON with `"enabled": true`, `chain_id
bc-2`, the escrow/treasury addresses, and the non-secret limits
(`max_eth_per_tx`, `sell_daily_cap` fields, `escrow_wallet_configured`).
A dead URL exercises the flag's error path instead:

```bash
aitbc exchange sell_admin status --hub-url http://127.0.0.1:9
```

**Expected output (exit 1):** `Failed to read sell config status: GET
request failed: … Connection refused`.

### Step 3: Signed hub-exchange commands (free refusals)

Every command in this family resolves the signer wallet **before** it
signs or POSTs, so a nonexistent wallet name is a free refusal that
never reaches the exchange. node0 also has no file wallets, so the
abort is deterministic.

`order place` checks positivity first — an `--amount 0` stops even
earlier:

```bash
aitbc exchange order place --side BUY --amount 0 --price 0.0001 --wallet nosuch-exchopts1
```

**Expected output (exit 4):** `amount and price must be positive`

```bash
aitbc exchange order place --side BUY --amount 1 --price 0.0001 --expires-in 720 --chain-id nosuch-chain --exchange-url http://127.0.0.1:9 --wallet nosuch-exchopts1
```

**Expected output (exit 4):**

```
Failed to get wallet info: GET request failed: 404 Client Error: Not Found for url: http://localhost:8108/v1/wallets/nosuch-exchopts1
Wallet 'nosuch-exchopts1' not found as a file wallet.
  searched: /root/.aitbc/wallets, /var/lib/aitbc/wallets
  pass --wallet-path <file> to point at it directly
```

The same wallet gate covers `order cancel`, `node register`, and
`node set-payout` — the envelope is never built, so `--expires-in`,
`--chain-id`, `--label`, and the bogus `--exchange-url` are parsed but
no signature or request is produced:

```bash
aitbc exchange order cancel 1 --expires-in 60 --wallet nosuch-exchopts1 --chain-id nosuch-chain --exchange-url http://127.0.0.1:9
```

**Expected output (exit 4):** the same wallet-not-found abort.

```bash
aitbc exchange node register --wallet nosuch-exchopts1 --label nosuch-label --chain-id nosuch-chain --exchange-url http://127.0.0.1:9
```

**Expected output (exit 4):** the same wallet-not-found abort.

```bash
aitbc exchange node set-payout --eth-address 0x0000000000000000000000000000000000000001 --wallet nosuch-exchopts1 --chain-id nosuch-chain --exchange-url http://127.0.0.1:9
```

**Expected output (exit 4):** the same wallet-not-found abort (the
`--eth-address` normalises to EIP-55 before the wallet is touched, so
a malformed address refuses even earlier with `Invalid --eth-address`).

`order fund` resolves the wallet address without key material (the
`--print` path never signs) — an unknown name still refuses:

```bash
aitbc exchange order fund 999999 --fee 0.01 --print --wallet nosuch-exchopts1 --rpc-url http://127.0.0.1:9 --exchange-url http://127.0.0.1:9
```

**Expected output (exit 4):**

```
Failed to get wallet info: GET request failed: 404 Client Error: Not Found for url: http://localhost:8108/v1/wallets/nosuch-exchopts1
Wallet 'nosuch-exchopts1' not found
```

### Step 4: Prepaid-ETH lane (free refusals)

`prepay deposit` enforces its per-call cap before the wallet is
resolved — `--amount-eth` above `--max-eth` is the cheapest refusal:

```bash
aitbc exchange prepay deposit --amount-eth 0.05 --max-eth 0.01 --wallet nosuch-exchopts1 --exchange-url http://127.0.0.1:9 --eth-rpc-url http://127.0.0.1:9
```

**Expected output (exit 1):** `--amount-eth 0.05 exceeds the per-call
cap 0.01 ETH — pass --max-eth to raise it`

Inside the cap, the wallet gate fires next:

```bash
aitbc exchange prepay deposit --amount-eth 0.005 --max-eth 0.01 --wallet nosuch-exchopts1 --exchange-url http://127.0.0.1:9 --eth-rpc-url http://127.0.0.1:9
```

**Expected output (exit 4):**

```
Failed to get wallet info: GET request failed: 404 Client Error: Not Found for url: http://localhost:8108/v1/wallets/nosuch-exchopts1
Wallet 'nosuch-exchopts1' not found
```

Default mode is `--print` (unsigned preview) — even with a real wallet
nothing broadcasts without `--send`; the play stops at the wallet gate
because a successful preview would still read the participants board
and resolve the deposit address.

### Step 5: Exchange verifier (read-only, plus a drift)

`exchange verify` runs `scripts/ops/exchange_verify.py` read-only
(SQLite `mode=ro`). Its `--db`/`--bridge-db` path guard demands an
existing regular file under `/var/lib/aitbc/`:

```bash
aitbc exchange verify --db /tmp/nosuch.db
```

**Expected output (exit 1):**
`Error: --db: cannot read /tmp/nosuch.db: [Errno 2] No such file or directory: '/tmp/nosuch.db'`

node0 carries no exchange DB; pointing `--db` at the node's real
`bridge_deposits.db` exercises the verifier on a file that opens but
lacks the exchange schema — reported cleanly in `--json`:

```bash
aitbc exchange verify --db /var/lib/aitbc/data/bridge_deposits.db --json
```

**Expected output (exit 1):**

```json
{
  "ok": false,
  "fail": 1,
  "warn": 0,
  "findings": [
    {
      "severity": "FAIL",
      "scope": "db",
      "message": "phase-3 columns absent — is this a pre-settlement exchange DB? (no such table: orders)"
    }
  ]
}
```

The text renderer reports the same finding:

```bash
aitbc exchange verify --db /var/lib/aitbc/data/bridge_deposits.db --settlement
```

**Expected output (exit 1):**

```
FAIL db: phase-3 columns absent — is this a pre-settlement exchange DB? (no such table: orders)
FAIL — 1 failures, 0 warnings
```

> **Drift (flagged for registration):** when `--rpc-url` is passed the
> script skips `--no-chain` and enters the eth-chain leg, which
> dereferences the `trades` table unguarded — on a DB without the
> exchange schema it crashes with an unhandled
> `sqlite3.OperationalError` traceback instead of reporting a FAIL row
> like the DB-internal group does:

```bash
aitbc exchange verify --db /var/lib/aitbc/data/bridge_deposits.db --bridge-db /var/lib/aitbc/data/bridge_deposits.db --rpc-url http://127.0.0.1:9 --ait-rpc http://127.0.0.1:9 --escrow-address 0x40c7181b639A2642294A802b1CD60C7a0d531a07 --bridge-address 0x0000000000000000000000000000000000000001 --settlement --json
```

**Expected output (exit 1):** a Python traceback ending
`sqlite3.OperationalError: no such table: trades` (drift — every flag
in the argv is still exercised end-to-end into the script).

### Step 6: exchange-island buy/sell (free refusals)

The island exchange commands need island credentials before the wallet
is touched — node0 has none
(`/var/lib/aitbc/island_credentials.json` absent), so `--wallet` is
exercised as a parse-time flag inside a refusal that never signs. A
non-positive amount refuses even earlier:

```bash
aitbc exchange-island buy --ait-amount 0 --quote-currency ETH --wallet nosuch-exchopts1
```

**Expected output (exit 4):**

```
AIT amount must be greater than 0
Error creating buy order: AIT amount must be greater than 0
```

```bash
aitbc exchange-island buy --ait-amount 1 --quote-currency ETH --wallet nosuch-exchopts1
```

**Expected output (exit 1):**

```
Island credentials not found: Island credentials not found at /var/lib/aitbc/island_credentials.json. Run 'aitbc node island join' to join an island first.
Run 'aitbc node island join' to join an island first
Error creating buy order: Run 'aitbc node island join' to join an island first
```

```bash
aitbc exchange-island sell --ait-amount 1 --quote-currency ETH --wallet nosuch-exchopts1
```

**Expected output (exit 1):** the same island-credentials refusal with
`Error creating sell order:` as the last line.

---

## Option coverage result

49 previously-unexercised non-secret options exercised across the two
census groups (all outputs verified live on node0, `logger -t coderA`):

| Option | Command | Play | Exit class |
|---|---|---|---|
| `--exchange` | `exchange add-liquidity` | scratch-HOME live | ok (0) |
| `--min-order-size` | `exchange create-pair` | scratch-HOME live | ok (0) |
| `--price-precision` | `exchange create-pair` | scratch-HOME live | ok (0) |
| `--quantity-precision` | `exchange create-pair` | scratch-HOME live | ok (0) |
| `--real-time` | `exchange monitor` | scratch-HOME live | ok (0) |
| `--interval` | `exchange monitor` | scratch-HOME live | ok (0) |
| `--exchange-url` | `exchange node list` | live hub read | ok (0) |
| `--label` | `exchange node register` | wallet-gate refusal | expected-refusal (4) |
| `--chain-id` | `exchange node register` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange node register` | wallet-gate refusal | expected-refusal (4) |
| `--wallet` | `exchange node set-payout` | wallet-gate refusal | expected-refusal (4) |
| `--chain-id` | `exchange node set-payout` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange node set-payout` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange order book` | live 401 refusal | expected-refusal (2) |
| `--expires-in` | `exchange order cancel` | wallet-gate refusal | expected-refusal (4) |
| `--wallet` | `exchange order cancel` | wallet-gate refusal | expected-refusal (4) |
| `--chain-id` | `exchange order cancel` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange order cancel` | wallet-gate refusal | expected-refusal (4) |
| `--fee` | `exchange order fund` | wallet-gate refusal | expected-refusal (4) |
| `--print` | `exchange order fund` | wallet-gate refusal | expected-refusal (4) |
| `--wallet` | `exchange order fund` | wallet-gate refusal | expected-refusal (4) |
| `--rpc-url` | `exchange order fund` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange order fund` | wallet-gate refusal | expected-refusal (4) |
| `--address` | `exchange order my` | live hub read | ok (0) |
| `--exchange-url` | `exchange order my` | live hub read | ok (0) |
| `--expires-in` | `exchange order place` | wallet-gate refusal | expected-refusal (4) |
| `--chain-id` | `exchange order place` | wallet-gate refusal | expected-refusal (4) |
| `--exchange-url` | `exchange order place` | wallet-gate refusal | expected-refusal (4) |
| `--wallet` | `exchange prepay deposit` | wallet-gate refusal | expected-refusal (4) |
| `--max-eth` | `exchange prepay deposit` | cap refusal | expected-refusal (1) |
| `--exchange-url` | `exchange prepay deposit` | cap/wallet refusal | expected-refusal (1/4) |
| `--eth-rpc-url` | `exchange prepay deposit` | cap/wallet refusal | expected-refusal (1/4) |
| `--sandbox` | `exchange register` | scratch-HOME live | ok (0) |
| `--description` | `exchange register` | scratch-HOME live | ok (0) |
| `--hub-url` | `exchange sell_admin status` | live hub read + conn-refused | ok (0) / expected-refusal (1) |
| `--price` | `exchange start-trading` | scratch-HOME live | ok (0) |
| `--base-liquidity` | `exchange start-trading` | scratch-HOME live | ok (0) |
| `--quote-liquidity` | `exchange start-trading` | scratch-HOME live | ok (0) |
| `--exchange` | `exchange start-trading` | scratch-HOME live | ok (0) |
| `--db` | `exchange verify` | path-guard + live FAIL row | expected-refusal (1) |
| `--bridge-db` | `exchange verify` | live (drift traceback) | drift (1) |
| `--rpc-url` | `exchange verify` | live (drift traceback) | drift (1) |
| `--ait-rpc` | `exchange verify` | live (drift traceback) | drift (1) |
| `--escrow-address` | `exchange verify` | live (drift traceback) | drift (1) |
| `--bridge-address` | `exchange verify` | live (drift traceback) | drift (1) |
| `--settlement` | `exchange verify` | live FAIL row | expected-refusal (1) |
| `--json` | `exchange verify` | live FAIL row | expected-refusal (1) |
| `--wallet` | `exchange-island buy` | island-credentials refusal | expected-refusal (1) |
| `--wallet` | `exchange-island sell` | island-credentials refusal | expected-refusal (1) |

Exit classes: ok exit 0 (13 plays), expected-refusal exit 1/2/4
(11 plays), drift exit 1 (1 play — the `exchange_verify.py`
`no such table: trades` traceback, flagged for registration).

---

## Safety notes

- `exchange order place/cancel/fund`, `node register/set-payout` all
  sign an envelope with the node's wallet — never run them with a real
  wallet unless an order/registration is intended; the signatures are
  dedupe keys on the hub.
- `exchange prepay deposit --send` broadcasts a real Sepolia ETH
  transaction; the default `--print` preview still requires a
  registered-node row to succeed.
- The `exchange register/create-pair/start-trading/add-liquidity`
  family silently writes `~/.aitbc/exchanges.json` in the caller's
  HOME — on a node with a real integration file, a scratch `HOME` is
  the safe sandbox.
