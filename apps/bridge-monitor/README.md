# bridge-monitor

Ethereum→AIT bridge payout monitor. Watches the configured Sepolia deposit
address for ETH inflows, prices each deposit via the oracle pair, and pays
the AIT equivalent from a dedicated payout wallet — ledger-first, and a
deposit is only `COMPLETED` once its payout transaction is sealed at the
configured depth.

**Node type:** hub · **GPU:** no · **Unit:** `aitbc-bridge-monitor.service`

## Ledger lifecycle

Each inflow lands a row in `eth_deposits` (`DATA_DIR/data/bridge_deposits.db`;
the dir resolves `AITBC_DATA_DIR` first, then `DATA_DIR`, then
`/var/lib/aitbc`):

| Status | Meaning |
|--------|---------|
| `PENDING`/`PROCESSING` | seen on-chain, awaiting confirmation depth |
| `PENDING_RETRY` | retryable failure — no signed envelope exists yet |
| `SUBMITTED` | owns a signed payout envelope that may still seal — never re-sign it |
| `COMPLETED` | payout sealed at `PAYOUT_SEAL_DEPTH` |
| `FAILED` | permanent failure (bad recipient, over-cap, dust) — deliberate resolution required |
| `WRITTEN_OFF` | operator-declared terminal loss (reason recorded) |
| `FUNDING` | inflow from a configured `BRIDGE_FUNDING_SOURCES` sender — recorded, never paid out |
| `EXCHANGE_PREPAY` | inflow carrying an `EXCHANGE_DEPOSIT:<addr>` tag — credited to the buyer's prepaid exchange balance by the wallet-side settlement monitor (ETH-8 phase 3), never minted |

## Operator commands

Every payout goes through a ledger row — never send ad-hoc from the payout
account. Operator actions:

```bash
cd /opt/aitbc && scripts/ops/bridge-admin.sh <command>
#   status <tx_hash>                inspect a ledger row
#   list [--status S] [--limit N]   recent rows (incl. FUNDING/FAILED), newest first
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
| `BRIDGE_CYCLE_TIMEOUT_SECONDS` | `300` | bound on one block-scan pass — a breach holds the cursor and alerts; a cycle exceeding it also logs `ALERT` |
| `BRIDGE_HEAD_STALL_SECONDS` | `600` | alert when the ETH endpoint keeps serving the same head (stale LB backend) — deposits sealing on-chain are then not being scanned |
| `ETH_RPC_TIMEOUT` | `10` | per-request timeout (seconds) for the Ethereum RPC provider |
| `AIT_USD_FIXED_PRICE` | unset | pins the AIT/USD quote (oracle bypass) |
| `BLOCKCHAIN_RPC_URL` | `http://127.0.0.1:8202` | node RPC — balance, nonce, and submit all share this endpoint |
| `BRIDGE_MONITOR_ENV` | `/etc/aitbc/aitbc-bridge-monitor.env` | env file loaded by `admin.py` |
| `BRIDGE_DEPOSITS_DB` | unset | absolute ledger path override; unset resolves `DATA_DIR/data/bridge_deposits.db`. An empty or whitespace-only value is treated as unset. Set for every consumer or none — a consumer left on the old path silently creates an empty ledger |
| `GENESIS_WALLET_ADDRESS` / `GENESIS_WALLET_PRIVATE_KEY` | — | transitional fallback for the payout wallet — deprecated; set `BRIDGE_PAYOUT_*` instead (a warning is logged when the fallback signs) |
| `CHAIN_ID` | `ait-localnet` | chain ID bound into signed payout transactions |
| `BRIDGE_BURST_INTERVAL` / `BRIDGE_BURST_WINDOW` | `20` / `60` | fast poll cadence and the window it applies for after a kick-file touch |
| `EXCHANGE_SETTLEMENT_ENABLED` | `false` | ETH-8 phase 3: routes `EXCHANGE_DEPOSIT:<addr>`-tagged inflows to `EXCHANGE_PREPAY` rows instead of the mint path; bypasses `MIN_ETH_DEPOSIT` (no payout is owed). Flag-off leaves the old path — the tag fails recipient parsing → `FAILED` |

## Outbound ledger (`bridge_outbound`)

Every ETH send *from* the bridge wallet is ledgered (`record_outbound`,
deduped on `tx_hash`). `kind` is assigned by strongest evidence first: the
tx hash found in a release-leg table (`eth_withdrawals`,
`bridge_sell_locks`, or `exchange_settlements` — the note names which) →
`withdrawal`; `to` the wallet itself → `self_send` (gas only, value
returns); `to` a recorded depositor → `refund`; `to` a
`BRIDGE_FUNDING_SOURCES` address → `withdrawal` (float return); otherwise
`unidentified` and logged as a warning — the reconcile treats that term as
untrusted. A failed send records gas only (`value_eth = 0`, intended value
in `note`).

## Layout

`src/bridge_monitor/` — `main.py` (poll loop, payout lifecycle, caps, float
checks), `storage.py` (ledger schema + committed-float sums), `admin.py`
(operator commands). Tests in `tests/` cover price locking, both caps,
committed-float accounting, and the retry/envelope paths.

---
*Last updated: 2026-09-30*
