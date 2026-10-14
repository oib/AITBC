# Sepolia Buy/Sell AIT via the ETH Bridge

**Level**: Operator
**Prerequisites**: [per-node Sepolia wallets](../ops/node-sepolia-wallets.md)
(ETH-1) — a funded `sepolia` wallet file on node0 and/or node2
**Estimated Time**: 15 minutes per direction, mostly waiting for confirmations
**Last Updated**: 2026-10-13
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Sepolia Buy/Sell AIT via the ETH Bridge

---

## Scenario Overview

> **Operator play:** both directions move real (testnet) value and burn or
> mint AIT. Every send step is an operator action; nothing here runs
> automatically.

Two plays against the live Sepolia bridge (bridge wallet
`0x310dcE00270D0aC10CAccfBD636Ff07BD5648781`, ≈0.05 ETH float):

- **Scenario A — buy AIT**: node0's Sepolia wallet sends ETH to the bridge
  wallet; the bridge monitor detects it, prices it, and pays out AIT from
  the hub payout wallet to the depositor's AIT address.
- **Scenario B — sell AIT**: node2 burns AIT via a signed
  `BRIDGE_WITHDRAW`; hub's withdrawal monitor sees the sealed burn and
  releases ETH from the bridge wallet to node2's Sepolia address.

### Safe test amounts (chosen for the ≈0.05 ETH float)

| play | amount | why |
|---|---|---|
| A — deposit | **0.002 ETH** | 2× `MIN_ETH_DEPOSIT` (0.001); ≈$5 ⇒ ~18 AIT payout at current oracle prices (ETH ≈$2,508, AIT ≈$0.279) — far under `BRIDGE_MAX_PAYOUT_FRACTION` (0.5 × ~747 AIT payout float); deposits *grow* the ETH float |
| B — withdraw | **10 AIT** | far above `MIN_AIT_WITHDRAW` (0.01); ≈$2.79 ⇒ ~0.0011 ETH released + ~0.0002 gas — ~2.6% of the float; stays well above the 0.005 ETH `ETH_WITHDRAW_MIN_RESERVE` |

### Use Case

Proves the bridge works end-to-end in both directions on the per-node
wallets created by ETH-1, without touching the bridge wallet key.

---

## Scenario A — buy AIT (node0)

### Step A1 — preflight on any host (read-only)

```bash
# instructions + estimate, served by hub's wallet daemon
# (node0's own wallet service has no ETH_WALLET_ADDRESS -> HTTP 503, see Gap 1)
ssh hub 'curl -s -X POST http://localhost:8108/v1/bridge/deposit \
  -H "Content-Type: application/json" \
  -d "{\"eth_amount\": \"0.002\", \"ait_address\": \"<node0-sepolia-address>\"}"'
```

Expect `"status": "ready"`, `instructions.send_eth_to` =
`0x310dcE00270D0aC10CAccfBD636Ff07BD5648781`, and
`instructions.transaction_data_hex` = the `0x`-prefixed hex of the UTF-8
recipient string (see "data format" below).

Equivalent MCP call (read-only):
`get_eth_bridge_deposit_instructions(eth_amount=0.002, ait_address=..., role="hub")`.

### Step A2 — the deposit send (operator, on node0)

`aitbc wallet bridge deposit` calls `wallet_daemon_url` for the
instructions; hub's daemon is loopback-only (`127.0.0.1:8108`) and node0
has no route or ssh path to hub at all — so the CLI path needs one of
these operator choices:

**Option A2.1 — bridge-enable node0's wallet service (recommended)**
(adds two env lines + one restart; an operator change on the host):

```bash
# on node0, as root — append to /etc/aitbc/exchange.env (comment on its
# own line; EnvironmentFile does not strip inline comments):
cat >> /etc/aitbc/exchange.env <<'EOF'
ETH_WALLET_ADDRESS=0x310dcE00270D0aC10CAccfBD636Ff07BD5648781
ETH_NETWORK=sepolia
ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
EOF
systemctl restart aitbc-wallet && systemctl is-active aitbc-wallet

cd /opt/aitbc
venv/bin/python -m aitbc_cli wallet bridge deposit \
  --wallet-name sepolia --amount 0.002 \
  --eth-rpc-url https://ethereum-sepolia-rpc.publicnode.com
# wallet password prompt (TTY) — the CLI signs the ETH tx with the
# sepolia key; the AIT recipient is that same 0x address
```

**Non-interactive form (agents / no TTY):** the same command takes
`--password-file` or `--password-stdin` like every signing command. The
shared order is `--password-stdin` → `--password-file` → `--password`
(deprecated) → `AITBC_WALLET_PASSWORD_FILE` → `AITBC_WALLET_PASSWORD[_<NAME>]`
→ keyring → TTY prompt; an explicit flag always beats env and keyring.
Keep the password file **on the node that owns the wallet** (here: node0),
mode `0600`, owned by the user that runs the CLI — never in the repo,
never copied to another node:

```bash
# file form — /etc/aitbc/sepolia.wallet.pass must be 0600 on node0:
venv/bin/python -m aitbc_cli wallet bridge deposit \
  --wallet-name sepolia --amount 0.002 \
  --eth-rpc-url https://ethereum-sepolia-rpc.publicnode.com \
  --password-file /etc/aitbc/sepolia.wallet.pass

# stdin form — the secret never touches argv or a file:
ssh node0 'read -rs PASS'   # or deliver it from your secrets store
printf '%s\n' "$PASS" | ssh node0 'cd /opt/aitbc && \
  venv/bin/python -m aitbc_cli wallet bridge deposit \
  --wallet-name sepolia --amount 0.002 \
  --eth-rpc-url https://ethereum-sepolia-rpc.publicnode.com \
  --password-stdin'
```

**Option A2.2 — manual send (no env change, no CLI)**

Send the Sepolia tx from the `sepolia` key with any ETH tooling:
`to = 0x310dcE00270D0aC10CAccfBD636Ff07BD5648781`, `value = 0.002 ETH`,
`data = 0x` + hex of the UTF-8 AIT recipient address (A1 shows the exact
`transaction_data_hex`). No AITBC command performs this — it is Gap 2.

### Deposit transaction data format

The monitor (`bridge_monitor/main.py::parse_ait_recipient`) accepts two
encodings in the Ethereum tx `data` field:

1. **UTF-8 text** — the 42-char EIP-55 `0x…` AIT address as bytes;
   the wallet service emits `"0x" + address.encode("utf-8").hex()`.
2. **Raw address** — the bare 20-byte / 40-hex address.

Anything else (bad checksum, junk, empty) records the deposit as FAILED —
the ETH stays in the bridge wallet until refunded.

### Step A3 — confirm and verify

Timeline: the monitor only *sees* a deposit once it is
`BRIDGE_CONFIRMATIONS` = 3 Sepolia blocks deep (~40 s); the instruction
call above also kicked the burst poller (~3 polls/60 s). Payout seals
within ~2 AITBC blocks. End-to-end: **1–5 minutes** typical.

```bash
# ledger row on hub (operator):
ssh hub 'cd /opt/aitbc && venv/bin/python -m bridge_monitor.admin \
  status <eth_tx_hash>'
#   expect: status completed, ait_tx_hash set

# AIT side (on node0 — the sepolia wallet is also the AIT wallet):
cd /opt/aitbc && venv/bin/python -m aitbc_cli wallet balance --name sepolia
#   expect: ~28 AIT (amount priced at sealed-time oracle rates)

# ETH side (read-only):
venv/bin/python scripts/ops/sepolia_balance.py \
  <node0-sepolia-address> 0x310dcE00270D0aC10CAccfBD636Ff07BD5648781
#   node0 down 0.002 ETH + gas; bridge up 0.002 ETH, nonce still 0
```

## Scenario B — sell AIT (node2)

### Step B1 — estimate (read-only)

```bash
ssh node2 'curl -s -X POST http://localhost:8108/v1/bridge/withdraw/estimate \
  -H "Content-Type: application/json" \
  -d "{\"ait_amount\": \"10\", \"eth_address\": \"<node2-sepolia-address>\"}"'
```

or MCP: `eth_bridge_withdraw_estimate(ait_amount=10, eth_address=..., role="node2")`.

Expect `status: ready` and an `eth_amount` ≈ 0.0007.

### Step B2 — the withdraw send (operator, on node2)

```bash
cd /opt/aitbc
venv/bin/python -m aitbc_cli wallet bridge withdraw \
  --wallet-name default --amount 10 --eth-address <node2-sepolia-address>
# node2's funded wallet is named `default` (~92 AIT balance);
# wallet password prompt if the wallet is encrypted
```

**Non-interactive form:** `--password-file /etc/aitbc/default.wallet.pass`
(mode `0600`, on node2 only) or `--password-stdin` — same standard as the
deposit step above; never put the file in the repo or copy it off node2.

The CLI builds the unsigned tx via `POST /v1/bridge/withdraw/build`
(node2's wallet service is fully bridge-configured), signs it with the
**node2 AIT wallet key** — a chain key, not the ETH key — and posts it to
`/rpc/transaction`. Result payload:

```json
{"type": "BRIDGE_WITHDRAW", "from": "<node2 addr>",
 "to": "0x0000000000000000000000000000000000000000",
 "amount": <units>, "fee": <0.01 AIT in units>, "nonce": N,
 "payload": {"eth_address": "<node2 sepolia>", "amount": <units>},
 "signature": "0x…"}
```

**Who releases the ETH:** the withdrawal monitor inside hub's
`aitbc-wallet` service — it polls `/rpc/transactions?type=BRIDGE_WITHDRAW`
every 30 s, and only hub's env holds a release key
(`ETH_WALLET_PRIVATE_KEY`); node2's own monitor short-circuits on key
validation before scanning, so only hub acts. The burn itself is done by
the chain apply (debit + fee at seal), not by the monitor.

Timeline: sealed in the next block (~15 s), seen by the monitor within
one 30 s poll, ETH released immediately after. End-to-end **≤2 min**.

### Step B3 — verify

```bash
# withdrawal row lives in hub's bridge db — read it on/through hub
# (node2 cannot reach hub's loopback daemon; node2's own db never
# gets the row because its monitor has no release key):
ssh hub 'curl -s http://localhost:8108/v1/bridge/withdraw/<ait_tx_hash>'
#   expect: status completed, eth_tx_hash set
#   (or MCP: get_eth_bridge_withdrawal(ait_tx_hash=..., role="hub"))

# ETH side:
venv/bin/python scripts/ops/sepolia_balance.py \
  <node2-sepolia-address> 0x310dcE00270D0aC10CAccfBD636Ff07BD5648781
#   node2 sepolia +~0.0007 ETH; bridge wallet nonce 0 -> 1

# AIT side: node2 wallet down 10 AIT + 0.01 AIT fee (burned at seal)
```

## Watching the ETH side — `aitbc eth transfers`

`aitbc eth transfers` (read-only, key-free, Sepolia only) fetches the
public Blockscout history of every fleet wallet, appends new rows to
`~/.aitbc/eth-transfers.jsonl`, and cross-checks each wallet's outgoing
count against its RPC nonce. Run it **before** and **after** each play:

```bash
# baseline — note the bridge wallet's nonce (0) and each float balance
venv/bin/python -m aitbc_cli eth transfers
# after the play — only new rows appear; nonce and net/balance must move
venv/bin/python -m aitbc_cli eth transfers --address node0 --address bridge
```

For Scenario A expect: one new `out` row on node0 (0.002 ETH + gas),
one matching `in` row on `bridge`, `net=bal yes` on both, bridge nonce
unchanged (deposits are inbound). For Scenario B expect a new `out` row
on `bridge` (~0.0007 ETH release) and nonce 0 → 1. A `NO` flag in the
`net=bal` column or a nonce warning means stop and reconcile before
continuing.

## Rollback / refund paths

- **Deposit never detected / bad data**: the ETH sits in the bridge
  wallet; the `eth_deposits` ledger row is FAILED or absent. Refund is an
  operator action: a plain ETH send back from the bridge wallet (bridge
  key — gated custody), visible to the monitor as an outbound `refund`
  row (B-13 ledger design). The AIT side never minted, so nothing to undo
  there.
- **Deposit detected but payout failed**: `bridge_monitor.admin`
  `abandon-and-resign` / `write-off` / `manual-payout` — the ledger-first
  admin path from AGENTS.md, never a raw resend.
- **Withdraw sealed but ETH release failed** (float too low, RPC down):
  the monitor marks the row `failed` and auto-issues an AIT `TRANSFER`
  refund from the genesis/funding wallet → status `refunded`. Check with
  `list_eth_bridge_withdrawals` / `aitbc wallet bridge status`.
- **Withdraw unsealed**: a mempool BRIDGE_WITHDRAW that never seals
  simply expires — no burn happened.

## Finding — does BRIDGE_WITHDRAW seal at the current protocol version?

**Yes.** Head is ~45,7xx; v9 (signature requirement) has been live since
height 30,400 and v13/v14 only arrive at 46,100.

- **Type accepted**: `BRIDGE_WITHDRAW` is in `AUTHORITY_OPEN_TX_TYPES`
  — any funded account may submit one.
- **Signature**: it is a *user-signed* type — `v9_signature_verdict`
  exempts only `BRIDGE_LOCK`/`BRIDGE_RELEASE`/`BRIDGE_REFUND`
  (`V9_UNSIGNED_ALLOWED_TX_TYPES`), so at v9+ an *unsigned* withdraw is
  rejected (`missing_signature`) while the CLI's signed one passes
  `verify_transaction_signature`. The unsigned-exempt trio are the
  bridge-service-emitted types — the withdraw deliberately is not one.
- **Apply**: validates `payload.eth_address` (canonical 0x) and
  `value > 0`, debits AIT + fee, bumps sender nonce. ETH release is
  off-chain.
- **BNT-2 impact: none.** BNT-2 retired the unsigned *protocol-emission*
  surfaces (`queue_protocol_transfer` RPCs: staking/bounty/HTLC/
  AUTO_STAKE → HTTP 410). `BRIDGE_WITHDRAW` is never emitted there — it
  arrives signed from `aitbc wallet bridge withdraw` /
  `eth_bridge_withdraw_submit`.
- Pinned by tests: `apps/blockchain-node/tests/
  test_bridge_withdraw_state.py` (signed validation/burn/nonce, unsigned
  and malformed rejections) and `tests/unit/test_v9_type_coverage_
  replay.py` (BRIDGE_WITHDRAW in the replay set). Those are the deciding
  tests if this finding is ever doubted.

## Scenario C — escrowed AIT→ETH sell (ETH-10 phase 1)

> Gated behind `SELL_ESCROW_ENABLED=true` on the hub (default off) plus
> the escrow key slot (`SELL_ESCROW_WALLET_PATH` +
> `SELL_ESCROW_CREDENTIAL_FILE`), `AIT_SELL_ESCROW`, and
> `SELL_TREASURY_ADDRESS` in `/etc/aitbc/exchange.env` — see
> [docs/ops/sell-escrow-runbook.md](../ops/sell-escrow-runbook.md). The
> shop side runs on node2; the
> shop's wallet key never leaves node2.

### C.1 Happy path — quote, lock 10 AIT, release, settle

```bash
# on node2 — quote hits the hub wallet service over HTTP
aitbc wallet bridge sell quote --amount 10 \
  --eth-address <node2-sepolia-addr> --hub-url http://<hub>:8108
# → quote_id sellq_…, eth_amount, expires_at (+15 min), escrow_address

# on node2 — lock signs TRANSFER→AIT_SELL_ESCROW locally (node2's own
# wallet key) and submits to node2's own chain RPC
aitbc wallet bridge sell lock --quote-id sellq_… --wallet-name <shop>

# status until settled — locked → released → settled
aitbc wallet bridge sell status --id sellq_… --hub-url http://<hub>:8108
```

Expected ledger trace on hub (`bridge_deposits.db`, read-only inspection):

- `bridge_sell_quotes` row: `quoted` → `locked` (or `expired`+requote).
- `bridge_sell_locks` row: `locked` → `releasing` (nonce+hash persisted
  pre-broadcast) → `released` (ETH tx hash) → `settling` → `settled`
  (`settle_tx_hash` = escrow→treasury TRANSFER on the AIT chain).
- Sepolia: one `out` on the bridge wallet (`amount` = quote's
  `eth_amount`, ≤ `SELL_MAX_ETH_PER_TX`).

### C.2 Forced failure — stale quote parks, deadline refunds

```bash
aitbc wallet bridge sell quote --amount 10 --eth-address <addr> --hub-url …
# wait past SELL_QUOTE_EXPIRY_SECONDS (900 s), then lock anyway:
aitbc wallet bridge sell lock --quote-id sellq_… --wallet-name <shop>
```

- Feed healthy: the expired quote re-quotes at the live rate
  (`requoted=1` on the lock row) and releases — expiry alone never traps
  funds.
- Feed stale (older than `BRIDGE_PRICE_MAX_AGE`): the row parks
  `stale_price` while still escrowed; on feed recovery it releases, and
  if `SELL_RELEASE_DEADLINE` (1 h) passes first, the escrow→shop refund
  fires — expect `status=refunded` with `refund_tx_hash`.

Verify with `aitbc wallet bridge sell status --id …` or
`GET /v1/bridge/sell/list` on the hub wallet service.

## Scenario D — signed exchange orders (ETH-11 phase 2)

> Hub-side order book with real node identities. Orders are **unfunded**
> — placing one moves no funds, a match books a `trades` row, and nothing
> settles on-chain (funded settlement is phase 3 / ETH-16). The point of
> the play: signatures, the exchange-scoped nonce, the registry, and the
> cancel path all work end-to-end against the live hub.
>
> Prerequisites: the hub exchange runs `EXCHANGE_REQUIRE_SIGNED_ORDERS`
> (default on); the hub operator has seeded `node_registry` labels from
> the fleet wallet table. Signing happens **on each node with its own
> wallet** — `aitbc exchange …` resolves `exchange_service_url` from
> `HUB_EXCHANGE_URL`/`HUB_DISCOVERY_URL` in `/etc/aitbc/*.env` (or pass
> `--exchange-url http://<hub>:8106`).

```bash
# on node2 — claim the seeded registry row (signs exchange_register locally)
aitbc exchange node register --wallet <node2-wallet> --password-file ~/.aitbc-wallet-pw

# on node2 — sell offer: signed envelope, exchange-scoped nonce from the hub
aitbc exchange order place --side SELL --amount 10 --price 0.000083 \
    --wallet <node2-wallet> --password-file ~/.aitbc-wallet-pw

# on node0 — the same, buy side; the two orders cross on the hub book
aitbc exchange node register --wallet <node0-wallet> --password-file ~/.aitbc-wallet-pw
aitbc exchange order place --side BUY --amount 4 --price 0.000083 \
    --wallet <node0-wallet> --password-file ~/.aitbc-wallet-pw
```

Verify (any host, read-only):

```bash
aitbc exchange order my --wallet <node2-wallet>   # own orders + next nonce
curl -s http://<hub>:8106/api/exchange/nodes      # registered-node board
curl -s http://<hub>:8106/api/orders/orderbook    # remaining sell depth: 6 AIT
curl -s http://<hub>:8106/api/trades/recent       # tape row names buyer+seller labels
```

Expected: the buy fills against the sell — `trades` carries
`buyer_address`/`seller_address`/`fee_ait`, node2's sell shows
`remaining=6` (`filled=4`), and `order my` reports the advanced
`next_nonce`. Nothing on Sepolia or the AIT chain changes — the book is
display-only by design this phase.

### D.2 — cancel and replay behaviour

```bash
# cancel the open remainder; the signed cancel races any fill under the
# same SQLite write lock — loser gets a deterministic 409
aitbc exchange order cancel <order-id> --wallet <node2-wallet> --password-file ~/.aitbc-wallet-pw
```

Re-submitting the *same* place command after a crash returns the recorded
order (the `(address, envelope_hash)` dedupe), while a *different* order
reusing a consumed nonce is 409 — that is the replay guard, not a bug.

## Gaps — steps with no CLI/MCP command

| # | gap | current path |
|---|---|---|
| 1 | `POST /v1/bridge/deposit` on node0/node1 503s — their `exchange.env` lacks `ETH_WALLET_ADDRESS`, and hub's daemon is `127.0.0.1:8108` only with no node→hub route or ssh path. The fix is an env append + `aitbc-wallet` restart on the node (A2.1) — an operator change — or the manual send (A2.2). | operator env change or manual |
| 2 | No CLI/MCP command sends an ETH tx crediting an AIT address **other than the sender's** — `wallet bridge deposit` hard-binds recipient = signing wallet. A deposit for someone else's AIT address needs a hand-built ETH tx (`data = 0x` + utf8-hex of the recipient). | manual ETH send |
| 3 | No CLI/MCP deposit-status tool — only withdraw status exists (`bridge status`, `get_eth_bridge_withdrawal`). Deposit verification is `bridge_monitor.admin status <eth_tx_hash>` on hub or `GET /v1/bridge/deposit/by-recipient/<addr>` on a wallet service. | ssh/curl |
| 4 | `aitbc wallet bridge status` reads the **local** wallet db — withdraw rows exist only on hub; remote hosts cannot reach its loopback daemon, so status checks go through `ssh hub` or MCP `host=`/`role=hub`. | ssh/MCP |
| 5 | Faucet funding and any bridge-wallet refund send have no command — operator wallet/browser actions by design. | manual |
| 6 | `sepolia_balance.py` reports `latest`-only; a pending-vs-sealed nonce gap (stuck outbound tx detector) is a possible follow-up flag. | — |
