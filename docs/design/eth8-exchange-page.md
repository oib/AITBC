# ETH-8 — Hub trade exchange page (design, Sepolia only)

Date: 2026-10-13 · revised 2026-10-14 (ETH-14/ETH-15 settlement reality,
phase-1 shipped, open decisions listed) · Status: **design — phase 1
(display) shipped; phases 2–3 unimplemented** ·
Network: Sepolia (chainId 11155111) exclusively until the v1 switch.
Builds on [eth7-escrowed-sell-flow.md](eth7-escrowed-sell-flow.md) —
settlement, escrow, quote and failure semantics are **not redesigned
here**, only mapped onto trades.

The hub website should work like a stock exchange: a visitor sees who
wants to buy or sell AIT for ETH, at which price and size, and the
recent trades. Today `exchange.html` shows only the spot price —
yet the backend already serves the order book
(`GET /api/orders/orderbook`, `handlers/__init__.py:29`) and recent
trades (`GET /api/trades/recent`, `:27`). The gap is almost entirely
upstream of the page: orders are unsigned, unfunded, and never settle.

## Recommendation (first)

**Three phases, strictly ordered:**

1. **Read-only public page** — render the book, tape and spread from
   endpoints that already exist. No order-placement changes, no
   settlement. Marks every order visibly as `unfunded — display only`.
   **Shipped** as ETH-11 phase 1 (`a22794e63`, via nginx-gated
   `/exchange-api/orderbook` + `/exchange-api/trades`); zero consensus
   adjacency.
2. **Signed orders** — orders carry a wallet signature over a canonical
   envelope; placement verifies it before `BEGIN IMMEDIATE`. Registered
   nodes only (the fleet wallet registry). Still database-only — no
   funds move — but identity is now real.
3. **Funded settlement** — sell orders lock AIT through the ETH-7
   keyed escrow (`AIT_SELL_ESCROW`); buy orders are backed by prepaid
   ETH at the bridge wallet. A match becomes a settlement request in
   the ETH-7 state machine. Waits until the 46,100 activation has
   settled and ETH-2 (live withdraw run) has proven the release path.
   The release path itself changed shape under ETH-14 — receipt-gated
   completion with estimated gas, not broadcast-equals-sent (§7).

Price rule: **±10 % band around the Chainlink-derived rate**, width a
config value (`EXCHANGE_PRICE_BAND_PCT`, default 0.10). Traders:
**registered nodes only**, shown as `node-name (0x1234…abcd)`. Both
DECIDED 14 Oct 2026 — see "Operator decisions needed".

## 1. Identity and signing

- **Envelope**: `{side, pair:"AIT/ETH", amount_ticks, price_ticks,
  expiry_height, account_nonce, chain_id:"ait-localnet"}` — canonical
  JSON (sorted keys, compact separators), the exact encoding the
  refund path already uses
  (`bridge_withdraw_monitor.py:345`).
- **Signer**: the node's registered AIT wallet key — the same wallet
  the node uses for chain transactions, never a new key.
- **Verify**: `verify_transaction_signature`
  (`aitbc_chain/rpc/utils.py:151`) against the claimed
  `user_address` before the insert; reject any signature that recovers
  to a different address — today `user_address` is a free-text field
  anyone can type (`handlers/exchange.py:133-178` — the whole "anyone
  can order in anyone's name" hole).
- **Replay protection**: `account_nonce` must equal the wallet's
  current exchange-scoped nonce — a per-address counter column
  (`order_nonces` table), not the chain nonce (an order is not a chain
  tx); plus `expiry_height` so stale envelopes die on their own.
  UNIQUE constraint on `(user_address, envelope_hash)` makes a
  byte-identical resubmit a no-op.
- **Available today**: this is application-layer verification of an
  ordinary wallet signature — same primitive every signed tx already
  uses. No new tx type is admitted; **no consensus change**. A future
  `EXCHANGE_ORDER` chain-recorded type is post-settle.

## 2. Funding — unfunded orders never reach the book

- **Sell order (AIT → ETH)**: requires a confirmed lock `TRANSFER`
  node → `AIT_SELL_ESCROW` with `payload.sell_quote=<order_id>` — the
  ETH-7 lock mechanism verbatim (§3 there: open signed type, no
  consensus change). The order appears as `funded` once the lock
  confirms; `remaining` can never exceed the locked amount.
- **Buy order (ETH → AIT)**: backed by a **prepaid ETH balance**
  tracked per node on hub — the node sends Sepolia ETH to the bridge
  wallet with `data = "EXCHANGE_DEPOSIT:<node>"` (visible as a
  `FUNDING`-class inflow, distinct from AIT deposits so it is never
  mistaken for an ETH→AIT deposit). Cost = `amount × price` at the
  order's own price — debited from the prepaid ledger at placement,
  refunded on cancel/expiry, consumed at settlement. The bridge
  wallet's ETH is a float, not a per-user account: the prepaid table
  is the accounting layer, exactly like `bridge_sell_quotes` in ETH-7.
- **Unfunded orders cannot reach the book**: placement without backing
  returns the order as `unfunded` with the funding instructions; it
  never enters the matchable set. The page shows `unfunded` orders in
  a separate greyed lane so the book's displayed depth is real.
- **Backing failed/expired**: lock or prepaid balance that lapses →
  order state `backing_expired`, still visible (never silently
  dropped), unmatchable.

## 3. Price rule — band around the oracle

Recommended: **±10 % band** (`EXCHANGE_PRICE_BAND_PCT`, config).

| | free market | band (recommended) |
|---|---|---|
| price discovery | real | bounded — a fat-finger can't print a 10× tick |
| oracle dependence | none | feed outage → book freezes new placements (orders already resting stay visible, new placements 503 like the quote endpoint) |
| manipulation surface | spoofed prints move the displayed "price" | the band makes a fake print cheap to spot and bounded in damage |
| testnet realism | closer to a real exchange | closer to the bridge's actual economics |

The band moves with the feed; orders outside it are rejected at
placement and flagged `out_of_band` (not cancelled) if a later feed
move leaves them outside. Width is config — 10 % is a starting
default on an illiquid testnet.

## 4. Who may trade — registered nodes

- **Registration**: a node claims a display name + its fleet AIT
  address by signing a registration envelope (same scheme as §1) —
  `node_registry` table: `address, label, registered_tx, status`.
  Bootstrap set = the five fleet wallets + bridge labels already
  published in `docs/ops/node-sepolia-wallets.md` /
  `DEFAULT_WALLETS` (`commands/eth.py`) — the label table is already
  the single source of truth.
- **Display**: `node2 (0xCf17…74C1)` — label + short address, never
  the bare address alone, so the page reads like a participants board.
- Non-registered signatures are rejected at placement; anonymous
  visitors can still *read* everything (it's a testnet board).

## 5. Pairs and units — AIT/ETH only

- **Price unit**: **ETH per AIT** (`price` = ETH for 1 AIT) — matches
  the natural "how much ETH is one AIT" reading and the oracle
  (`eth_ait_rate_usd` exists in `price_api.py:265`).
- **Ticks**: reuse the existing `amount_ticks`/`price_ticks` 8-decimal
  integer columns (`db.py:126-127`) — comparisons and ORDER BY already
  run on integers. `amount` in whole+8dp AIT units; `price` max 8dp
  ETH-per-AIT.
- **Minimum order**: `EXCHANGE_MIN_ORDER` (suggest 1 AIT) —
  dust orders would only pollute the tape on a test board.
- **Rounding**: `total = amount × price` may carry >8 dp legitimately
  (`handlers/exchange.py:169`) — keep the existing convention:
  total stays a TEXT Decimal, only amount/price are tick-constrained.
  All money as `Decimal`/integer ticks — never float (repo rule).

## 6. Matching

- **Priority**: price–time, exactly as `_match_orders_in_txn` already
  does (best price first, `id ASC` tiebreak — `:566-580`).
- **Partial fills**: already correct (`trade_qty = min(remainings)`).
- **Self-match prevention**: add `AND user_address != ?` to the match
  query — today `user_address` is selected but never compared, so a
  node can fill its own order and print fake tape.
- **Expiry**: `expiry_height` column; unfillable expired orders flip
  `expired` at match scan (lazily — no sweeper needed in phase 2) or
  via the same 30 s poll the bridge monitor pattern uses in phase 3.
- **Cancel**: `DELETE`-equivalent endpoint
  `POST /api/orders/<id>/cancel` signed like placement; races a fill
  inside the same `BEGIN IMMEDIATE` — whichever holds the write lock
  wins, loser gets a deterministic 409 (`cancel` on a filled order,
  or fill on a cancelled one — no phantom fills).
- **Stays in one SQLite transaction**: insert + match under
  `BEGIN IMMEDIATE` (`:220`) is already the correct serialization for
  a single-writer book — keep it.
- **Match found, settlement fails**: the `trades` row and the order
  updates commit together (the match is durable — tape integrity),
  and the trade carries `settlement_state` starting at `locked`
  (ETH-7 machine). A failed settlement leaves the *trade* visible
  and its settlement row in `failed` — the tape never lies about what
  matched; the escrow state machine owns recovery.

## 7. Settlement — mapped onto ETH-7

Every trade = one settlement request:

| trade event | ETH-7 state |
|---|---|
| match commits | `locked` (sell leg already escrowed; buy leg already prepaid) |
| hub broadcasts the ETH send to seller | `releasing` — `eth_tx_hash` + nonce persisted *with the intent*, at broadcast (the ETH-7 duplicate-release fix applies verbatim) |
| release receipt verifies | `released` — written **only** on a status-1 receipt at `BRIDGE_RELEASE_CONFIRMATIONS` depth; since ETH-14 the broadcast echo is never payment proof, and the monitor's per-poll check owns the flip |
| escrow sweep sell-AIT → buyer's AIT address | `settled` (escrow → buyer, not treasury — the *buyer* receives the AIT) |
| ETH leg **provably** failed | `refunded` — escrow → seller, prepaid ETH → buyer's balance restored |
| ETH leg unverifiable | `needs_review` / `needs_review_release` — parked for the operator, **never auto-refunded** (ETH-14/14b) |
| refund itself fails | `failed` + operator write-off — identical to ETH-7 |

**Release mechanics (post-ETH-14, 14 Oct — `9341661aa`/`8bdf20362`)** —
this updates the "hub sends ETH to seller" step above:

- **Receipt-gated completion**: a broadcast release sits `releasing`
  and is re-verified every poll; `released`/`completed` is written only
  on a status-1 receipt at `BRIDGE_RELEASE_CONFIRMATIONS` depth. A
  status-0 receipt proves `not_sent`; an absence-only view (no
  receipt, no tx, nonce not pending) younger than
  `ETH_RELEASE_ABSENCE_GRACE_SECONDS` (default 600) reads `unknown` —
  never a refund trigger (ETH-14b).
- **Estimated gas, not a constant**: `eth_estimateGas(from,to,value)`
  × `ETH_WITHDRAW_GAS_MARGIN` (default 1.25), floor 21 000, hard cap
  `ETH_WITHDRAW_GAS_MAX` (default 300 000). Post-Glamsterdam a send to
  a previously unseen account estimates at ~207 k gas — the static
  100 000 limit that caused the ETH-14 incident deterministically
  reverts, and an estimate error or over-cap result raises before
  signing. `ETH_WITHDRAW_GAS` survives only as an explicit override.
- **Recovery is operator-gated**: a proven-reverted release is retried
  via `withdraw_admin release-retry` (dry-run default, two-RPC proof,
  exact recorded amount — never re-quoted) or parked
  `needs_review_release` for `mark-review` → refund. Runbook:
  `docs/ops/withdraw-release-runbook.md`.

Nothing in this design pinned a fixed gas limit — the 100 000
assumption lived in the release implementation and is gone. What the
pre-revision text *did* assume was broadcast-equals-release ("hub sends
ETH to seller → `released`"): corrected above. The two design steps
that depend on the new mechanics are the **ETH leg of settlement**
(`releasing` → verified `released` → `settled`) and the **refund leg**
(only on a *proven* failure; an unverifiable outcome parks for the
operator rather than auto-refunding — so a slow or lagging RPC can no
longer refund an in-flight release). The same rules already apply to
the ETH-7 sell-escrow releases this design reuses.

The escrow sweep in a trade goes escrow → *buyer* (ETH-7 settles to
treasury because the hub was the counterparty; here the buyer is) —
the only semantic difference, one line in the settle target.

**Fee**: `apply_bridge_fee` already computes a fee on the withdraw
path (`price_api.py:203`); reuse its shape. Recommendation: `EXCHANGE_FEE_PCT`
(default 0 on testnet, knob present) charged on the **AIT leg to the
seller**, swept to the same treasury address the settle leg uses —
one fee path, one place in the ledger. Open decision — see below.

## 8. The public page

Existing (verify-then-reuse): `GET /api/orders/orderbook`,
`GET /api/trades/recent`, `GET /exchange/price.json`,
`GET /v1/exchange/history`.

Needed additions:

| endpoint | serves | cache / limit |
|---|---|---|
| `GET /api/orders/orderbook` (extend) | bid/ask ladder rows + per-level depth sums | 10 s edge cache, 60 req/min/IP |
| `GET /api/trades/recent` (extend) | tape rows incl. buyer/seller node labels | 10 s, 60/min |
| `GET /api/exchange/depth` new | aggregated ±band depth buckets for the depth chart | 30 s, 30/min |
| `GET /api/exchange/ohlc` new | 24 h candles from `trades` | 60 s, 30/min |
| `GET /api/exchange/stats` new | last price, 24 h vol, spread, open-order counts | 10 s, 60/min |
| `GET /api/exchange/nodes` new | registered node labels (no addresses beyond short form) | 5 min, 30/min |
| `GET /api/exchange/my-orders?addr=` | open orders for one wallet — read-only by address, no auth needed (public testnet board) | 10 s, 60/min |

All GETs read-only; cache headers + per-IP rate limits at the
handler layer (no new dependency — the existing handler class can
carry a small token-bucket dict).

**Layout (text mockup, phone-first single column → two columns ≥900 px):**

```
┌──────────────────────────────────────────────┐
│ ⚠ SEPOLIA TESTNET — not real value           │  sticky banner
│ AIT/ETH   last 0.0000105   24h +2.1%         │
│ spread 0.0000008 (7.6%)   vol 24h 412 AIT    │
├───────────────┬──────────────────────────────┤
│ BIDS (ETH)    │ ASKS (ETH)                   │
│  0.0000102 40 │ 0.0000110 25   node2         │
│  0.0000101 15 │ 0.0000115 60   node0  ← size │
│  0.0000100 90 │ 0.0000120 10   hub1    +node │
│ [====depth bars behind each row====]         │
├──────────────────────────────────────────────┤
│ RECENT TRADES          price · size · when   │
│ 0.0000105 · 10 AIT · 14:02 · node0←node2     │
│ 0.0000104 ·  5 AIT · 13:47 · node1←node2     │
├──────────────────────────────────────────────┤
│ 24h chart (sparkline, candles on ≥900px)     │
├──────────────────────────────────────────────┤
│ MY ORDERS  [addr input → ?addr=]             │
│ open 2: sell 10 @0.0000110 · buy 5 @0.0000102│
│ open orders per node: node2 4 · node0 2 …    │
└──────────────────────────────────────────────┘
```

Static HTML + tiny fetch JS like the current page — no framework, no
build step (the page already works that way). Banner is a persistent
sticky element, not a dismissible toast.

## 9. Abuse limits

| abuse | rule |
|---|---|
| order rate | `EXCHANGE_MAX_ORDERS_PER_MIN` per address (suggest 20) + per IP |
| open orders | `EXCHANGE_MAX_OPEN_PER_NODE` (suggest 50) — placement over the cap rejects the *new* order, never evicts the old |
| min size | `EXCHANGE_MIN_ORDER` — dust spam |
| spoofing | signature + funding make an unfunded fake book impossible; a cancel-rate > `EXCHANGE_CANCEL_RATIO` (say 90 % of placements in a window) flags the node `watchlisted` on the page |
| wash trading | self-match is prevented outright (§6); matched-pair reporting (same two nodes trading round-trips) is a stats column, not hidden — on a named board it outs itself |
| book size | `EXCHANGE_MAX_BOOK_ROWS` (suggest 5000 open); oldest-expired evictions are logged |
| endpoint DoS | all reads cached (§8); the POST surface is signature-verified before any DB write — unsigned garbage costs a 401, not a transaction |

## 10. Reconciliation

- **ETH-6** (`aitbc eth transfers`): every settled trade shows the
  seller's escrow lock (`in` on the escrow label once it's added to
  `DEFAULT_WALLETS`), the ETH release (`out` on `bridge`), and buy-side
  prepayments (`in` on `bridge` from the node's address). `net=bal`
  stays the tripwire.
- **B13 `bridge_outbound`**: sell-settlement sweeps classify by
  `to_address ∈ depositors → refund` today — as ETH-4 showed, that's
  honest but lossy; the trade-settlement legs deserve a dedicated
  `exchange_settle` kind alongside the `sell_release`/`opening_balance`/
  `operator_transfer` kinds already proposed. Until then they read as
  `unidentified` — which is *correct*: a B13 row can't be proven
  without the trade id, so the trades row carries
  `settlement_eth_tx_hash`/`settlement_ait_tx_hash` for the join.
- Prepaid-ETH deposits get the `EXCHANGE_DEPOSIT:<node>` data tag so
  the deposit monitor treats them as funding-class inflows, never as
  ETH→AIT deposits — keep them out of `eth_deposits`' payout path by
  registering them as a funding class (needs a small monitor change,
  flagged in §13).

## 11. Failure matrix

| failure | behaviour |
|---|---|
| hub crash mid-match | `BEGIN IMMEDIATE` atomicity: the trade + order updates either committed or didn't; on restart the book is exactly the committed state. |
| match committed, settlement fails | trade stays on the tape (the match *happened*); its settlement row retries/refunds per ETH-7 — tape integrity and settlement integrity are separate concerns. |
| stale price feed | placements 503 (`BRIDGE_PRICE_MAX_AGE` gate from ETH-7); the book stays readable, new-band checks just refuse. |
| bridge float short | sell releases queue `insufficient_reserve` (existing status); page shows the settlement as queued, not lost. |
| duplicate signed order | `(user_address, envelope_hash)` UNIQUE → idempotent reject. |
| cancel races a fill | same write lock decides — 409 to the loser, deterministic. |
| DB restore after crash | book/orders/trades are the SQLite file; escrow locks + prepaid balances are re-derivable from chain + explorer — a rebuild pass like SD-1's rebuild tool re-checks the DB against chain state before the book reopens (design: `exchange_verify.py` read-only checker). |
| reorg on Sepolia | ETH-7's receipt re-verification on `released` rows covers the settlement leg. |

## 12. Test plan

- **Unit**: signature envelope verify/reject (wrong signer, replay,
  expired height); unfunded order refusal; self-match prevention;
  cancel-fill race under `BEGIN IMMEDIATE`; tick-exact matching;
  band rejection; prepaid-balance debit/refund math; a release
  broadcast that reverts on-chain → settlement row stays
  `releasing`/`needs_review`, never `released`, and refunds only on
  proven `not_sent` (ETH-14 semantics).
- **Two-node Sepolia scenario** (node2 sells, node0 buys): register →
  node0 prepays ETH → node2 locks 10 AIT → place crossing orders →
  match → settle → verify with `aitbc eth transfers` (escrow `in`,
  bridge `out`, node `in`/`out`) + `sepolia_balance.py` `net=bal yes`
  + ledger rows.
- **Abort conditions**: any `net=bal NO`; a trade whose settlement
  row exceeds its ETH-7 deadline; two `trades` rows sharing a
  settlement hash; escrow/prepaid balances disagreeing with the DB
  rebuild check; nonce-mismatch warning in the ETH-6 log.

## 13. Per-file change list (sized) + rollout

| file | Δ | phase |
|---|---|---|
| `website/exchange.html` | ~200 new | 1 — ladder, tape, spread, nodes, my-orders, banner (fetch-only, no backend) |
| `apps/exchange/simple_exchange/handlers/exchange.py` | +250 | 2 — signature verify, self-match guard, expiry, cancel endpoint; +150 in 3 — funding gates |
| `apps/exchange/simple_exchange/db.py` | +90 | 2 — `node_registry`, `order_nonces`, `prepaid_eth`, order columns (signature, envelope_hash, expiry, funded_state); +40 in 3 — `trades.settlement_*` |
| `apps/exchange/simple_exchange/handlers/__init__.py` | +30 | 1/2 — new GET routes + POST cancel |
| `apps/wallet/…/bridge/` (ETH-7 monitor) | +60 | 3 — settle target override (escrow → buyer) + `EXCHANGE_DEPOSIT` funding class |
| `cli/aitbc_cli/commands/` (`exchange` or `eth`) | +120 | 2 — `aitbc exchange order place/cancel/my` signing client |
| `scripts/ops/exchange_verify.py` | ~120 new | 3 — SD-1-style rebuild/check tool |
| docs + scenario 59 addendum | +80 | each phase |

**Post-settle (after 46,100 + ETH-2)**: phase 3 settlement itself is
already ETH-7-phase-1 tech (keyed escrow — no consensus wait); what
*does* wait for post-settle is the keyless-escrow upgrade and any
chain-recorded `EXCHANGE_ORDER` type. The funding-monitor change for
prepaid deposits can ship with phase 2 (it only *adds* a funding
class — no existing behavior changes).

**Rollout**: phase 1 is pure display — **live** since ETH-11 phase 1
(`a22794e63`); phase 2 (signed orders, still unfunded/settlement-free)
hardens identity without touching value; phase 3 wires funding and
settlement once ETH-7 phase 1 + ETH-2 have run. Each phase is
independently revertible (page revert = static file; signature
enforcement = env flag; settlement = monitor flag).

## Sovereignty check (operator rule, 13 Oct)

Every node is wallet-sovereign: no host may hold, receive, use, sign
for, or read another node's wallet key, password or keystore, and no
step may need SSH trust between nodes. Per-step key location:

| step | key lives on | signs | only verifies |
|---|---|---|---|
| registration | node | node signs the registration envelope on its own host | hub verifies the signature |
| sell funding (lock) | node | node signs `TRANSFER`→`AIT_SELL_ESCROW` with its own AIT key, on its own host | hub, on-chain (sealed tx + quote/order payload) |
| buy funding (prepay) | node | node signs the Sepolia ETH send to the bridge wallet with its own Sepolia key, on its own host | hub via RPC/explorer receipt |
| order placement | node | node signs the §1 envelope locally (CLI/wallet on its host) | hub verifies the signature before any DB write |
| order cancel | node | node signs the cancel envelope locally | hub verifies, then the write lock resolves the race |
| matching | — | nobody — SQLite rows only | — |
| ETH leg of settlement | hub | hub signs the Sepolia send with its own ETH release key | all parties via explorer |
| AIT leg of settlement | hub | hub signs escrow→buyer sweep with the dedicated escrow key | all parties via chain |
| refund leg | hub | hub signs escrow→seller with the same escrow key | all parties via chain |
| page reads (§8) | — | nobody — public read-only GETs | — |

Rule check against the four violations: none applies.

1. **No node key material crosses a boundary**: the only private keys
   in the design are (a) node keys that never leave their own node —
   AIT wallet for locks/envelopes, Sepolia wallet for prepayment — and
   (b) hub-custodied keys — the bridge payout key, the ETH release
   key, and the dedicated `AIT_SELL_ESCROW` key (see below). No
   password, keystore or wallet file is ever transmitted or read by
   another host.
2. **The hub never signs for a node**: every node-originated value
   movement — lock transfer, prepayment send, order envelope, cancel —
   is signed by the node itself on its own host. The hub signs only
   hub-custodied outputs: escrow sweeps of AIT that shops placed into
   escrow by their own signed transfers, and ETH sends out of the
   hub's own bridge wallet.
3. **No wallet-service or wallet-file access crosses a host**: order
   signatures arrive in the POST body; the exchange verifies them
   against the claimed address. It never calls `aitbc-wallet` on any
   node — signing is strictly client-side on the node. Funding proofs
   come from sealed chain data and the public explorer/RPC, not from
   querying the sender's wallet.
4. **No SSH trust between nodes**: every node↔hub interaction is a
   signed envelope over HTTP plus on-chain data. Nodes never connect
   to each other at all in this flow.

**The escrow key itself (hub custody — DECIDED 13 Oct 2026, decision
below)**: same terms as ETH-7 — a dedicated key whose only
permitted action is sweeping `AIT_SELL_ESCROW`'s balance, exclusively
AIT placed there by nodes' own signed lock transfers, to the buyer
(settle) or back to the seller (refund). It can never move a node
wallet. It is generated and held separately from the bridge payout
key, the ETH release key and the genesis key; the operator creates it
and no agent handles it; ETH-7 §4's per-release and daily caps bound
it; the phase-2 keyless escrow remains the long-term target.

**Prepaid-ETH note**: buy-side ETH prepayments sit in the hub's bridge
wallet — explicitly "its own float" under the rule — with per-node
accounting in the `prepaid_eth` table. The node voluntarily sent the
ETH as prepayment (same class as a bridge deposit); the hub never
needed the node's key to receive it.

## Operator decisions needed

- **Keyed-escrow classification — DECIDED 13 Oct 2026, operator
  reply verbatim: "a".** The dedicated hub-owned `AIT_SELL_ESCROW`
  key satisfies the sovereignty rule as hub custody under the
  conditions in the sovereignty check (moves only shop-locked AIT —
  settle or refund — never a node wallet; separate from the bridge
  payout, ETH release and genesis keys; operator-created, never
  agent-handled; ETH-7 §4 caps apply; phase-2 keyless remains the
  long-term target). Carried identically in the ETH-7 design;
  the strict-reading fallback (locks to the hub's existing treasury
  address, commingled escrowed AIT) is not needed.
- **Price rule — DECIDED 14 Oct 2026, operator reply verbatim:
  "±10% oracle band (rec.)".** ±10 % band around the
  Chainlink-derived rate, width config (`EXCHANGE_PRICE_BAND_PCT`,
  default 0.10) — a fat-finger can't print a 10× tick and a fake print
  is cheap to spot; consequence: a feed outage freezes *new*
  placements (resting orders stay visible, placements 503 like the
  quote endpoint). *Rejected alternative:* free market — real price
  discovery but spoofed prints move the displayed price and the
  manipulation surface is unbounded. (§3.)
- **Who may trade — DECIDED 14 Oct 2026, operator reply verbatim:
  "Registered nodes (rec.)".** Registered nodes only — a
  `node_registry` row (display name + fleet AIT address, signed
  registration envelope) is required to place; consequence: the board
  shows accountable `label (0x1234…abcd)` identities and a new trader
  needs one operator-side registration step. *Rejected alternative:*
  open to any signing address — permissionless but anonymous labels
  can be Sybil'd, and a spoofed "node2" cannot be told apart from the
  real one. Reads stay public either way. (§4.)
- **Fee — DECIDED 14 Oct 2026, operator reply verbatim:
  "AIT leg to seller (rec.)".** `EXCHANGE_FEE_PCT` (default 0 on
  testnet — knob present, off) reusing the `apply_bridge_fee` shape
  (`price_api.py:203`), charged on the **AIT leg to the seller** and
  swept to the same treasury address the settle leg uses; consequence:
  one fee path, one ledger entry, the seller's proceeds are net of
  fee. *Rejected alternative:* buyer-pays fee on the ETH leg — the
  buyer's prepaid debit would become `amount × price × (1+fee)`,
  changing the prepaid-math direction and landing fee income in a
  second currency path. (§7.)
- **Phase order — DECIDED 14 Oct 2026, operator reply verbatim:
  "Phase 2 next (rec.)".** Phase 1 (read-only display) already shipped
  as ETH-11 phase 1 (`a22794e63`). Phase 2 (signed orders +
  registration, still unfunded/settlement-free) ships next; phase 3
  (funded settlement) waits on the 46,100 activation bedding in **and
  a clean ETH-2 live withdraw run** — ETH-14's recovery (14 Oct) was a
  first live withdrawal (ran, reverted on the old fixed-100 000-gas
  assumption, recovered via `withdraw_admin`) but does **not** count
  as ETH-2: the operator wants the release path proven by a clean run,
  not only by a recovery. *Rejected alternatives:* jump straight to
  phase 3 — the signed-identity layer would go untested in the field
  while real funds move; hold phase 2 until phase 3 is ready —
  signature/cancel code paths would sit dark and get no soak time.
  (Rollout, §13.)

## Could not verify (and why)

- **Whether `/api/orders` is publicly reachable today** — route table
  says it exists; whether the hub's nginx exposes it externally
  (vs. loopback) wasn't probed (read-only, no live POST allowed).
  The design assumes placement is reachable or becomes so — phase 2
  keeps the same path.
- **Prepaid-ETH data-tag parsing in the deposit monitor** — the ETH
  `data` field parsing for deposit recipients was verified in ETH-1
  (UTF-8 of the AIT address); whether a non-address `data` tag
  (`EXCHANGE_DEPOSIT:<node>`) cleanly fails into FUNDING-class or
  needs a code path is listed as a §13 change rather than claimed.
- **Trade-row schema evolution** — `trades` today has no
  counterparty columns at all (amount/price/total/created_at only,
  `INSERT` at `handlers/exchange.py:604`); buyer/seller attribution
  needs the columns designed in §13 — flagged, not assumed.
- **Feed freshness behavior under load** — same caveat as ETH-7:
  the Chainlink round cadence wasn't probed live.
- **The exchange service's systemd/user context on hub** — port 8106
  is up and idle per the task, but which unit and env file own it
  wasn't enumerated (not needed to design the change; needed to
  deploy it).

## Evidence pointers (verified while writing)

- unsigned orders: `handlers/exchange.py:133-178` (payload = side,
  amount, price, user_address — no signature anywhere)
- db-only + comment on the retired `/rpc/sendTx`: `:205-212`
- atomic match in one transaction: `:220` (`BEGIN IMMEDIATE`),
  `:532-660` (`_match_orders_in_txn`, price-time, partial fills,
  `INSERT INTO trades` at `:604`)
- tick math: `db.py:126-127` (8dp integer tick columns; comparisons on
  ticks, TEXT for display — lexical-compare bug already fixed and
  commented)
- routes: `handlers/__init__.py:26-36` (`/api/orders/orderbook`,
  `/api/trades/recent`, `/api/wallet/balance`), `:83-87`
  (`/v1/exchange/history`, `/exchange/price.json`), `:93-101`
  (`POST /api/orders`)
- live counts (read-only, mode=ro, nice): `orders` 21 rows
  (2026-07-02 → 2026-08-20), `trades` 6 rows (→ 2026-08-19) at
  `/var/lib/aitbc/data/exchange/exchange.db` on hub
- oracle: `price_api.py:211` (`calculate_eth_amount`), `:265`
  (`eth_ait_rate_usd`), `AIT_USD_FIXED_PRICE=0.28`
- ETH-7 reuse: `docs/design/eth7-escrowed-sell-flow.md` (states,
  quote expiry, keyed-vs-keyless escrow decision, reserve/cap math,
  failure matrix)
