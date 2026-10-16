# Messaging storage growth and spam economics (MSG-9)

Report-only measurement of what a forum post costs to store and what spam
could do to the chain database. Measured 2026-10-16 on hub and node2 via
read-only RPC and the backup copies already present in the data
directories — the live `chain.db`/`chain.db-wal` was never opened (WAL
safety), and no keys or wallets were touched.

## Measured

| quantity | value | source |
|---|---|---|
| chain height (hub / node2) | 48975 / 48976 | `GET /rpc/height`, 2026-10-16 ~00:34 UTC |
| live `chain.db` size (hub) | 124,674,048 B (~119 MiB) + 4.3 MB WAL | `ls -la` data dir |
| live `chain.db` size (node2) | 124,669,952 B (~119 MiB) | `ls -la` data dir |
| MSG-3a MESSAGE tx (API view) | 717 B total JSON, 277 B `payload` | `GET /rpc/transaction/0x4c125811…ac44` |
| backup Sep 10 | height 921, 13 txs, 1.7 MB | `sqlite3 -readonly chain.db.bak.20260910` |
| backup Sep 27 (fork-era) | height 25560, 226 txs, 59.7 MB | `…bak-20260927-fork` |
| backup Sep 28 | height 27207, 253 txs, 63.8 MB | `…bak-20260928-27207wedge` |
| backup Oct 2 | height 31643, 301 txs, 75.3 MB | `…bak-pre-gpu-clean-20261002` |
| tx payload bytes by type (Oct 2) | 301 txs, ~150 KB payloads total; largest classes GPU_MARKET/GPU_MARKETPLACE ~820 B avg, ESCROW_* ~170-250 B avg | `GROUP BY type` on the Oct 2 backup |
| biggest tables (Oct 2, `dbstat`) | `block` 40.4 MB, `bridge_block_header` 13.7 MB, block indexes ~7.3 MB; `transaction` not in top 8 | `dbstat` on the Oct 2 backup |

### Growth rate

Oct 2 → Oct 16: 31643 → 48975 blocks = 17332 blocks in ~13.6 days ≈
**1270 blocks/day (~68 s/block — the `max_empty_block_interval` heartbeat
paces a mostly-empty chain)**, and 75.2 MB → 124.7 MB ≈ **3.6 MB/day** of
total growth, dominated by block rows (~1.3 KB/block + ~0.4 KB bridge
header + indexes), not transactions. At this organic rate: **1 GB ≈ 285
days**, entirely independent of messaging.

### Admission and caps (code)

- `POST /rpc/transaction`: **no API key**; in-app limiter `50 req/60 s`
  per client IP. Fee/balance checked, signature verified.
- Mempool: 10,000 entries global, 128 KiB per tx, fee-priority eviction;
  `mempool_nonce_lookahead = 16` bounds pending nonces per sender.
- Blocks: `max_txs_per_block = 500`, `block_time_seconds = 10` target,
  heartbeat empty block at 60 s.
- Message: body ≤ 4096 B (`MAX_MESSAGE_BODY_BYTES`), topic ≤ 64 chars,
  fee floor observed 360000 base units (0.01 AIT).

## Model — worst case at today's rules

Row cost per post: ~0.7-1.1 KB minimal body, ~5.2 KB at the 4 KB cap
(payload + envelope + columns, derived from the MSG-3a row). Cost is
paid in fees: **0.01 AIT per message regardless of speed.**

- **Fee-bound**: 1 GB of message rows ≈ 192k max-body posts ≈
  **~1900 AIT per GB**; 10 GB ≈ ~19,000 AIT. Every replica stores a copy,
  so real fleet storage is ×5.
- **Rate-bound** (in-app limiter only): 50/min per source IP → ≤72k
  msgs/day per IP ≈ **~375 MB/day of rows**, i.e. 1 GB in ~2.7 days at
  ~720 AIT/day. The nonce-lookahead (16) only bounds per-account *pending
  depth* — nonces refill as blocks seal, so it is not a daily cap.
- **Block-bound**: 500 tx/block → at the 10 s target ≈ 4.3 M tx/day
  ceiling; at the measured 68 s heartbeat pace ≈ 635k/day. Sealing is
  never the binding constraint versus the fee or the submit limiter.
- Steady single-IP spam at 1 msg/min: ~7.3 MB/day of rows, ~14.4 AIT/day —
  1 GB in ~137 days for ~2000 AIT total.

Spam is therefore **fee-bound in total cost and IP-rate-bound in speed**;
the durable lever is making admission smarter, not storage cheaper.

## Recommended non-consensus limits (ranked)

1. **Per-sender admission rate for MESSAGE txs** — enforce in
   `submit_transaction`/`mempool.add` (e.g. ≤N MESSAGE per sender per
   rolling window, or a MESSAGE-specific pending-count cap tighter than
   the 16-nonce lookahead). Bypass: funded multi-account spreading —
   each identity still pays the same total fee, so cost per GB is
   unchanged; it caps *rate*, not *total*. Cost: small (mempool +
   submit path, tests).
2. **nginx `limit_req` on the submit route** — extend the
   `messaging_rpc` zone (deployed 16 Oct per
   `docs/ops/messaging-explorer-nginx.md`) to a `location = /rpc/transaction`
   or a `location /rpc/` write-side variant at the public edge. Bypass:
   multi-IP; followers' `0.0.0.0:8202` sockets skip nginx entirely (see  <!-- check-ports: ignore -->
   `messaging-nginx-limits.md` exposure caveat). Cost: config only.
3. **Alert thresholds** — Prometheus alerts on `total_messages` growth
   rate, mempool depth, and per-sender submit rate; the hardened index
   already exposes cheap aggregates (`scan_bounded:false`), so the probe
   is a read of `/rpc/messaging/state`. Cost: small (alert rules only).
4. **Read-side hygiene (already in place)** — MSG-FIX-1 bounded scans,
   cursor/offset caps, nginx `limit_req` on `/rpc/messaging/*` and
   `/explorer-api/api/messages*`. Note for operators: the "index" is a
   bounded query over the `transaction` table — there is no separate
   index store to retain or prune; retention talk only makes sense for
   snapshots/backups, not the chain.
5. **Backup pressure** — chain.db grows ~3.6 MB/day organically; backups
   accumulate uncompressed in the same dir (75-125 MB each and growing).
   A rotation/compression policy is housekeeping, not consensus.

## Options that need the operator (listed, not decided — MSG-12)

- **Fee schedule**: per-byte fee for MESSAGE bodies (e.g. fee ∝ payload
  size) — changes the spam unit price; consensus-adjacent, needs a
  versioned fee rule.
- **Body size cap**: lowering `MAX_MESSAGE_BODY_BYTES` below 4096 —
  consensus-visible predicate change.
- **Per-sender stake/bond for posting** — bond locked per active poster,
  slashed or burned on rule violations; needs the MSG-2 moderation
  authority question settled first.

## Reproduce

```bash
# height + head
curl -s http://127.0.0.1:8202/rpc/height  # check-ports: ignore — loopback RPC port, not the edge service
# one MESSAGE row's size
curl -s http://127.0.0.1:8202/rpc/transaction/<tx_hash> | python3 -m json.tool | wc -c
# backup-copy stats (never open the live WAL db)
sqlite3 -readonly <backup>.bak 'SELECT max(height) FROM block;'
sqlite3 -readonly <backup>.bak 'SELECT type, count(*), sum(length(payload)) FROM "transaction" GROUP BY type;'
sqlite3 -readonly <backup>.bak 'SELECT name, sum(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC LIMIT 8;'
```
