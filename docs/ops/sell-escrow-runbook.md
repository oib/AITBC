# Sell escrow runbook — escrowed AIT→ETH sell flow (ETH-10, phase 1)

> Phase-1 keyed-escrow sell flow per
> `docs/design/eth7-escrowed-sell-flow.md`. Sepolia only. The feature is
> **off by default** (`SELL_ESCROW_ENABLED` defaults to `false`) and the
> whole surface fail-closes when any key slot or address is missing.

## What runs where

| piece | host | what it does |
|---|---|---|
| `aitbc-wallet` sell monitor | hub | polls the chain for `TRANSFER`s to `AIT_SELL_ESCROW` carrying `payload.sell_quote`; releases ETH from the bridge wallet; settles escrow→treasury; refunds escrow→shop on orphan/deadline/failure |
| `POST /v1/bridge/sell/quote`, `GET /sell/status/<id>`, `GET /sell/list` | hub wallet service | quote issue + status; admin key required for `quote` (same `require_admin_api_key` stance as the other mutating bridge routes) |
| `aitbc wallet bridge sell quote\|lock\|status` | shop node | `quote`/`status` hit the hub over HTTP (`--hub-url` — the hub wallet daemon itself is loopback-only); `lock` signs the `TRANSFER` **on the shop's own node** with the shop's own wallet and submits it to the *local* chain RPC — the hub never sees the key |

## Configuration (hub `/etc/aitbc/exchange.env` — comments on their own lines)

```bash
# Master switch — the feature does nothing until this is true.
SELL_ESCROW_ENABLED=false
# Escrow address the shop's lock TRANSFER targets (0x…).
AIT_SELL_ESCROW=
# Hub treasury address that receives settled AIT.
SELL_TREASURY_ADDRESS=
# Escrow key slot — ops-signer custody mechanism: an encrypted wallet JSON
# plus a systemd-creds sealed password file. No key value ever goes in env.
SELL_ESCROW_WALLET_PATH=/var/lib/aitbc/wallets/ait-sell-escrow.json
SELL_ESCROW_CREDENTIAL_FILE=/etc/aitbc/credentials/sell-escrow-pass
SELL_ESCROW_CREDENTIAL_NAME=sell-escrow-pass
# Caps / timeouts (defaults shown).
SELL_MAX_ETH_PER_TX=0.01
SELL_MAX_ETH_PER_DAY=0.03
SELL_RELEASE_DEADLINE=3600
SELL_LOCK_ORPHAN_BLOCKS=150
SELL_QUOTE_EXPIRY_SECONDS=900
SELL_POLL_INTERVAL=30
SELL_MAX_OPEN_QUOTES_PER_SHOP=5
SELL_QUOTE_MIN_INTERVAL_SECONDS=30
# Price-feed freshness gate for quote issue and release (default 7200 = 2 h).
BRIDGE_PRICE_MAX_AGE=7200
# Comma-separated AIT addresses whose sends to the escrow are float
# top-ups (fee seed / operating balance), never sell locks — without this
# the scanner would treat the operator's seed send as an orphan lock and
# refund it right back. Mirrors BRIDGE_FUNDING_SOURCES on the ETH side.
SELL_ESCROW_FUNDING_SOURCES=
# Reused existing keys: CHAIN_ID (required — the monitor refuses to sign
# escrow sweeps without it; there is no ait-localnet fallback),
# ETH_WALLET_ADDRESS (release source),
# ETH_WITHDRAW_MIN_RESERVE (float floor, default 0.005),
# BRIDGE_MAX_PAYOUT_FRACTION (per-release fraction-of-float cap, 0.5),
# BRIDGE_RELEASE_CONFIRMATIONS / BRIDGE_CONFIRMATIONS (receipt depth, 3).
```

Reads: `sell_escrow_monitor.py::_sell_config` reads all of the above at
monitor start and on every poll; `bridge_routes.py` reads
`SELL_MAX_OPEN_QUOTES_PER_SHOP`/`SELL_QUOTE_MIN_INTERVAL_SECONDS`/
`MIN_AIT_WITHDRAW` on the quote route; `price_api.py` reads
`BRIDGE_PRICE_MAX_AGE` inside `get_eth_prices_fresh`. An **invalid**
cap/reserve/deadline value makes the sell monitor refuse to start (the
withdraw monitor keeps running); a *missing* one uses the documented
default.

## The escrow key slot — operator action, no agent

Per operator decision (b): the **operator** generates the escrow key on the
hub and custodies it as its own ops-signer-style entry — an encrypted
wallet JSON file plus a `systemd-creds`-sealed password file, exactly like
`aitbc-ops-signer`'s wallet (`OPS_WALLET_PATH` + `ops-wallet-pass`). The
monitor loads the slot inside the signing call only: password from
`$CREDENTIALS_DIRECTORY/<name>` when systemd provides it, else
`systemd-creds decrypt --name=<name> <credential-file>` (the LXC
fallback), then `decrypt_value` on the wallet's `private_key`. The key is
never in env, argv, logs, or the bridge DB; the derived address is checked
against `AIT_SELL_ESCROW` on every load, and there is **no fallback** to
any other key.

Operator steps (runbook `ops-signer-runbook.md` machinery, escrow slot):

```bash
# on hub, as root — create the wallet entry (CLI wallet format) and seal
# the password as a systemd credential. The password is chosen by the
# operator and typed interactively — it is never written to any file in
# cleartext.
cd /opt/aitbc && venv/bin/python -c '
from aitbc.security.encryption import encrypt_value
from eth_account import Account
import json, getpass
acct = Account.create()
pw = getpass.getpass("escrow wallet password: ")
json.dump({"address": acct.address,
           "private_key": encrypt_value(acct.key.hex(), pw)},
          open("/var/lib/aitbc/wallets/ait-sell-escrow.json", "w"))
print("AIT_SELL_ESCROW =", acct.address)'
chmod 600 /var/lib/aitbc/wallets/ait-sell-escrow.json
chown aitbc:aitbc /var/lib/aitbc/wallets/ait-sell-escrow.json
systemd-creds encrypt --name=sell-escrow-pass \
  - /etc/aitbc/credentials/sell-escrow-pass   # type the same password + Enter, then Ctrl-D
# aitbc-wallet runs as User=aitbc — the slot must be readable by it,
# mode 0600 (unlike the root-owned ops-signer credential).
chown aitbc:aitbc /etc/aitbc/credentials/sell-escrow-pass
chmod 600 /etc/aitbc/credentials/sell-escrow-pass
```

Record `AIT_SELL_ESCROW` in `exchange.env`; the printed address is the
only output — the key material stays sealed.

## The escrow fee float — the escrow account needs seed AIT

Every escrow sweep (a settle to treasury or a refund to a shop) spends the
locked amount **plus the standard 0.01 AIT transfer fee** from the escrow
account. The locked amounts alone do not cover the fees — the escrow needs
a small seed AIT balance on top of whatever it custodies.

Before signing a sweep the monitor checks the on-chain escrow balance
against `amount + 0.01 AIT`. A shortfall **parks** the row — never fails,
never signs blind:

- `queued_fee_settle` / `queued_fee_refund` — the row's `error` field
  carries the exact deficit; the sweep retries every poll and proceeds
  the moment the balance covers it. Nothing else is needed — no restart,
  no manual status change.

The check compares against the **total** escrow balance — funds custodied
for other pending locks are *not* reserved. With several open locks the
real margin is `balance − Σ(open lock amounts)`, so size the float against
the lock book, not just the raw balance. Recommended minimum standing
float: **1 AIT above the sum of open (unsettled) lock amounts** — each
sweep costs its amount plus 0.01 AIT, so 1 AIT covers ~100 sweep fees of
headroom on top of whatever is custodied.

Top up with an ordinary wallet send **from an address listed in
`SELL_ESCROW_FUNDING_SOURCES`**. The scanner skips sends from those
addresses entirely — an unlisted sender's top-up would be recorded as an
orphan lock and refunded back after the orphan window, which is exactly
the wrong outcome. Seed once, a few AIT is plenty (0.01 AIT per sweep).

## Enabling — prerequisites in order

1. ETH-2 (first live withdrawal) has run and the ETH-9/9b monitor is live
   on the hub.
2. The escrow key slot exists (above) and `AIT_SELL_ESCROW` is set.
3. The bridge ETH float is topped up (~0.10 ETH via a
   `BRIDGE_FUNDING_SOURCES` send — operator action) **and the escrow
   AIT fee float is seeded** (e.g. 5 AIT from a
   `SELL_ESCROW_FUNDING_SOURCES` address — above).
4. `SELL_ESCROW_ENABLED=true` + the rest of the env block set —
   including `CHAIN_ID` (no default; missing means the monitor refuses
   to sign).
5. `systemctl restart aitbc-wallet` — the one unit that reads the sell
   config. (The operator names the restart; the monitor logs either
   `Starting AIT->ETH sell escrow monitor` or one clear `disabled` line.)

Rollback: `SELL_ESCROW_ENABLED=false` + `systemctl restart aitbc-wallet`.
Open locks keep their rows; a live hub processes them once re-enabled —
nothing is stranded by a disabled monitor except time.

## Runtime behaviour

- Lock detected → sender must equal the quote's `shop_ait_address` (a
  foreign lock on a live quote id is orphan-refunded to its real sender)
  → caps/reserve checked from persisted rows → ETH release (intent
  `releasing` + signed hash persisted *before* broadcast) → `released` →
  settle escrow→treasury after the release receipt reaches
  `BRIDGE_RELEASE_CONFIRMATIONS` depth.
- The lock scan reads the **complete** escrow history every poll:
  `/rpc/transactions` has no pagination, and the monitor passes `limit=0`
  — the endpoint's `if limit:` guard then skips truncation — so a burst of
  any size cannot hide a lock behind a page limit.
- `queued_reserve` = float/cap-bound: retried every poll until released
  or the deadline fires; the error field carries the deficit.
- `stale_price` = feed older than `BRIDGE_PRICE_MAX_AGE`: parked while
  still escrowed, resumed when the feed recovers.
- `orphaned` = no live quote (incl. a second lock reusing a bound quote):
  refunded once `locked_height + SELL_LOCK_ORPHAN_BLOCKS` has passed.
- `needs_review` = ambiguous **ETH release** outcome (receipt missing but
  nonce consumed, RPC down, shallow receipt): **never auto-refunds**;
  re-verified every poll and completes on its own when the receipt
  reaches depth.
- `needs_review_sweep` = the **escrow sweep** intent became undecidable:
  the recorded nonce was consumed by an unmatched transaction (a manual
  send from the escrow account), the nonce was never persisted, or the
  stored signed blob is gone. Unlike `needs_review` this status is
  **terminal for the monitor** — it is never auto-processed, never
  re-swept, and the row only moves by an explicit operator action via
  `sell_admin` (see "Operator command" below).
- Escrow sweeps are **serialized**: at most one `settling`/`refunding`
  row is in flight at a time. A row leaves that state only when its
  outflow is found *sealed* — matched on nonce + recipient + amount +
  `payload.sell_ref`, so a foreign transaction at the same nonce can
  never be credited — or resolved to `needs_review_sweep` (e.g. the nonce
  was consumed by an unmatched tx — a manual send from the escrow
  account).
  A queued sweep simply waits for the next poll; a stuck in-flight sweep
  blocks later sweeps until resolved, the same head-of-line discipline
  the ETH payout ledger uses.
- Escrow-side settle/refund transfers persist nonce + signed blob before
  broadcast; a restart mid-flight re-broadcasts the identical blob —
  never a fresh signature at a new nonce — so a resume cannot double-pay.
- `refund_pending` = the ETH release provably never landed and the row
  owes a refund — it stays open until the refund sweep is in flight.
- `queued_fee_settle` / `queued_fee_refund` = sweep parked on the escrow
  fee float (see above); the error field carries the AIT deficit.
- Deadline and orphan refunds are evaluated on successful polls only: a
  failed lock scan aborts the poll, so an RPC outage can never drive a
  refund decision on stale data.

## Operator command (ETH-13)

`needs_review_sweep` rows and fee-parked sweeps are operated from hub as
root, through the wallet-package admin module — same environment and the
same dry-run/`--confirm --note` contract as `withdraw_admin`:

```bash
cd /opt/aitbc
PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
    venv/bin/python -m wallet_app.bridge.sell_admin <command>
```

| verb | scope | effect |
|---|---|---|
| `list [--status S]…` | read-only | lock rows (default: all open statuses) |
| `inspect <ait_tx_hash>` | read-only | full row, quote, parsed sweep intent (the signed blob is never printed), escrow nonce/balance |
| `confirm-swept <hash> --tx <sealed_hash>` | `needs_review_sweep` | re-verifies `--tx` on-chain with the monitor's own match rule (nonce + recipient + amount + `payload.sell_ref`), then writes `settled`/`refunded` with the real hash — no hash or mismatch ⇒ refuse |
| `requeue <ait_tx_hash>` | `needs_review_sweep` | returns the row to the lane its intent was in — `released` for a settle, `refund_pending` for a refund; the monitor re-runs its normal sweep next poll (no quote/cap re-check). Refuses while another sweep is in flight, and when the intent blob is unreadable (lane indeterminate) |
| `write-off <ait_tx_hash> --reason "…"` | any open, non-in-flight row | terminal `written_off`; the ETH leg stays recorded, the AIT leg is marked abandoned. Refuses `releasing`/`settling`/`refunding` — a live send owns those rows |
| `sweep-now <ait_tx_hash>` | `queued_fee_settle`/`queued_fee_refund` | runs the monitor's own `_escrow_sweep` once, synchronously — same fee-float check, so a still-short escrow re-parks identically. An accelerator for "I just funded the escrow", not an override |

Rules, mirroring the monitor's own invariants: the module runs **on hub
as root only** — it refuses when euid ≠ 0 or `BLOCKCHAIN_MODE` ≠ `hub` in
the loaded env set, and it refuses when the bridge ledger file is absent
rather than create an empty DB on the wrong host. These gates are a
guard rail for the operator, not a security boundary — env-file values
load through `os.environ.setdefault`, so a `BLOCKCHAIN_MODE` already
exported in the shell wins over the files. Every mutating verb is
a dry-run by default and writes only with `--confirm --note "…"`; every
status change goes through `update_sell_lock_status`; resolutions stamp
`resolved_by`/`resolved_at`/`operator_note` (ETH-13 audit columns, added
by `init_db`'s column-if-missing migration on first run) and record
`operator:<verb>` in the row's error field; nothing signs or broadcasts
except `sweep-now`, which lives inside `_escrow_sweep`'s
persist-intent-then-broadcast order; sweep serialization holds across
manual actions — a requeued row sweeps exactly once on the monitor's own
in-flight gate. `SELL_ESCROW_ENABLED` is not required — the sell config
addresses and the escrow key slot must still be loadable for
chain-touching verbs.

Typical `needs_review_sweep` resolution:

```bash
# 1. what does the row think happened?
venv/bin/python -m wallet_app.bridge.sell_admin inspect <ait_tx_hash>
# 2. inspect the escrow account's sealed history at escrow_out_nonce —
#    does a transaction carry this row's sell_ref/amount/recipient?
#    (chain explorer or /rpc/transactions?address=<escrow>)
# 3a. it sealed → venv/bin/python -m wallet_app.bridge.sell_admin \
#       confirm-swept <ait_tx_hash> --tx 0x<sealed> --confirm --note "…"
# 3b. nothing sealed → venv/bin/python -m wallet_app.bridge.sell_admin \
#       requeue <ait_tx_hash> --confirm --note "…"
# 3c. unrecoverable → venv/bin/python -m wallet_app.bridge.sell_admin \
#       write-off <ait_tx_hash> --reason "…" --confirm --note "…"
```

## First live run (shop side, e.g. node2)

```bash
# quote — hits the hub wallet route; the shop's key never leaves node2
aitbc wallet bridge sell quote --amount 10 \
  --eth-address 0x<shop-sepolia-addr> \
  --hub-url http://<hub>:8108           # or the hub's exposed wallet mount
# lock — signs the TRANSFER on node2, submits to the LOCAL chain RPC
aitbc wallet bridge sell lock --quote-id sellq_… --wallet-name <shop>
# status
aitbc wallet bridge sell status --id sellq_…
```

A forced-failure check: quote, wait out `SELL_QUOTE_EXPIRY_SECONDS`
(15 min), lock against the expired quote, stop the feed
(`BRIDGE_PRICE_MAX_AGE` exceeded) → the row parks `stale_price`, then
`refunded` once the deadline passes — or releases at the re-quoted live
rate if the feed recovers first.

## Follow-up: B13 `bridge_outbound` ledger kinds

Out of scope here, tracked for the outbound-ledger design: the sell flow
introduces `sell_release` (hub→shop ETH) plus `sell_settle` /
`sell_refund` (escrow→treasury / escrow→shop AIT). A `bridge_outbound`
ledger that wants to account for these needs the sell-lock row's
`ait_tx_hash`/`settle_tx_hash`/`refund_tx_hash` fields joined by
`sell_ref` in the AIT tx payload, and to treat `AIT_SELL_ESCROW` outflows
as bridge outbound, not generic treasury moves.
