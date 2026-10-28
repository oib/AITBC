# Bridge Island Lock → Release — bc-2 → bc-2-island-1 (first live lock)

**Status: ✅ exercised on bc-2 → bc-2-island-1 (28 Oct)** — Lock A
(5,000u): bc-2 @8932 `0xfb2bb32c…` → island `BRIDGE_RELEASE` @156
`b13a6cdc…`; Lock B (30,000,000u): bc-2 @9004 `0x1dc9a5d8…` → island
`BRIDGE_RELEASE` @198 `0aca483b…`; ledger pending→confirmed→completed
×2; recipient 360,000,000 → 390,005,000; roots identical hub1↔node1.
**Level**: Advanced (operator lane)
**Prerequisites**: island `bc-2-island-1` sealing blocks; `BRIDGE_SUPPORTED_CHAINS` wired + rpc restarted; `BRIDGE_LOCKS_PAUSED=false` fleet-wide
**Estimated Time**: 15 minutes + finality/relay time
**Last Updated**: 2026-10-28
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Bridge Island Lock → Release

---

## Scenario Overview

End-to-end **protocol-lane** bridge exercise: `BRIDGE_LOCK`s submitted
on `bc-2` whose relay produces an authority-signed `BRIDGE_RELEASE`
credit that seals on the companion island `bc-2-island-1`
(`apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`,
`bridge_finality.py`). This is the **first live lock** on bc-2 —
`BRIDGE_LOCKS_PAUSED=false` is already fleet-wide, so nothing else
fences it once the island stands.

Context:

- `bc-2-island-1` is produced by **hub1 + node1** (2-of-2 PBFT) from its
  own genesis — its `bridge_validators` and `bridge_release_authority`
  rows are seeded island-side at deploy.
- The bc-2 side needs `BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1` in
  `blockchain.env` on all five hosts plus an rpc restart — **post-8900
  only**: the env matrix is deliberately kept identical while the
  `STATE_TRANSITION_V17_HEIGHT=8900` activation (the v17 drift canary)
  is in play.
- This is the protocol lane — a different path from the ETH-side
  deposit monitor (`apps/bridge-monitor`, `BRIDGE_PAYOUT_*`,
  `scripts/ops/bridge-admin.sh`). Nothing in this play moves ETH-side
  money.
- The governing document is
  [bridge-release-exercise](../ops/bridge-release-exercise.md): this
  play authorizes nothing on its own — the runbook's operator sign-off
  governs the live exercise.

### Prerequisites

- `bc-2-island-1` sealing blocks (hub1 + node1, 2-of-2 PBFT) — a shadow
  ledger cannot seal the release; the historical lock @27251 died
  exactly there (`ait-shop-island` had `accounts` +
  `cross_chain_transfer` but no block/transaction tables)
- `BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1` in `blockchain.env` on
  all five hosts and the units reading it restarted — post-8900 only.
  The island also sits in `SUPPORTED_CHAINS`/`BLOCK_PRODUCTION_CHAINS`
  on its producers; that part is the deploy's job, not this play's.
- `BRIDGE_LOCKS_PAUSED=false` fleet-wide (already set — this play is
  the first lock it admits)
- **Cross-wise validator sets registered** — after
  `BRIDGE_SUPPORTED_CHAINS` lands, each chain must hold the remote's
  real set under the remote chain id BEFORE the first lock: bc-2's
  4-validator set on the island under `chain_id=bc-2`, and the
  island's 2-validator set on bc-2 under `chain_id=bc-2-island-1`, via
  `POST /rpc/bridge/validators/register` (validator self-signature over
  `{chain_id, address, public_key, action:"register"}` — per-host
  `PROPOSER_KEY` — **plus** an authorized bridge admin signature,
  required while `bridge_release_enabled`). Do not rely on the
  backfill: `ensure_supported_chain_validators` silently installs the
  *local* set under every served id, so without the registrations
  both sides resolve the wrong remote set from boot — the same
  wrong-set class that stranded the 27251 attempt. Pre-check: the
  intended admin is `BRIDGE_ADMIN_ADDRESS=0xD80372cb` — the
  pre-rotation `0x02B8F2C6…` id in `bridge-validator-keys.env` on
  hub1+node1 is a known-stale field Coder B corrects during I-2
  (Refs #661).
- The multisig check in `_validate_proof` resolves the validator set
  for the *source* chain, so `BRIDGE_MULTISIG_THRESHOLD=2` is covered
  by bc-2's rows plus lock blocks that carry
  `block_metadata.attestations`. That is the other half of the 27251
  failure — "Threshold not met: 1/6 valid signers (need 2)" because
  that source block carried only the proposer signature.
- `bridge_release_authority` resolvable island-side (genesis row — the
  emitted credit verifies against it)
- Sender wallet: node0 `default` (funded on bc-2)
- Recipient: `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` — a fresh
  address recorded at island deploy (10 AIT genesis alloc), used below
- The lock must be POSTed to a node that **produces bc-2**:
  `initiate_transfer` refuses on non-producers (`ValueError: Source
  chain bc-2 is not produced by this node`). node0 hosts the wallet but
  does not produce bc-2, so `--rpc-url` points at a producer — hub,
  node1, or node2.

---

## Procedure

### Step 1: Gate check — probe, don't fire

```bash
PRODUCER_RPC=http://<bc-2-producer>:8202/rpc   # hub / node1 / node2 — NOT node0 (non-producer)

# pause flag — the honest pre-lock read (env, not the endpoint)
grep '^BRIDGE_LOCKS_PAUSED=' /etc/aitbc/blockchain.env     # want: false

# free read-only probes — none of these fires a lock
aitbc bridge health           --rpc-url "$PRODUCER_RPC"
aitbc bridge security-status  --rpc-url "$PRODUCER_RPC"
aitbc bridge oracle-status    --rpc-url "$PRODUCER_RPC"
aitbc bridge pending --chain-id bc-2 --rpc-url "$PRODUCER_RPC"
curl -s "$PRODUCER_RPC/bridge/validators/bc-2-island-1" | python3 -m json.tool
#   ^ the validators endpoint validates chain_id against SUPPORTED_CHAINS —
#     on a host that does not host the island it 400s ("not in
#     supported_chains"); probe an island producer (hub1 / node1) instead.
# cross-wise check (on an island unit): must show bc-2's REAL 4 validators,
# not a backfilled local set
curl -s "http://<island-rpc>/rpc/bridge/validators/bc-2" | python3 -m json.tool
```

**Expected:** `BRIDGE_LOCKS_PAUSED=false`; `release_enabled: true`;
`bridge_max_lock_amount: 36000000000`; `multisig_enabled: true` with
`validator_count ≥ 2` (the threshold); `min_confirmations: 3`,
`finality_blocks: 6`, `large_transfer_threshold: 10000`; the island's
validator set non-empty; `pending` empty. Do not proceed on
`release_enabled: false`, an empty validator set, or a 503.

### Step 2: Lock A — 5,000 units (small-transfer finality path)

Run on node0 (the `default` wallet lives there), pointed at the
producer RPC. `--wallet-name default` signs the eight-field replay-guard
dict and generates `issued_at`/`nonce` itself — nodes with
`BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true` refuse the legacy six-field
body, so do not drop to `--signature` without matching `--issued-at`/`--nonce`.

```bash
aitbc bridge lock \
  --rpc-url "$PRODUCER_RPC" \
  --target-chain bc-2-island-1 \
  --sender <node0-default-address> \
  --recipient 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40 \
  --amount 5000 \
  --wallet-name default          # add --wallet-password if the wallet is encrypted
```

5,000 units sits below `BRIDGE_LARGE_TRANSFER_THRESHOLD` (10,000 raw
units, ~0.00028 AIT) → this lock takes the 3-confirmation
`BRIDGE_MIN_CONFIRMATIONS` path. Record the returned transfer id (it is
also the lock tx hash). A `BRIDGE_LOCK` row seals on bc-2 and the
`cross_chain_transfer` record appears `pending`.

### Step 3: Lock B — 30,000,000 units (large-transfer finality path)

Same command, `--amount 30000000`. At/above the threshold → the
6-confirmation `BRIDGE_FINALITY_BLOCKS` path — expect the confirm to
wait roughly twice as many blocks as Lock A's. Both locks sit far below
`BRIDGE_MAX_LOCK_AMOUNT` (36,000,000,000 units = 1,000 AIT).

```bash
aitbc bridge lock \
  --rpc-url "$PRODUCER_RPC" \
  --target-chain bc-2-island-1 \
  --sender <node0-default-address> \
  --recipient 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40 \
  --amount 30000000 \
  --wallet-name default
```

### Step 4: Observation — finalizer + relayer (automatic, ~60 s passes)

**Observation, no command to fire.** On any node hosting both stores
(the island producers host bc-2 + `bc-2-island-1`), each finalizer pass
inside `aitbc-blockchain-node` (`bridge_monitor_interval` = 60 s) runs:

1. `_sync_local_chain_headers` — mirrors produced bc-2 block headers
   into `bridge_block_header` (the finality anchor; first pass backfills
   only the recent window).
2. `_relay_pending_transfers` — builds the real proof via `build_proof`
   (`merkle_proof`, `lock_event`, `bridge_state_root`,
   `proposer_signature`, and `validator_signatures` lifted from the lock
   block's `block_metadata.attestations`) and calls `confirm_transfer`,
   which runs the full `_validate_proof` chain: field match →
   recipient-bound leaf → stored-header check → proposer signature →
   Merkle inclusion → finality tier → multisig threshold.
3. The emitted `BRIDGE_RELEASE` (`sender='bridge_release'`,
   `payload.bridge_signature` signed by
   `BRIDGE_RELEASE_PRIVATE_KEY`/`ESCROW_RELEASE_PRIVATE_KEY`, verified
   island-side against `bridge_release_authority`) preregisters into the
   island mempool and **seals in a produced island block**; the record
   moves `pending` → `confirmed` → `completed` (completed is mirrored
   back onto the bc-2 record).

```bash
journalctl -u aitbc-blockchain-node --since "-10min" | \
  grep -iE 'bridge (relayer|header|finaliz)|confirm'
```

Expect `Relayed 1 bridge transfers on chain bc-2` within a few passes of
the lock block reaching its tier's confirmations. A couple of silent
passes right after the lock seals is the normal finality wait, not a
stuck row — failures stay `pending` and retry every pass.

### Step 5: Island-side verification

```bash
# on an island producer (hub1 / node1) — the island chain store
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT tx_hash, block_height, sender, recipient,
          json_extract(payload,'$.amount') AS amount
   FROM transaction WHERE type='BRIDGE_RELEASE' ORDER BY block_height;"

# bc-2 side — transfer record lifecycle
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT transfer_id,status,target_tx_hash FROM cross_chain_transfer;"
```

**Expected:** two `BRIDGE_RELEASE` rows sealed on `bc-2-island-1`
(`sender='bridge_release'`, `recipient=0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40`, amounts 5,000 and
30,000,000) and both bc-2 records at `completed` with `target_tx_hash`
set to the release tx hash.

---

## Validation

```bash
# bc-2: two locks sealed
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT tx_hash,block_height,sender,recipient,value FROM transaction \
   WHERE type='BRIDGE_LOCK' ORDER BY block_height DESC LIMIT 5;"

# bc-2: records completed
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT transfer_id,status,target_tx_hash FROM cross_chain_transfer;"

# island: two releases sealed + island-side record lifecycle
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT tx_hash,block_height,sender,recipient,type FROM transaction \
   WHERE type='BRIDGE_RELEASE' ORDER BY block_height;"
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT transfer_id,status,target_tx_hash FROM cross_chain_transfer;"
```

**Expected:**

- Two `BRIDGE_LOCK` rows on bc-2 (`sender=<node0-default-address>`,
  `recipient='bridge_lock'`, `value` = 5,000 / 30,000,000) — one at each
  finality tier: the 5,000 lock confirms once its block header reaches
  `confirmation_count ≥ 3` (`BRIDGE_MIN_CONFIRMATIONS`), the
  30,000,000 lock needs `≥ 6` (`BRIDGE_FINALITY_BLOCKS`)
- Two matching `BRIDGE_RELEASE` rows on `bc-2-island-1` —
  `sender='bridge_release'`, `recipient=0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40`,
  `payload.amount` = 5,000 / 30,000,000, each carrying
  `payload.bridge_signature` verifiable against the island's
  `bridge_release_authority`
- `cross_chain_transfer` flips `pending` → `confirmed` → `completed`
  with `target_tx_hash` set — on **both** the bc-2 and the island
  stores
- `aitbc bridge pending --chain-id bc-2` returns to `[]` once both
  complete

---

## Related Resources

- [Bridge release exercise runbook](../ops/bridge-release-exercise.md) — the governing runbook; this play defers to its operator sign-off
- [v1–v9 live-exercise waivers](../decisions/v1-v9-live-exercise-waivers.md) — V-1 reserves this one live `BRIDGE_RELEASE` exercise pending operator approval
- [On-chain record coverage](./README.md#on-chain-record-coverage) — the coverage rows this scenario feeds
- [Bridge CLI options](./76_bridge_options.md) — the same `aitbc bridge` surface exercised as reads/free refusals
- [Sepolia buy/sell via the ETH bridge](./59_sepolia_buy_sell_ait.md) — the other (ETH-side) bridge lane

---

*Last updated: 2026-10-28*
*Version: 1.0*
