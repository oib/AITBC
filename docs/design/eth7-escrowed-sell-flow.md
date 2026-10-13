# ETH-7 — Escrowed AIT→ETH sell flow (design, Sepolia only)

Date: 2026-10-13 · Status: **design only — nothing implemented** ·
Network: Sepolia (chainId 11155111) exclusively until the v1 switch.

The shop (node2) holds earned AIT and wants ETH. Counterparties do not
trust the shop; they do trust the hub. Today `BRIDGE_WITHDRAW` **burns**
the shop's AIT at seal
(`state/state_transition.py:1897` — debit `value + fee`, `0x0`
recipient never credited) and the hub releases ETH *afterwards*. If the
release fails, a second hot key (genesis/funding wallet) has to refund
from a different balance. The escrow design replaces the irreversible
burn with a **visible, reversible lock**: AIT sits in a published
escrow address while the ETH leg is in flight, and returns to the shop
on failure or timeout.

## Recommendation (first, per scope)

**Phase 1 — build it today, zero consensus change.** A dedicated
**keyed** escrow address `AIT_SELL_ESCROW` whose AIT key lives in hub
custody (ops-signer slot, not the genesis key and not the bridge payout
key). The lock is an ordinary signed `TRANSFER` shop → escrow — an
open user type at every current protocol version
(`admission_authority.py:49`, payload-carrying — the existing refund
path already sets `payload.reason`). A hub-side *sell monitor* (new
module beside `bridge_withdraw_monitor.py`) watches inbound locks,
quotes-then-releases ETH through the existing `_send_eth` path, and
signs the escrow leg's settle/refund `TRANSFER` itself. Every step is
either an existing tx type or a service action.

**Phase 2 — post-settle (after the 46,100 activation has bedded in).**
Move to a *keyless* protocol escrow `aitbc.bridge.sell.escrow`
(`protocol_escrow.py` pattern — no private key exists, so release
cannot be forged via `/rpc/transaction`) with a node-internal
origination path for the release/refund leg. That origination is
consensus-adjacent and is **marked post-settle** throughout; BNT-2
retired the open `queue_protocol_transfer` surface that used to let
services originate such transfers, so a keyless escrow cannot be
released by any RPC today.

Buyer-facing escrowed purchases (a buyer sends ETH to the bridge wallet
and the hub releases the shop's *locked* AIT to the buyer) are **phase
2 / later** — see §7; they reuse the same lock state machine but add a
buyer-binding leg this design deliberately does not spec yet.

## 1. State machine

States: `quoted → locked → released → settled`, with `refunded` and
`failed` as terminal escapes.

| transition | trigger | persisted | third-party-visible proof |
|---|---|---|---|
| `quoted` | shop calls `POST /v1/bridge/sell/quote` | quote row: id, shop AIT addr, ETH addr, `ait_amount`, `rate_usd`, `fee_ait`, `eth_amount`, `expires_at`, price-feed block/time | quote JSON (signed receipt string is enough — hash of row + hub MAC or ed25519 signature) |
| `locked` | shop's signed `TRANSFER` seals on-chain to `AIT_SELL_ESCROW` with `payload.sell_quote=<id>` | lock row: `ait_tx_hash` (UNIQUE), sender, amount, quote_id, lock height | the on-chain transfer — anyone can show the escrow balance grew |
| `released` | monitor sends ETH (existing `_send_eth`), receipt confirmed `BRIDGE_CONFIRMATIONS` deep | `eth_tx_hash`, `released_at`, gas cost | Sepolia tx from the bridge wallet to the shop's ETH address |
| `settled` | monitor signs escrow → hub-treasury `TRANSFER` (the AIT leg completes: shop sold it) | settle tx hash, `completed_at` | escrow → treasury transfer on the AIT chain |
| `refunded` | release fails, quote expires unclaimed, or deadline passes without ETH send | `refund_tx_hash`, reason, `refunded_at` | escrow → shop transfer on the AIT chain |
| `failed` | refund itself fails, or a row needs operator write-off | `error`, `failed_at`, admin notes | ledger row via `wallet bridge sell status` |

`locked → released` is the only transition that spends ETH;
`released → settled` is bookkeeping on the AIT side and can never be
reordered before `released` (the escrow sweep requires a confirmed
`eth_tx_hash`).

## 2. Quote

- `POST /v1/bridge/sell/quote {ait_amount, eth_address}` → returns
  `{quote_id, rate, fee_ait, eth_amount, expires_at}` computed from the
  Chainlink Sepolia ETH/USD feed + `AIT_USD_FIXED_PRICE=0.28`
  (`price_api.py:139`), stored on the row.
- **Expiry: 15 minutes.** The shop must get its lock tx *broadcast*
  inside the window; the monitor accepts a lock for an expired quote
  only at the current re-quoted rate (which it re-computes and records
  — the shop sees `requoted: true` on the status row).
- **Locked into the quote**: rate (ETH/USD price at quote time), fee,
  computed `eth_amount`. What is NOT locked: Sepolia gas (paid by the
  bridge wallet, priced at send time).
- **Stale feed**: if `updatedAt` on the Chainlink round is older than
  `BRIDGE_PRICE_MAX_AGE` (new env, default 2 h on Sepolia) the quote
  endpoint 503s rather than pricing off a dead feed; the monitor
  re-checks feed freshness at release time and parks the row
  `stale_price` (a pending sub-status, still escrowed) rather than
  releasing at a quote whose basis went stale.

## 3. Lock mechanism — comparison

| | (a) keyed escrow `TRANSFER` | (b) current `BRIDGE_WITHDRAW` burn | (c) keyless protocol escrow |
|---|---|---|---|
| tx type | `TRANSFER` (open, signed) | `BRIDGE_WITHDRAW` (open, signed — `v9_policy` requires a top-level sig) | `TRANSFER` lock; release needs **node-internal origination** |
| signed user type today | yes | yes | lock yes — **release no** (BNT-2 retired the origination RPC) |
| consensus change | none | none | yes — a release-origination path in the node; **post-settle** |
| reversibility | full — refund is escrow → shop | none — burn is final; refund needs a *second* funding source + second hot key | full, once the release path exists |
| counterparty visibility | escrow balance on-chain | none — burn is one-way | best — keyless, cannot be signed away |
| hot keys on hub | escrow key + release key | release key + genesis refund key | release key only |

**Recommendation: (a) now, (c) post-settle.** (a) delivers the trust
property — the lock is visible and reversible — with only service-side
code. (b) stays as the legacy path behind `BRIDGE_WITHDRAW` for
compat; the doc's recommendation is to route new sells through the
escrow and leave `BRIDGE_WITHDRAW` enabled-but-discouraged until (c)
ships.

Lock binding detail: `payload.sell_quote = <quote_id>` on the lock
`TRANSFER` identifies the quote. Rows without a matching live quote
are auto-refunded after `SELL_LOCK_ORPHAN_BLOCKS` — no silent holds.

## 4. Float and caps

- **Per-release cap**: `SELL_MAX_ETH_PER_TX` (new env; suggested 0.01
  ETH ≈ 20% of the 0.05 float) AND `BRIDGE_MAX_PAYOUT_FRACTION`
  (0.5, `main.py:96`) applied to the float — the stricter binds.
- **Daily cap**: `SELL_MAX_ETH_PER_DAY` (new; suggested 0.03 ETH/day) —
  a stolen release key drains at most one window before the ledger
  shows it.
- **Reserve floor**: existing `ETH_WITHDRAW_MIN_RESERVE=0.005` stays;
  `available = balance − pending_reserve` already subtracts in-flight
  rows (`bridge_withdraw_monitor.py:158`). Note a wart:
  `get_pending_withdrawals` counts `failed` rows toward the reserve
  (`bridge_db.py:608`) — a failed row parks float until refunded;
  the new table should exclude `failed` from its pending sum.
- **Queueing**: insufficient float → row sits `insufficient_reserve`
  (existing status) and the monitor retries each poll; the shop sees
  `status: queued_reserve` + the deficit in `sell status`.
- **Float top-up**: an operator send to the bridge wallet from a
  `BRIDGE_FUNDING_SOURCES` address lands as a `FUNDING` ledger row —
  never a deposit, never paid out (AGENTS.md funding rule). Top-ups
  from any other address are treated as deposits and FAIL — keep the
  allowlist current.

## 5. Timeouts

| state | deadline | on expiry |
|---|---|---|
| `quoted` | 15 min | quote row → `expired`; a late lock is re-quoted or refunded |
| `locked` (awaiting release) | `SELL_RELEASE_DEADLINE` — suggested 1 h | monitor refunds escrow → shop, marks `refunded` |
| `released` (awaiting confirmations) | 2 × `BRIDGE_CONFIRMATIONS` + 30 min | re-check receipt; if the ETH tx dropped out, release is *re-attempted once* under a stored nonce-locked envelope (see failure matrix), else `refunded` |
| orphan lock (no quote) | `SELL_LOCK_ORPHAN_BLOCKS` (suggest ~150 blocks) | auto-refund; alert if it repeats (probing) |
| any `failed` | — | operator `write-off` after review; never auto-forgotten |

A lock nobody resolves cannot strand value: the deadline refund is a
monitor action, and if the monitor itself is down the deadline is
evaluated on restart — worst case is a delayed refund, never a lost
one. Escrow balance anomalies (lock without row, row without lock)
emit the same `net=bal` alert channel ETH-6's transfer log surfaces.

## 6. Failure matrix

| failure | behaviour |
|---|---|
| hub crash between lock and ETH release | lock row persists; on restart the monitor re-scans confirmed transfers to the escrow address and resumes `locked` rows. The shop's AIT stays visibly locked — never burned. |
| ETH send succeeds, AIT settle fails | `released` row holds the `eth_tx_hash`; settle is retried idempotently (escrow → treasury transfer re-issued; the settle tx is deduplicated on `sell_id` via a UNIQUE column). |
| ETH send succeeds, DB write fails | **the real duplicate-release risk.** `_release_eth_for_withdrawal` sends ETH *then* updates the row (`bridge_withdraw_monitor.py:278-279`); a crash in between + a re-run today marks `failed` and *refunds on top of the released ETH* — over-delivery. Design rule: **send, then wait for the receipt inside the same step, and persist `eth_tx_hash` + receipt block before any status change**; on recovery, a `locked`/`released` row with a `eth_tx_hash` is verified on-chain first — never re-sent blindly. The new monitor must also gate on `eth_getTransactionByHash` receipt existence before refunding. |
| double submit of the same lock | `ait_tx_hash` UNIQUE on the lock row — second insert is a no-op (`INSERT OR IGNORE`); duplicate polls already skip via `get_withdrawal_by_ait_tx_hash`. |
| refund tx fails | row → `failed` with `error`; retried on a backoff (`next_retry_at` pattern from `eth_deposits`); funds stay escrowed, not burned — refund is always possible later. |
| monitor restarts mid-flight | every state is derivable: `locked` rows rescan the chain, `released` rows re-read their receipt, `settled/refunded` are terminal. `_ensure_db` + UNIQUE keys make replays idempotent. |
| Sepolia reorg > 3 confs | release rows re-verify `eth_getTransactionReceipt` each poll until `settled`; a dropped ETH tx → one re-send under the stored envelope (new signed tx, *same* nonce only if the old one never landed — else fresh nonce) then `refunded` on second failure. The AIT lock row anchors on `block_number` seen at confirmation — a reorged lock is treated as never-locked (auto-unlock path, no ETH sent). |
| RPC down (either side) | poll cycle skips with a logged error; deadlines are evaluated on successful polls, not wall-clock, so an outage cannot trigger a wrongful refund. |

## 7. Buyer-facing variant — later phase

A buyer who does not trust the shop sends ETH to the bridge wallet
(`to == bridge`, `data = quote_id`), the hub confirms the deposit 3
blocks deep, then signs escrow → **buyer's AIT address**. This reuses
`locked → released → settled` verbatim with the beneficiary swapped,
but it needs: buyer-bound quotes (buyer identity ≠ shop), anti-
front-running (the ETH `data` field is public — a quote must bind the
buyer's AIT address *and* the expected sender), and refund rules for
wrong-amount sends. **Out of scope for phase 1** — spec it once the
sell escrow has run live; do not implement before phase 2.

## 8. Reconciliation

- **ETH-6 log** (`aitbc eth transfers`): every leg appears — shop's
  lock is `in` on no watched wallet but `out` on `node2`; the ETH
  release is `out` on `bridge`; top-ups are `in` on `bridge`. The
  `net=bal` column is the tripwire: a release without a row, or a row
  without a release, breaks net=balance immediately.
- **B13 `bridge_outbound`**: releases land as `kind='refund'` if the
  shop's ETH address ever deposited, else `unidentified` — per ETH-4,
  `unidentified` is the honest answer until a dedicated `sell_release`
  kind exists. Add `kind='withdrawal'` mapping for releases to a
  configured operator/escrow set, `kind='opening_balance'` for the
  float carried in (the ETH-4 sweep precedent), and
  `kind='operator_transfer'` for treasury sweeps — the three kinds
  ETH-4 showed the ledger needs.
- The AIT side reconciles through the escrow address itself: locked =
  sum(unsettled locks), settled + refunded = total outflow; any
  escrow-balance residue other than the pending sum is an alert.

## 9. Key custody — options, sized

| option | blast radius on key theft | cost |
|---|---|---|
| caps only (recommended, phase 1) | one release ≤ `SELL_MAX_ETH_PER_TX`; daily ≤ `SELL_MAX_ETH_PER_DAY`; float floor keeps ≥ reserve | env vars + ledger accounting — ships with phase 1 |
| separate release key | ETH release key ≠ escrow key ≠ payout key: stealing any one can't move the others' assets; escrow key on ops-signer (never in a wallet env file) | one more custody slot — already the ops-signer pattern |
| Safe / 2-of-3 release | release needs two signers — removes the single hot key entirely | contract deploy + ops friction; **evaluate at float > 1 ETH**, not before |
| time-delayed releases | releases > X sit in a `queued_delay` state for N blocks — an attacker is visible before value moves | adds latency; pairs well with the Safe |

Phase 1 ships caps + separate keys. The Safe and delay gate are sized
options for when the float is real.

## 10. Test plan

- **Unit** (new `test_sell_escrow_monitor.py`): quote expiry; lock
  without quote → orphan refund; double-submit dedupe on
  `ait_tx_hash`; insufficient-reserve queueing; receipt-verified
  recovery (the duplicate-release case); deadline refund; settle
  idempotency on monitor restart.
- **Sepolia scenario** (extends scenario 59, node2 as shop): quote →
  lock 10 AIT → ETH release → settle; a forced-failure run
  (deliberately stale quote) → refund. Verify each leg with
  `aitbc eth transfers` + `sepolia_balance.py` (net=bal `yes`) and the
  hub ledger row.
- **Abort conditions**: `net=bal NO` on any wallet; nonce mismatch
  warning; a `locked`/`released` row older than its deadline; any
  second ETH send sharing an `ait_tx_hash`; escrow balance ≠ pending
  sum at any checkpoint. On abort: monitor stops releasing (rows stay
  escrowed — the safe state), alert fires, operator resolves.

## 11. Code changes (sized) — none consensus, none now

| file | Δ | what |
|---|---|---|
| `apps/wallet/…/bridge/sell_escrow_monitor.py` | ~300 new | poll loop, lock scan, quote/deadline checks, release + settle/refund signing calls into ops-signer |
| `apps/wallet/…/bridge/bridge_db.py` | +60 | `bridge_sell_locks` + `bridge_sell_quotes` tables; pending-reserve query *excluding* `failed` |
| `apps/wallet/…/bridge/bridge_routes.py` | +120 | `/sell/quote`, `/sell/status/<id>`, `/sell/list` |
| `apps/wallet/…/bridge/price_api.py` | +25 | `BRIDGE_PRICE_MAX_AGE` staleness gate on the Chainlink round |
| `apps/wallet/…/bridge/bridge_withdraw_monitor.py` | +15 | persist `eth_tx_hash` *before* status flip + receipt re-verify on restart (fixes the duplicate-release edge in the shared code path) |
| `cli/aitbc_cli/commands/wallet/bridge.py` | +80 | `aitbc wallet bridge sell quote/lock/status` |
| `docs/ops` + `docs/scenarios` | +60 | sell-escrow runbook + scenario steps |
| ops-signer env | config | `AIT_SELL_ESCROW` address + key slot |

**Post-settle (after 46,100 is live and quiet)**: keyless escrow
`aitbc.bridge.sell.escrow` + a node-internal origination path for its
release/refund (new tx types or a gated internal surface), and the
buyer-facing variant of §7. Nothing in this list is implemented by
this design.

## Could not verify (and why)

- **Exact `TRANSFER` payload limits** — a `payload` dict is accepted
  and stored (the refund path sets `reason`), but whether payload
  *bytes* are size-capped on admission was not chased; the quote id
  is ~40 bytes, so any sane cap admits it. If payload proves not to
  be stored for plain TRANSFERs, the fallback binds lock↔quote on
  (sender, amount, fresh nonce) — documented, not blocking.
- **`eth_withdrawals.status` enumeration under live load** — the
  table has 0 rows; `insufficient_reserve`/`refunded`/`failed`
  transitions are code-read, not observed. ETH-2/scenario 59 will be
  the first live data.
- **Chainlink feed staleness on Sepolia** — `get_eth_prices` return
  shape was read, but the live `updatedAt` cadence of the configured
  feed wasn't probed (read-only on hosts, no call made from this
  task); `BRIDGE_PRICE_MAX_AGE=2h` is a starting default to tune.
- **Whether `eth_sendRawTransaction` envelopes need the same
  nonce-locked durability as AIT payouts** — the AIT side has
  `signed_tx`/`envelope_hash` columns (`eth_deposits` schema);
  ETH-side sends currently re-derive nonce live each call. The
  design *assumes* we want envelope-style persistence for releases;
  whether to reuse the envelope machinery verbatim vs. a leaner
  `(sell_id, nonce)` lock is an implementation decision left open.
- **The shop's actual float need** — "collected a lot of AIT" has no
  on-chain number attached in this task; caps are sized against the
  0.05 ETH float, not demand.

## Evidence pointers (verified while writing)

- burn semantics: `state/state_transition.py:1897`,
  `pure_state_transition.py:412` ("BRIDGE_WITHDRAW burns… never
  creates or credits the pseudo-recipient")
- signature requirement: `v9_policy.py` unsigned-allowed set =
  BRIDGE_LOCK/RELEASE/REFUND only
- monitor flow: `bridge_withdraw_monitor.py:281-343` (record →
  release → status), `:246-258` (refund via genesis TRANSFER),
  `:158-164` (pending-reserve sum)
- ledger schema: `bridge_db.py:83-101` (eth_withdrawals,
  `ait_tx_hash` UNIQUE); `:597-608` (pending incl. `failed`)
- pricing: `price_api.py:139-164` (computed at poll time — quote is
  *not* locked at signing, one of the gaps this design fixes)
- confirmations: `bridge_monitor/main.py:61` (`BRIDGE_CONFIRMATIONS`=3),
  `:963-965` (buried-only payout)
- keyless escrow: `protocol_escrow.py` header (lock/release = plain
  transfers; "only this node's own code can originate" a release —
  hence post-settle)
- job escrow (not reused): `contracts/escrow.py` — v3 ESCROW_LOCK
  requires `job_id`+`provider`; job-shaped, wrong primitive
- BNT-2: unsigned protocol-transfer RPCs retired — the open path to
  originate keyless-escrow releases no longer exists
