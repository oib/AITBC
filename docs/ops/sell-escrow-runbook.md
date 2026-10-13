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
# Reused existing keys: ETH_WALLET_ADDRESS (release source),
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

## Enabling — prerequisites in order

1. ETH-2 (first live withdrawal) has run and the ETH-9/9b monitor is live
   on the hub.
2. The escrow key slot exists (above) and `AIT_SELL_ESCROW` is set.
3. The bridge ETH float is topped up (~0.10 ETH via a
   `BRIDGE_FUNDING_SOURCES` send — operator action).
4. `SELL_ESCROW_ENABLED=true` + the rest of the env block set.
5. `systemctl restart aitbc-wallet` — the one unit that reads the sell
   config. (The operator names the restart; the monitor logs either
   `Starting AIT->ETH sell escrow monitor` or one clear `disabled` line.)

Rollback: `SELL_ESCROW_ENABLED=false` + `systemctl restart aitbc-wallet`.
Open locks keep their rows; a live hub processes them once re-enabled —
nothing is stranded by a disabled monitor except time.

## Runtime behaviour

- Lock detected → quote matched → caps/reserve checked from persisted
  rows → ETH release (intent `releasing` + signed hash persisted *before*
  broadcast) → `released` → settle escrow→treasury after the release
  receipt reaches `BRIDGE_RELEASE_CONFIRMATIONS` depth.
- `queued_reserve` = float/cap-bound: retried every poll until released
  or the deadline fires; the error field carries the deficit.
- `stale_price` = feed older than `BRIDGE_PRICE_MAX_AGE`: parked while
  still escrowed, resumed when the feed recovers.
- `orphaned` = no live quote (incl. a second lock reusing a bound quote):
  refunded once `locked_height + SELL_LOCK_ORPHAN_BLOCKS` has passed.
- `needs_review` = ambiguous ETH release outcome (receipt missing but
  nonce consumed, RPC down, shallow receipt): **never auto-refunds**;
  re-verified every poll and completes on its own when the receipt
  reaches depth.
- Escrow-side settle/refund transfers persist nonce + signed blob before
  broadcast; a restart mid-flight re-broadcasts the identical blob —
  never a fresh signature at a new nonce — so a resume cannot double-pay.
- Deadline and orphan refunds are evaluated on successful polls only: a
  failed lock scan aborts the poll, so an RPC outage can never drive a
  refund decision on stale data.

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
