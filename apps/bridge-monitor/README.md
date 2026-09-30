# bridge-monitor

Ethereum→AIT bridge payout monitor. Watches the configured Sepolia deposit
address for ETH inflows, prices each deposit via the oracle pair, and pays
the AIT equivalent from a dedicated payout wallet — ledger-first, and a
deposit is only `COMPLETED` once its payout transaction is sealed at the
configured depth.

**Node type:** hub · **GPU:** no · **Unit:** `aitbc-bridge-monitor.service`

## Ledger lifecycle

Each inflow lands a row in `eth_deposits` (`DATA_DIR/bridge_deposits.db`):

| Status | Meaning |
|--------|---------|
| `PENDING`/`PROCESSING` | seen on-chain, awaiting confirmation depth |
| `PENDING_RETRY` | retryable failure — no signed envelope exists yet |
| `SUBMITTED` | owns a signed payout envelope that may still seal — never re-sign it |
| `COMPLETED` | payout sealed at `PAYOUT_SEAL_DEPTH` |
| `FAILED` | permanent failure (bad recipient, over-cap, dust) — deliberate resolution required |
| `WRITTEN_OFF` | operator-declared terminal loss (reason recorded) |
| `FUNDING` | inflow from a configured `BRIDGE_FUNDING_SOURCES` sender — recorded, never paid out |

## Operator commands

Every payout goes through a ledger row — never send ad-hoc from the payout
account. Operator actions:

```bash
cd /opt/aitbc && venv/bin/python -m bridge_monitor.admin <command>
#   status <tx_hash>                inspect a ledger row
#   manual-payout <to> <amount>     manual payout, ledger-first (uncapped by design)
#   abandon-and-resign <tx_hash>    re-queue a stuck SUBMITTED payout —
#                                   refuses unless the account nonce has passed
#                                   the envelope nonce AND it is unsealed
#   write-off <tx_hash> --reason …  terminal write-off (reason required)
```

## Safety invariants

- **Serialization** — at most one `SUBMITTED` envelope in flight; a stuck row
  head-of-line-blocks the queue and alerts at `BRIDGE_STUCK_PAYOUT_BLOCKS`.
- **Never re-sign** — a `SUBMITTED` envelope is rebroadcast verbatim; a fresh
  nonce could double-pay if the original then landed.
- **Price lock** — the first computed `ait_amount` is authoritative; retries
  pay exactly it. An unpriced row (`amount_ait='0'`, oracle outage) reprices
  on retry, never submits zero.
- **Per-deposit caps** — a payout may not exceed `BRIDGE_MAX_PAYOUT_FRACTION`
  of the wallet balance *and*, when set, `BRIDGE_MAX_PAYOUT_AIT`; the stricter
  binds. The absolute ceiling applies even when the balance RPC is down.
- **Committed float** — the low-float alert fires on balance minus amounts
  committed to non-terminal rows.

## Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `BRIDGE_ETH_ADDRESS` | — | Sepolia deposit address to watch |
| `BRIDGE_PAYOUT_ADDRESS` / `BRIDGE_PAYOUT_PRIVATE_KEY` | — | dedicated payout wallet (limited float) |
| `BRIDGE_CONFIRMATIONS` | `3` | ETH-side confirmations before processing |
| `MIN_ETH_DEPOSIT` / `BRIDGE_MIN_DEPOSIT_AIT` | `0.001` / `1` | dust floors (sub-minimum → `FAILED`, recorded) |
| `BRIDGE_FUNDING_SOURCES` | — | comma-separated ETH sender addresses whose inflows are float top-ups → `FUNDING`, not deposits. Case-insensitive match |
| `BRIDGE_MAX_PAYOUT_FRACTION` | `0.5` | max fraction of wallet balance per payout |
| `BRIDGE_MAX_PAYOUT_AIT` | unset | absolute AIT ceiling per payout — applies even with the balance RPC down |
| `BRIDGE_LOW_FLOAT_AIT` / `BRIDGE_LOW_FLOAT_ETH` | `50` / `0.01` | float alert floors (AIT on *available*, ETH raw) |
| `BRIDGE_FLOAT_ALERT_INTERVAL_SECONDS` | `3600` | min seconds between repeated low-float alerts (a persistent condition alerts at this cadence, not per poll; a cleared condition re-alerts immediately) |
| `PAYOUT_SEAL_DEPTH` | `2` | chain confirmations before `COMPLETED` |
| `PAYOUT_REBROADCAST_BLOCKS` / `PAYOUT_MAX_REBROADCAST` | `6` / `5` | rebroadcast cadence and budget for the same envelope |
| `BRIDGE_STUCK_PAYOUT_BLOCKS` | `rebroadcast×max` | head-of-line blocking alert horizon |
| `BRIDGE_QUEUE_ALERT_DEPTH` | `5` | `PENDING_RETRY` depth alert |
| `BRIDGE_POLL_INTERVAL` | `30` | poll cadence (seconds); `BRIDGE_KICK_FILE`/`BRIDGE_BURST_*` accelerate demand-triggered polls |
| `AIT_USD_FIXED_PRICE` | unset | pins the AIT/USD quote (oracle bypass) |
| `BLOCKCHAIN_RPC_URL` | `http://127.0.0.1:8202` | node RPC — balance, nonce, and submit all share this endpoint |
| `BRIDGE_MONITOR_ENV` | `/etc/aitbc/aitbc-bridge-monitor.env` | env file loaded by `admin.py` |
| `GENESIS_WALLET_ADDRESS` / `GENESIS_WALLET_PRIVATE_KEY` | — | transitional fallback for the payout wallet — deprecated; set `BRIDGE_PAYOUT_*` instead (a warning is logged when the fallback signs) |
| `CHAIN_ID` | `ait-localnet` | chain ID bound into signed payout transactions |
| `BRIDGE_BURST_INTERVAL` / `BRIDGE_BURST_WINDOW` | `20` / `60` | fast poll cadence and the window it applies for after a kick-file touch |

## Layout

`src/bridge_monitor/` — `main.py` (poll loop, payout lifecycle, caps, float
checks), `storage.py` (ledger schema + committed-float sums), `admin.py`
(operator commands). Tests in `tests/` cover price locking, both caps,
committed-float accounting, and the retry/envelope paths.

---
*Last updated: 2026-09-30*
