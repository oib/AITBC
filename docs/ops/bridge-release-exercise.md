# BRIDGE_RELEASE live exercise — runbook (DRAFT FOR APPROVAL)

> **Status: DRAFT — awaiting operator approval.** Writing this runbook
> authorizes nothing. V-1 waived live exercises for all 22
> fixture-replayable types but explicitly reserved the one live
> `BRIDGE_RELEASE` exercise "pending operator approval" — see
> [What is NOT waived](../decisions/v1-v9-live-exercise-waivers.md#what-is-not-waived).
> This document ends at an **approved / not approved** decision, not at
> execution.

## What this exercise is (and is not)

This runbook covers the **protocol-lane** `BRIDGE_RELEASE`: a cross-chain
`BRIDGE_LOCK` on `bc-2` whose relay produces an authority-signed
`BRIDGE_RELEASE` credit that seals in a block on the **target chain**
(`apps/blockchain-node/src/aitbc_chain/cross_chain/bridge_transfer.py`,
`bridge_finality.py`).

It is a **different path** from the ETH-side deposit payout lane
(`apps/bridge-monitor`, `BRIDGE_PAYOUT_*`, `TRANSFER` envelopes,
`scripts/ops/bridge-admin.sh`). Nothing in this exercise moves ETH-side
money; the ledger-first payout rules below apply only if a companion step
touches that lane.

## Goal — what a green run proves

One `BRIDGE_LOCK` → one `BRIDGE_RELEASE`, exercised end to end on the live
fleet:

1. **Monitor detection** — `aitbc-blockchain-node`'s finalizer loop
   (`start_finalizer`, `bridge_monitor_interval` = 60 s) mirrors the
   source chain's sealed headers into `bridge_block_header`
   (`_sync_local_chain_headers`) and notices the locked transfer.
2. **Proof + full validation** — `_relay_pending_transfers` builds the
   real Merkle inclusion proof (`build_proof`: `merkle_proof`,
   `lock_event`, `bridge_state_root`, `proposer_signature`,
   `validator_signatures` lifted from
   `block.block_metadata.attestations`) and `confirm_transfer` runs the
   full `_validate_proof` chain — field match, leaf binding, stored-header
   check, proposer signature, Merkle verification
   (`BRIDGE_REQUIRE_MERKLE_PROOF=true`), finality
   (`BRIDGE_MIN_CONFIRMATIONS=3` below
   `BRIDGE_LARGE_TRANSFER_THRESHOLD`), and the multisig threshold
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
- Sustained relay throughput, multiple concurrent locks, or the F5
  `BRIDGE_LOCKS_PAUSED` unpause itself (a precondition, not the subject).
- Anything about the v9/v17 signature rules — a `BRIDGE_RELEASE` block
  proves the bridge path, not protocol-transfer policy.

## Preconditions

### Hard gates — all must hold before any lock is submitted

- [ ] **`BRIDGE_LOCKS_PAUSED=false` on `bc-2`.** The chain launched paused
      (`bc2-environment-set.md`: "Stay paused until redeploy"); the
      unpause is the separate gated F5 step after `SEPOLIA-REDEPLOY-1`.
      With the pause on, `/rpc/bridge/lock` refuses with 503.
- [ ] **A produced companion chain exists as the release target.**
      `initiate_transfer` refuses same-chain locks, and the release only
      seals if the target chain *produces blocks*. The historical attempt
      (lock @27251 on `ait-hub`, target `ait-shop-island`) died here: the
      island was a shadow ledger — `accounts` + `cross_chain_transfer`
      only, no block/transaction tables — so even a passed confirm had
      nowhere to seal. The island needs its own genesis, block production
      on at least two of the four bc-2 validators (so its blocks carry
      `block_metadata.attestations` too), and hosting
      (`SUPPORTED_CHAINS`) on the node that runs the confirming
      finalizer.
- [ ] **The bc-2 `bridge_validators` set is populated** (genesis-seeded;
      verified by `ensure_supported_chain_validators` at startup —
      `BRIDGE_MULTISIG_VALIDATORS=4` is only the fence count
      `N ≥ threshold`, membership comes from the table rows).
- [ ] **Every host on the intended commit or newer**, `bridge` env
      matrix identical fleet-wide (`fleet-config-check.sh`).

### Confirm the path is armed but unexercised

```bash
# env matrix on the exercising node + the island's producers
grep -h '^BRIDGE_\|^MULTI_VALIDATOR_\|^SUPPORTED_CHAINS\|^BLOCK_PRODUCTION_CHAINS' \
  /etc/aitbc/blockchain.env /etc/aitbc/bridge-validator-keys.env 2>/dev/null | sort

# expected on bc-2 (from docs/deployment/bc2-environment-set.md):
#   BRIDGE_RELEASE_ENABLED=true            BRIDGE_LOCKS_PAUSED=false (post-F5)
#   BRIDGE_SUPPORTED_CHAINS=bc-2,<island>  BRIDGE_REQUIRE_MERKLE_PROOF=true
#   BRIDGE_MULTISIG_ENABLED=true           BRIDGE_MULTISIG_THRESHOLD=2
#   BRIDGE_MULTISIG_VALIDATORS=4           BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true
#   BRIDGE_LOCK_LEAF_V2_HEIGHT=1           BRIDGE_MAX_LOCK_AMOUNT=36000000000
#   MULTI_VALIDATOR_CONSENSUS_ENABLED=true MULTI_VALIDATOR_MIN_ATTESTATIONS=2

# unexercised: no BRIDGE_RELEASE has ever sealed on the island
sqlite3 /var/lib/aitbc/data/<island>/chain.db \
  "SELECT count(*) FROM transaction WHERE type='BRIDGE_RELEASE';"     # → 0
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT status, count(*) FROM cross_chain_transfer GROUP BY status;" # → empty
curl -s http://127.0.0.1:8202/rpc/bridge/pending | python3 -m json.tool # → []
```

### Node / wallet / authority roles

| role | who | notes |
|---|---|---|
| exercising node | operator pick — recommend **hub** | runs the finalizer pass that confirms; must host both `bc-2` and `<island>` stores |
| lock submitter | funded bc-2 wallet (operator's canary/ops wallet) | signs the replay-guarded lock body (`issued_at`+`nonce`) — `aitbc bridge lock --wallet-name` generates them |
| recipient | address on `<island>` | the release mints credit to it |
| authority key | `BRIDGE_RELEASE_PRIVATE_KEY` / `ESCROW_RELEASE_PRIVATE_KEY` env on the exercising node | signs the credit; verified against the `bridge_release_authority` chain parameter (bc-2 keeps the live authority per the env-set ruling) |
| island producers | ≥2 of the 4 bc-2 validators | `BLOCK_PRODUCTION_CHAINS` extended with `<island>`; their blocks carry the attestation signatures the threshold needs |

### Open parameters — operator must fix before execution

- `<island>` chain id and host layout (recommend: produced by all four
  bc-2 validators, hosted on all five hosts — gives replay evidence on
  every node).
- Lock amount in compute-units (≤ `BRIDGE_MAX_LOCK_AMOUNT` = 1000 AIT).
  Note the finality path is effectively fixed:
  `BRIDGE_LARGE_TRANSFER_THRESHOLD` = 10000 **raw units** (~0.00028 AIT)
  — any realistic lock is "large" and waits for
  `BRIDGE_FINALITY_BLOCKS` = 6 confirmations; the lighter
  `BRIDGE_MIN_CONFIRMATIONS` = 3 path only serves dust below the
  threshold (`bridge_finality.py:_check_finality_for_transfer`).
- Sender wallet, recipient address, exercising node.

## Procedure

### Phase 0 — record the parameters

Fill in: `<island>` id, `<amount>`, `<sender>`, `<recipient>`,
`<exercising-node>`. Note current bc-2 head height for the evidence log.

### Phase 1 — companion island standing (skip if already standing)

- `<island>` in `SUPPORTED_CHAINS` + `BRIDGE_SUPPORTED_CHAINS` on every
  host, in `BLOCK_PRODUCTION_CHAINS` on its producers; serial restarts
  (validator restart rules apply — one at a time, attestations observed).
- `data/<island>/chain.db` exists and blocks are sealing
  (`curl -s http://127.0.0.1:8202/rpc/head` on the island's RPC or the
  node's multi-chain head endpoint).
- `bridge_release_authority` resolvable for `<island>` (chain parameter
  or env fallback to `BRIDGE_RELEASE_AUTHORITY`/`ESCROW_SETTLEMENT_AUTHORITY`).

### Phase 2 — submit the lock (operator or delegated agent)

```bash
aitbc bridge lock --rpc-url http://127.0.0.1:8202/rpc \
  --target-chain <island> \
  --sender <sender> --recipient <recipient> --amount <amount> \
  --wallet-name <wallet>
```

- Submit against a node that **produces bc-2** (`initiate_transfer`
  rejects lock submissions on followers for chains not in their
  `BLOCK_PRODUCTION_CHAINS`).
- Record the returned transfer id / tx hash. Expected: `BRIDGE_LOCK`
  row in bc-2 mempool → sealed in a bc-2 block → `cross_chain_transfer`
  row `status='pending'`, `source_tx_hash` set.

### Phase 3 — observe detection → confirm (finalizer, automatic)

```bash
journalctl -u aitbc-blockchain-node --since "-10min" | \
  grep -iE 'bridge (relayer|header|finaliz)|confirm'
sqlite3 /var/lib/aitbc/data/bc-2/chain.db \
  "SELECT transfer_id,status,target_tx_hash FROM cross_chain_transfer;"
```

Expected within a few `bridge_monitor_interval` (60 s) passes after the
lock block reaches `BRIDGE_FINALITY_BLOCKS` (6) confirmations — the
3-confirmation `BRIDGE_MIN_CONFIRMATIONS` path applies only to
sub-threshold dust (see open parameters):

- `bridge_block_header` rows for `bc-2` mirror past the lock height.
- `Bridge relayer: confirm …` / `Relayed 1 bridge transfers on chain bc-2`.
- Record → `status='confirmed'`, `target_tx_hash` = the emitted release
  tx hash. Failures stay `pending` and retry every pass — an intermediate
  state, not a stuck row.

### Phase 4 — observe seal → completed

```bash
sqlite3 /var/lib/aitbc/data/<island>/chain.db \
  "SELECT tx_hash,block_height,sender,recipient,type FROM transaction \
    WHERE type='BRIDGE_RELEASE';"
sqlite3 /var/lib/aitbc/data/<island>/chain.db \
  "SELECT status FROM cross_chain_transfer WHERE transfer_id='<id>';"   # → completed
curl -s http://127.0.0.1:8202/rpc/bridge/transfer/<id> | python3 -m json.tool
```

- The release seals in an `<island>` block; the record flips to
  `completed` on the next finalizer pass (also mirrored onto the bc-2
  record).
- Capture: release tx hash, sealed height, block hash, and the sealed
  `payload` (`transfer_id`, `source_chain`, `source_sender`,
  `target_chain`, `amount`, `asset`, `proof` = proof hash,
  `bridge_signature`).

### Phase 5 — replay determinism

- On every host serving `<island>`: confirm the release tx and its block
  exist with identical `state_root`/`aux_state_root` at the sealed
  height (`/rpc/blocks-range` or the chain store), and the recipient's
  balance delta is identical.
- `sqlite3` the `account` row for `<recipient>` on each host — same
  balance everywhere.

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

- [ ] `BRIDGE_LOCK` sealed on `bc-2`; record `pending`,
      `source_tx_hash` = lock tx.
- [ ] `bridge_block_header` mirrored ≥ lock height + 3; the lock block's
      `finality_confirmed`/`confirmation_count` satisfies
      `BRIDGE_MIN_CONFIRMATIONS`.
- [ ] Proof submitted by the relayer carries ≥2 `validator_signatures`
      (from `block_metadata.attestations` — the failure mode that killed
      the 27251 attempt).
- [ ] Record `confirmed` with `target_tx_hash`; `BRIDGE_RELEASE` sealed
      on `<island>`: `sender='bridge_release'`, unsigned at top level,
      `payload.bridge_signature` verifies against the release authority.
- [ ] Record `completed` on both chain stores.
- [ ] Identical release tx + state roots on every host serving `<island>`;
      identical recipient balance.
- [ ] No `v9_would_reject_*` counter movement attributable to the release
      (the credit is a `BRIDGE_*` type — exempt from the v9 signature rule
      by design, and re-verified as a bridge credit at apply/attestation).

## Abort / rollback / cleanup

- **Before the lock is submitted:** abort = do nothing. The draft state
  has no chain footprint.
- **Lock sealed, confirm keeps failing:** safe steady state — the record
  stays `pending` and retries each pass. Diagnose from the relayer log
  (`Insufficient finality`, `Threshold not met`, `Validator set …`,
  `proof has no merkle_proof`). Fix the cause or abandon the attempt.
- **Abandon a locked transfer:** `POST /rpc/bridge/unlock` (sender-signed)
  → `BRIDGE_REFUND` returns the locked amount on `bc-2`; record →
  `refunded`. Do not re-attempt the same `transfer_id`.
- **Release emitted but island stopped producing:** the preregistered
  credit waits in the island mempool; restore the island's producers —
  nothing to rewrite.
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
  the release could never seal. The `<island>` here must be produced.
- **Finality wait** — confirm can't pass until the lock block's stored
  header accumulates `BRIDGE_MIN_CONFIRMATIONS` (3); a couple of silent
  passes right after the lock seals is normal.

## Operator sign-off

- [ ] Open parameters fixed: `<island>` id + topology, `<amount>`,
      `<sender>`, `<recipient>`, exercising node
- [ ] Preconditions verified (F5 unpaused, island producing, env matrix
      identical, release count = 0)
- [ ] **Decision: APPROVED / NOT APPROVED**

    Operator: ______________  Date: __________  Notes: ______________
