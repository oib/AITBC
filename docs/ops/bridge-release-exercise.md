# BRIDGE_RELEASE live exercise — runbook (DRAFT FOR APPROVAL)

> **Status: EXECUTED (28 Oct) — green run.** Approved by operator
> decision (cards 1B + 2 + card-11 30M resize). Evidence:
>
> - **Lock A** (5,000u, 3-conf tier): `BRIDGE_LOCK` bc-2 @8932
>   `0xfb2bb32c…` → island `BRIDGE_RELEASE` @156 `b13a6cdc…`
> - **Lock B** (30,000,000u, 6-conf tier): `BRIDGE_LOCK` bc-2 @9004
>   `0x1dc9a5d8…` → island `BRIDGE_RELEASE` @198 `0aca483b…`
> - ledger `pending → confirmed → completed` ×2; recipient balance
>   360,000,000 → 360,005,000 → 390,005,000 units; state+aux roots
>   identical hub1↔node1 @198.
>
> Two incidents ran and were recovered — warnings below.
> V-1 waived live exercises for all 22 fixture-replayable types but
> explicitly reserved the one live `BRIDGE_RELEASE` exercise "pending
> operator approval" — see
> [What is NOT waived](../decisions/v1-v9-live-exercise-waivers.md#what-is-not-waived).
> This document ends at an **approved / not approved** decision, not at
> execution.

## What this exercise is (and is not)

This runbook covers the **protocol-lane** `BRIDGE_RELEASE`: a cross-chain
`BRIDGE_LOCK` on `bc-2` whose relay produces an authority-signed
`BRIDGE_RELEASE` credit that seals in a block on the **target chain**
`bc-2-island-1`, the companion island
(`apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`,
`bridge_finality.py`).

It is a **different path** from the ETH-side deposit payout lane
(`apps/bridge-monitor`, `BRIDGE_PAYOUT_*`, `TRANSFER` envelopes,
`scripts/ops/bridge-admin.sh`). Nothing in this exercise moves ETH-side
money; the ledger-first payout rules below apply only if a companion step
touches that lane.

## Goal — what a green run proves

Two `BRIDGE_LOCK`s → two `BRIDGE_RELEASE`s, exercised end to end on the
live fleet — one lock per finality tier (parameters below):

1. **Monitor detection** — the finalizer loop (`start_finalizer`,
   `bridge_monitor_interval` = 60 s) inside the island unit's
   `aitbc-blockchain-node` on hub1/node1 mirrors the source chain's
   sealed headers into `bridge_block_header`
   (`_sync_local_chain_headers`) and notices the locked transfer.
2. **Proof + full validation** — `_relay_pending_transfers` builds the
   real Merkle inclusion proof (`build_proof`: `merkle_proof`,
   `lock_event`, `bridge_state_root`, `proposer_signature`,
   `validator_signatures` lifted from
   `block.block_metadata.attestations`) and `confirm_transfer` runs the
   full `_validate_proof` chain — field match, leaf binding, stored-header
   check, proposer signature, Merkle verification
   (`BRIDGE_REQUIRE_MERKLE_PROOF=true`), finality
   (`BRIDGE_MIN_CONFIRMATIONS=3` for Lock A, below
   `BRIDGE_LARGE_TRANSFER_THRESHOLD`; `BRIDGE_FINALITY_BLOCKS=6` for
   Lock B, at/above it), and the multisig threshold
   (`BRIDGE_MULTISIG_THRESHOLD=2` against the genesis-seeded
   `bridge_validators` set of the source chain).
3. **Authority-signed envelope → sealed block** — the emitted
   `BRIDGE_RELEASE` (`sender = "bridge_release"`, `payload.bridge_signature`
   from `BRIDGE_RELEASE_PRIVATE_KEY`/`ESCROW_RELEASE_PRIVATE_KEY`) lands in
   a produced block on the target chain; the record moves
   `pending → confirmed → completed`.
4. **Replay determinism** — every host that imports the release block
   applies the credit and arrives at the same `state_root`/`aux_state_root`;
   the replay suite's determinism claim demonstrated on a real, live
   transaction.

### What it does NOT prove

- The ETH→AIT deposit monitor lane (detection, ledger rows, `TRANSFER`
  payout envelopes — covered by `bridge-canary-runbook.md`).
- `BRIDGE_WITHDRAW`, `BRIDGE_REFUND`, refund-after-timeout, or fork
  healing of an in-flight release.
- Sustained relay throughput or concurrent locks — the two locks run
  sequentially, one tier at a time.
- The `BRIDGE_LOCKS_PAUSED` refusal path itself (503 at the route,
  `BridgeLocksPausedError` in `initiate_transfer`) — locks are already
  unpaused fleet-wide and stay that way; the guard is context, not a
  step in this runbook.
- Anything about the v9/v17 signature rules — a `BRIDGE_RELEASE` block
  proves the bridge path, not protocol-transfer policy.

## Preconditions

### Hard gates — all must hold before any lock is submitted

- [ ] **`BRIDGE_LOCKS_PAUSED=false` on `bc-2` — already fleet-wide.**
      Locks are unpaused on every host; this exercise **is** the first
      live lock — verify the env value, do not toggle it. The guard
      stays as machinery context: while `true`, `/rpc/bridge/lock`
      refuses with 503 and `initiate_transfer` raises
      `BridgeLocksPausedError` before any lock envelope is signed;
      refund/confirm paths are deliberately untouched by the pause.
- [ ] **`bc-2-island-1` exists as a produced companion chain** — the
      release target. `initiate_transfer` refuses same-chain locks, and
      the release only seals if the target chain *produces blocks*. The
      historical attempt (lock @27251 on `ait-hub`, target
      `ait-shop-island`) died here: the island was a shadow ledger —
      `accounts` + `cross_chain_transfer` only, no block/transaction
      tables — so even a passed confirm had nowhere to seal. Resolved
      topology (operator decision, option B): the island is deployed in
      **Coder B's lane** — own genesis via the standard genesis builder
      with `bridge_validators` + `bridge_release_authority` rows baked
      island-side, own DATA_DIR/env/ports, and dedicated systemd units
      on **hub1 + node1** as its 2-of-2 PBFT validator set (island
      blocks carry `block_metadata.attestations`). The island units
      host both stores — `bc-2` followed + `bc-2-island-1` produced —
      so the confirming finalizer runs there. Deploy spec:
      [companion-island-deploy.md](companion-island-deploy.md).
- [ ] **bc-2-side wiring — gated on post-8900** (Coder A holds this
      step): `BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1` in
      `/etc/aitbc/blockchain.env` on all five hosts, then restart
      `aitbc-blockchain-rpc` (the RPC unit only — no producer restart).
      Held until the bc-2 head is past `STATE_TRANSITION_V17_HEIGHT`
      (8900) so the v17 drift canary stays clean during the armed
      window. Without the edit `/rpc/bridge/lock` refuses
      `target_chain=bc-2-island-1` at admission; `SUPPORTED_CHAINS`
      stays `bc-2` on the bc-2 units — bc-2-only nodes simply skip the
      island store in finalizer passes.
- [ ] **Cross-wise validator sets registered** — bc-2's real 4
      validators on the island under `bc-2`; the island's real 2 on
      bc-2 under `bc-2-island-1` — each self-signed + admin-signed via
      `POST /rpc/bridge/validators/register` (Phase 1; the
      `ensure_supported_chain_validators` backfill installs the wrong
      local set by default). `BRIDGE_ADMIN_ADDRESS` identity verified
      against `bridge-validator-keys.env` first — intended admin is
      `0xD80372cb`; the file's pre-rotation `0x02B8F2C6…` id on
      hub1+node1 is a known-stale field Coder B corrects during I-2
      (Refs #661).
- [ ] **The bc-2 `bridge_validators` set is populated** (genesis-seeded;
      verified by `ensure_supported_chain_validators` at startup —
      `BRIDGE_MULTISIG_VALIDATORS=4` is only the fence count
      `N ≥ threshold`, membership comes from the table rows).
- [ ] **Every host on the intended commit or newer**, `bridge` env
      matrix identical fleet-wide (`fleet-config-check.sh`).

### Confirm the path is armed but unexercised

```bash
# env matrix on the bc-2 hosts + the island units (hub1, node1)
grep -h '^BRIDGE_\|^MULTI_VALIDATOR_\|^SUPPORTED_CHAINS\|^BLOCK_PRODUCTION_CHAINS' \
  /etc/aitbc/blockchain.env /etc/aitbc/bridge-validator-keys.env 2>/dev/null | sort
# island units: same grep against each unit's own env file (path per
# the island deploy spec — own env, not /etc/aitbc/blockchain.env)

# expected on bc-2 (from docs/deployment/bc2-environment-set.md):
#   BRIDGE_RELEASE_ENABLED=true            BRIDGE_LOCKS_PAUSED=false (already fleet-wide)
#   BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1  (post-8900 edit — hard gate above)
#   BRIDGE_REQUIRE_MERKLE_PROOF=true
#   BRIDGE_MULTISIG_ENABLED=true           BRIDGE_MULTISIG_THRESHOLD=2
#   BRIDGE_MULTISIG_VALIDATORS=4           BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true
#   BRIDGE_LOCK_LEAF_V2_HEIGHT=1           BRIDGE_MAX_LOCK_AMOUNT=36000000000
#   MULTI_VALIDATOR_CONSENSUS_ENABLED=true MULTI_VALIDATOR_MIN_ATTESTATIONS=2
#   SUPPORTED_CHAINS=bc-2 (unchanged — the island is not hosted on the bc-2 units)

# unexercised: no BRIDGE_RELEASE has ever sealed on the island
# (run on hub1 or node1 — /var/lib/aitbc per the deploy spec)
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT count(*) FROM transaction WHERE type='BRIDGE_RELEASE';"     # → 0
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT status, count(*) FROM cross_chain_transfer GROUP BY status;" # → empty
curl -s http://127.0.0.1:8202/rpc/bridge/pending | python3 -m json.tool # → []

# free read-only probes against a bc-2 producer RPC — none fires a lock
PRODUCER_RPC=http://<bc-2-producer>:8202/rpc
aitbc bridge health           --rpc-url "$PRODUCER_RPC"   # release_enabled: true
aitbc bridge security-status  --rpc-url "$PRODUCER_RPC"   # caps/finality values as above
aitbc bridge pending --chain-id bc-2 --rpc-url "$PRODUCER_RPC"   # → []
curl -s "$PRODUCER_RPC/bridge/validators/bc-2-island-1" | python3 -m json.tool
```

### Node / wallet / authority roles

| role | who | notes |
|---|---|---|
| confirming nodes | the `bc-2-island-1` units on **hub1 + node1** | only hosts holding both stores (`bc-2` followed + island produced); the relayer skips a target whose store isn't local (`_chain_db_ready`) — observe on either |
| lock submitter | node0 **`default`** wallet | funded on bc-2 (≥ amount + 0.1% fee, both locks); signs the replay-guarded lock body (`issued_at`+`nonce`) — `aitbc bridge lock --wallet-name default` generates them; submit reaches a **bc-2 producer's** RPC (Phase 2) |
| recipient | `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` | fresh address generated on `bc-2-island-1` at deploy time (Coder B) — recorded at island deploy (10 AIT genesis alloc); the release mints credit to it |
| authority key | `BRIDGE_RELEASE_PRIVATE_KEY` / `ESCROW_RELEASE_PRIVATE_KEY` env on the island units | signs the credit; verified against the island's `bridge_release_authority` chain parameter (baked at island genesis); bc-2 keeps its own live authority for the lock side per the env-set ruling |
| island producers | **hub1 + node1** (2-of-2 PBFT) | dedicated units, own DATA_DIR/env/ports; produce the island blocks the releases seal in. The lock proof's `validator_signatures` come from **bc-2's** block attestations (≥2 per block) — the island side does not feed the threshold |

### Parameters — resolved by operator decision

- **Companion chain = `bc-2-island-1`** (option B): own genesis via the
  standard genesis builder with `bridge_validators` +
  `bridge_release_authority` rows baked island-side; 2-of-2 PBFT
  validators on **hub1 + node1**; own DATA_DIR/env/ports, dedicated
  systemd units. Island deploy is **Coder B's lane** — this runbook
  consumes that spec, it does not define it.
- **Two locks, one per finality tier**
  (`bridge_finality.py:_check_finality_for_transfer` —
  `BRIDGE_LARGE_TRANSFER_THRESHOLD` = 10000 **raw units**, ~0.00028
  AIT):
  - **Lock A = 5,000 units** — below the threshold → the
    3-confirmation `BRIDGE_MIN_CONFIRMATIONS` path (the "small" tier
    that would otherwise only ever serve dust).
  - **Lock B = 30,000,000 units** (resized from 36M — sender
    `0x08aB80…` holds 34,780,000u; 36M + fees was ~1.26M short. The
    tier boundary is `>10,000u`, so 30M exercises the same
    6-confirmation path with margin — recipient expected total across
    both locks: **30,005,000u**) — at/above the threshold →
    the 6-confirmation `BRIDGE_FINALITY_BLOCKS` path.
  Both far under `BRIDGE_MAX_LOCK_AMOUNT` = 36,000,000,000 raw = 1000
  AIT (fail-closed: `0`/unset refuses locks in production).
- **Sender** = node0 `default` wallet (funded on bc-2).
- **Recipient** — `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` —
  recorded at island deploy (a fresh address generated on
  `bc-2-island-1`, 10 AIT genesis alloc).
- **Confirming nodes** = the island units on hub1 + node1 (the only
  hosts with both stores); the locks are submitted **from node0** to a
  bc-2 producer's RPC.

## Procedure

### Phase 0 — record the parameters

Confirm the resolved set: `bc-2-island-1`, Lock A `5000` + Lock B
`30000000`, sender = node0 `default` (record its bc-2 address),
confirming nodes = the island units on hub1/node1. The recipient is
now recorded: `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` (generated
at island deploy — verify it against the deploy record before
executing; the run is not valid without it).
Note current bc-2 head height for the evidence log.

### Phase 1 — companion island standing + bc-2 wiring

- `bc-2-island-1` deployed and sealing (**Coder B's lane**): dedicated
  units on hub1 + node1, own DATA_DIR/env/ports;
  `/var/lib/aitbc/data/bc-2-island-1/chain.db` exists and blocks
  seal (`curl -s http://127.0.0.1:8302/rpc/head` on the
  island unit, or the node's multi-chain head endpoint).
- `bridge_release_authority` resolvable for `bc-2-island-1` — baked as
  a chain parameter at island genesis (env fallback
  `BRIDGE_RELEASE_AUTHORITY`/`ESCROW_SETTLEMENT_AUTHORITY` on the
  unit).
- Island `bridge_validators` rows present (baked at genesis); the
  island unit's `ensure_supported_chain_validators` startup check
  passed.
- **bc-2-side wiring — post-8900 only (Coder A):** once the bc-2 head
  is past `STATE_TRANSITION_V17_HEIGHT` (8900), set
  `BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1` in
  `/etc/aitbc/blockchain.env` on all five hosts and restart
  `aitbc-blockchain-rpc` on each; verify with
  `fleet-config-check.sh`. Do **not** touch `SUPPORTED_CHAINS` or
  `BLOCK_PRODUCTION_CHAINS` on the bc-2 units — the island is hosted
  only by its own units.
- **Cross-wise validator registration — mandatory before the first
  lock.** Once `BRIDGE_SUPPORTED_CHAINS` lands, each chain must hold
  the *other* chain's real validator set under the remote chain id —
  bc-2's 4-validator set registered on `bc-2-island-1` under
  `chain_id=bc-2`, and the island's 2-validator set registered on
  bc-2 under `chain_id=bc-2-island-1` — via
  `POST /rpc/bridge/validators/register`. Do not rely on the
  backfill: `ensure_supported_chain_validators`
  (`cross_chain/bridge_validator.py:100-135`) silently installs the
  *local* chain's set under every served target id — without the
  explicit registrations the bridge set each side resolves for the
  remote is wrong from boot (the same wrong-set class that stranded
  the historical 27251 attempt — "1/6 valid signers"; **live-verified
  28 Oct** — the 12:54 restart backfilled bc-2's local 4 under
  `bc-2-island-1` before the genuine registrations ran, see the known
  trap in [companion-island-deploy](companion-island-deploy.md)). Each
  registration body needs the validator's **self-signature** over the
  canonical JSON `{chain_id, address, public_key, action:"register"}`
  (per-host `PROPOSER_KEY` signs for its own address) **plus** an
  authorized **bridge admin signature** (`admin_address` +
  `admin_signature` — required whenever `bridge_release_enabled`,
  `rpc/bridge.py:644-654`).
  - **Admin pre-check first:** the intended admin is
    `BRIDGE_ADMIN_ADDRESS=0xD80372cb` (the real
    `BRIDGE_ADMIN_ADDRESSES` value — Refs #661).
    `/etc/aitbc/bridge-validator-keys.env` on hub1+node1 carried a
    stale pre-rotation `BRIDGE_ADMIN_ADDRESS=0x02B8F2C6…` — inert but
    stale; Coder B corrects the field to `0xD80372cb` during I-2.
    Verify the corrected value is in place before registering:
    registrations under the wrong admin are refused; registrations
    under a compromised-stale id would be accepted.
  - Verify the resolved sets afterwards:
    `GET /rpc/bridge/validators/bc-2` **on an island unit** must list
    bc-2's 4 real validators, and `GET
    /rpc/bridge/validators/bc-2-island-1` **on a bc-2 producer** must
    list the island's 2 — not the backfilled local set.

### Phase 2 — submit the locks (operator or delegated agent)

Run on **node0** — the `default` wallet lives there. The signed lock
must reach a **bc-2 producer's** RPC: `initiate_transfer` rejects lock
submissions on followers whose `BLOCK_PRODUCTION_CHAINS` lacks the
source chain (`ValueError: Source chain bc-2 is not produced by this
node`), and node0 follows bc-2 without producing it.

```bash
PRODUCER_RPC=http://<bc-2-producer>:8202/rpc   # hub / node1 / node2 / hub1 — NOT node0

# Lock A — 5,000 units (small tier: 3-confirmation path)
aitbc bridge lock --rpc-url "$PRODUCER_RPC" \
  --target-chain bc-2-island-1 \
  --sender <node0-default-address> --recipient 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40 \
  --amount 5000 --wallet-name default

# Lock B — 30,000,000 units (large tier: 6-confirmation path)
aitbc bridge lock --rpc-url "$PRODUCER_RPC" \
  --target-chain bc-2-island-1 \
  --sender <node0-default-address> --recipient 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40 \
  --amount 30000000 --wallet-name default
```

- `--wallet-name default` signs the eight-field replay-guard body and
  generates `issued_at`/`nonce` itself — `BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true`
  nodes refuse the legacy six-field body, so do not drop to
  `--signature` without matching `--issued-at`/`--nonce`.
- Submit **sequentially**: let Lock A reach `completed` before
  submitting Lock B, so each finality tier is observed cleanly.
- Record each returned transfer id / tx hash. Expected per lock:
  `BRIDGE_LOCK` row in bc-2 mempool → sealed in a bc-2 block →
  `cross_chain_transfer` row `status='pending'`, `source_tx_hash` set.

### Phase 3 — observe detection → confirm (finalizer, automatic)

```bash
# on hub1 or node1 — the island's dedicated unit (name per deploy spec)
journalctl -u aitbc-blockchain-node-island --since "-10min" | \
  grep -iE 'bridge (relayer|header|finaliz)|confirm'
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT transfer_id,status,target_tx_hash FROM cross_chain_transfer;"
```

Expected within a few `bridge_monitor_interval` (60 s) passes after the
lock block reaches its tier's confirmations — **3**
(`BRIDGE_MIN_CONFIRMATIONS`) for Lock A, **6**
(`BRIDGE_FINALITY_BLOCKS`) for Lock B, so Lock B's confirm takes
roughly twice as many blocks:

- `bridge_block_header` rows for `bc-2` mirror past the lock height
  (the island units mirror the source chain's headers into their local
  stores — the finality anchor).
- `Bridge relayer: confirm …` / `Relayed 1 bridge transfers on chain bc-2`.
- Record → `status='confirmed'`, `target_tx_hash` = the emitted release
  tx hash. Failures stay `pending` and retry every pass — an intermediate
  state, not a stuck row.

### Phase 4 — observe seal → completed

```bash
# on hub1 or node1 — the island chain store (/var/lib/aitbc per deploy spec)
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT tx_hash,block_height,sender,recipient,type FROM transaction \
    WHERE type='BRIDGE_RELEASE';"                    # → 1 row per lock, 2 total
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT status FROM cross_chain_transfer WHERE transfer_id='<id>';"   # → completed
curl -s http://127.0.0.1:8302/rpc/bridge/transfer/<id> | python3 -m json.tool
```

- The release seals in a `bc-2-island-1` block; the record flips to
  `completed` on the next finalizer pass (also mirrored onto the bc-2
  record).
- Capture: release tx hash, sealed height, block hash, and the sealed
  `payload` (`transfer_id`, `source_chain`, `source_sender`,
  `target_chain`, `amount`, `asset`, `proof` = proof hash,
  `bridge_signature`).

### Phase 5 — replay determinism

- On every host serving `bc-2-island-1` — hub1 + node1 in this
  topology: confirm both release txs and their blocks exist with
  identical `state_root`/`aux_state_root` at the sealed heights
  (`/rpc/blocks-range` or the chain store), and the recipient's
  balance delta is identical.
- `sqlite3` the `account` row for `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` on each island host
  — same balance everywhere, = 36,005,000 units (Lock A + Lock B;
  the release credits the full locked amount on the target chain).

### Phase 6 — record evidence

Append height/tx-hash/hosts-verified to the exercise record (this file's
evidence section or the tracking ticket) and update the V-1 close-out
placeholder row for `BRIDGE_RELEASE` via the decision doc's next edit.

## Ledger-first payout rules — quoted verbatim

From `AGENTS.md` ("Bridge payout account — no manual sends"); they bind
any step that touches the payout account — **the protocol-lane release in
this runbook does not use it**:

> Never send an ad-hoc transaction from the bridge payout account
> (`BRIDGE_PAYOUT_*`). Every payout must go through a ledger row:
> SUBMITTED rows hold a signed envelope whose nonce may still land — a
> manual send can occupy that nonce and strand the deposit forever, and
> two sends from the same account is how double payments happen. Operator
> actions use the monitor's own commands, never a raw RPC submit:

```bash
cd /opt/aitbc && scripts/ops/bridge-admin.sh <command>
#   status <tx_hash>                inspect a ledger row
#   list [--status S] [--limit N]   recent rows (incl. FUNDING/FAILED)
#   manual-payout <to> <amount>     manual payout, same ledger-first path
#   abandon-and-resign <tx_hash>    abandon a stuck SUBMITTED payout —
#                                   refuses unless the account nonce has
#                                   passed the envelope nonce AND the
#                                   envelope hash is not sealed
#   write-off <tx_hash> --reason …  terminal write-off (reason required)
```

If the exercise ever needs a payout-account remediation (e.g. a monitor
lane hiccup while the island is up), it goes through these commands only.

## Observation checklist

- [ ] Both `BRIDGE_LOCK`s sealed on `bc-2`; records `pending`,
      `source_tx_hash` = lock txs.
- [ ] `bridge_block_header` mirrored ≥ Lock A height + 3 and ≥ Lock B
      height + 6; each lock block's `finality_confirmed`/
      `confirmation_count` satisfies its tier
      (`BRIDGE_MIN_CONFIRMATIONS` / `BRIDGE_FINALITY_BLOCKS`).
- [ ] Proofs submitted by the relayer carry ≥2 `validator_signatures`
      (from `block_metadata.attestations` — the failure mode that killed
      the 27251 attempt).
- [ ] Records `confirmed` with `target_tx_hash`; two `BRIDGE_RELEASE`s
      sealed on `bc-2-island-1`: `sender='bridge_release'`, unsigned at
      top level, `payload.bridge_signature` verifies against the
      island's `bridge_release_authority` (amounts 5,000 and
      30,000,000, recipient `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40`).
- [ ] Records `completed` on both chain stores.
- [ ] Identical release txs + state roots on hub1 and node1; identical
      recipient balance (36,005,000 units).
- [ ] No `v9_would_reject_*` counter movement attributable to the
      releases (the credits are `BRIDGE_*` types — exempt from the v9
      signature rule by design, and re-verified as bridge credits at
      apply/attestation).

## Abort / rollback / cleanup

- **Before the first lock is submitted:** abort = do nothing. The draft
  state has no chain footprint.
- **Between locks:** Lock A completing and Lock B never submitted is a
  clean end state — record the partial result; no cleanup needed.
- **Lock sealed, confirm keeps failing:** safe steady state — the record
  stays `pending` and retries each pass. Diagnose from the relayer log
  (`Insufficient finality`, `Threshold not met`, `Validator set …`,
  `proof has no merkle_proof`). Fix the cause or abandon the attempt.
- **Abandon a locked transfer:** `POST /rpc/bridge/unlock` (sender-signed)
  → `BRIDGE_REFUND` returns the locked amount on `bc-2`; record →
  `refunded`. Abandoning one lock leaves the other untouched; do not
  re-attempt the same `transfer_id`.
- **Release emitted but island stopped producing:** the preregistered
  credit waits in the island mempool; restore the island units on
  hub1/node1 — nothing to rewrite.
- **Payout-account involvement (only if the monitor lane was used for a
  companion step):** ledger-first commands above; `write-off` for a
  sealed-failed or lost row, `manual-payout` to pay what is still owed —
  never a raw send from `BRIDGE_PAYOUT_*`.

## Known failure modes (history)

- **"Threshold not met: 1/6 valid signers (need 2)"** — lock @27251
  (v0.25.8): the source block header carried only the proposer signature;
  `build_proof` harvests `validator_signatures` from
  `block_metadata.attestations`, which that topology did not produce. On
  `bc-2` (`MULTI_VALIDATOR_MIN_ATTESTATIONS=2`) blocks carry attestations —
  verify the lock block does before expecting confirm to pass.
- **Shadow-ledger target** — `ait-shop-island` had no block tables, so
  the release could never seal. `bc-2-island-1` is produced by its
  dedicated hub1 + node1 units — verify sealing before submitting.
- **Finality wait** — confirm can't pass until the lock block's stored
  header accumulates its tier's confirmations (3 for Lock A, 6 for
  Lock B); a couple of silent passes right after a lock seals is
  normal.

## Topology rule + incidents observed during the executed run

- **Lock intake lives on hub's RPC** — hub holds the sole
  `BRIDGE_RELEASE_PRIVATE_KEY` (K-1). Submit locks to hub's bc-2 RPC,
  then `scripts/ops/bridge-transplant.sh` moves the `pending` ledger
  row into hub1's bc-2 db and fires the rpc-island relay from there.
  **Not** co-located intake: `cross_chain_transfer` is rpc-local, so
  the island's own rpc unit is the only correct relayer for the
  island leg — Refs #662.
- **Incident — mis-relay (Refs #662):** the first lock attempt relayed
  from the wrong unit's rpc view — relayer scoping matters; the
  transplant script exists precisely because intake (hub, key
  custody) and relay (island co-located) live on different hosts.
- **Incident — hub1 drain-skip:** hub1's bc-2 rpc lacked the intake
  key needed for the transplanted row's relay, so its mempool drain
  skipped it — an intake-key prerequisite on the relayer host, caught
  and fixed during the run.

## Operator sign-off

- [ ] Parameters confirmed: `bc-2-island-1` topology (hub1 + node1
      dedicated units), Lock A `5,000` / Lock B `30,000,000`,
      sender = node0 `default`, recipient recorded (Phase 0)
- [ ] Preconditions verified (locks unpaused fleet-wide, island
      producing, post-8900 `BRIDGE_SUPPORTED_CHAINS` wiring done,
      env matrix identical, release count = 0)
- [ ] **Decision: APPROVED / NOT APPROVED**

    Operator: ______________  Date: __________  Notes: ______________
