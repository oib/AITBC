# V-5 replay inventory — 2026-09-30

> Tracked copy of the V-5 replay inventory (sanitized; TOPOLOGY keeps
> the scratch original).

Prep work for V-5 (checkpoint replay / honest bootstrap). Read-only inventory +
one bounded verification run on node2. No validators touched; the v9 window was
unaffected (run happened on node2, in /tmp, against snapshot copies).

## Inputs `scripts/ops/replay-chain.py` expects

```
PYTHONPATH=apps/blockchain-node/src venv/bin/python scripts/ops/replay-chain.py \
  --snapshot <chain.db copy, opened ro+immutable> \
  --genesis  <genesis.json — ALLOCATION SET ONLY> \
  --chain-id ait-hub.aitbc.bubuit.net \
  --env-file <merged env — see below> [--to-height N] [--keep --workdir DIR]
```

- Replays blocks 1..tip through `ChainSync.bulk_import_from` → `import_block`
  with `SYNC_STATE_ROOT_VALIDATION_ENABLED=true` — first divergence aborts and
  `height: DIVERGED` prints want/got hash+state_root.
- Block 0 comes from the SNAPSHOT verbatim (hash, state_root); genesis.json is
  used **only** for the allocation account set + chain parameters. A hash
  mismatch between the file and snapshot block 0 is a warning, not fatal.
- Consensus knobs are force-disabled in replay (no attestation/quorum) — proposer
  signatures still verify. The "authority parameter … not set; lenient branch"
  warnings are expected for pre-v5 history.
- Backup files under `/var/backups/aitbc/<ts>/` are **gzipped SQL dumps**, not
  binary DBs: materialize with `gunzip -c file.gz | sqlite3 out.db`.

## Verified inputs (2026-09-30)

| input | value | status |
|---|---|---|
| snapshot | `hub:/var/backups/aitbc/20260828_010035/chain_ait-hub.aitbc.bubuit.net_chain.db.gz` — oldest complete post-migration backup, blocks 0–122, 160 tx | verified (materializes + replays) |
| genesis | `hub1:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net-pre-0x-migration-20260828-075825/genesis.json` — 16 allocations, block hash `0xd95e600b…` = live block 0 | **verified** — wrong allocations would diverge at block 1; replay was clean through block 10 |
| env | merged file: `cat node.env aitbc-blockchain-node.env blockchain.env` (secrets stripped) — see caveat | verified faithful (same divergence with heights-only vs full merge) |

The staged copy on node2 is at `/tmp/v5-inv/` (`chain-0828.db`,
`genesis-candidate.json`, `merged-node.env`).

**Stale genesis files**: every `data/<chain>/genesis.json` on the fleet carries
`40ea48f9…`, 1 allocation, `state_root 0x00` — the abandoned pre-migration
genesis; none reproduce live block-0 root `0x448ab9e8…`.

## Env-height caveat (the v3 trap)

| version | env | code default | effective |
|---|---|---|---|
| v2 | 0 (dozens of env files) | 0 | 0 |
| **v3** | **5470 (`blockchain.env` on all 5 hosts)** | **0** | **5470** |
| v4 | — | 11000 | 11000 |
| v5 | — | 24000 | 24000 |
| v6 | — | 0 | 0 (gate disabled) |
| v7 | — | 24650 | 24650 |
| v8 | — | 24800 | 24800 |
| v9 | — | None | None (shadow) |

`--env-file` takes ONE file but `STATE_TRANSITION_V3_HEIGHT` lives in
`blockchain.env`, not `aitbc-blockchain-node.env`. Replay MUST get a merged env:
`_load_env_file` is first-wins, systemd EnvironmentFile is last-wins →
concatenate in reverse precedence order (`node.env` + `%N.env` + `blockchain.env`).
Replaying without it silently applies v3 rules from height 0 → divergence.

## FINDING: genesis replay diverges at height 11 — v1 model is wrong

Replay of the 08-28 snapshot (full merged env, verified genesis) fails at
**height 11**: first TRANSFER to a non-genesis recipient
(`0xFe2d…` → `0xd3d4362840AC0727EEC41570b0b69CF8313E740B`, 36000 units).

Root cause (verified against history):

- Recording-era import path (`602ba8a45f`, Aug 27) created missing sender and
  recipient accounts **unconditionally** in `sync_block_import.py` before apply
  (sender skipped for faucet/bridge_release/bridge_refund; recipient skipped for
  bridge_lock).
- The Sep-3 version gate `b6f43f6eb7` modeled v1 as "no auto-created
  recipient/provider accounts" and applied `block_version >= 2` gates to the
  same creation block — but the actual genesis-era chain DID create recipients
  at import (account `updated_at` stamps land ~100 ms after each first-credit
  block's seal — insert-at-apply, not off-chain `/register-account`).
- Net: replay v1 never creates `0xd3d436…`; the transfer's credit no-ops while
  the recorded root includes it → divergence at 11 on the first new-recipient
  tx. All blocks 1–10 replayed hash+root identical.

**Fix direction** (post-window, apply-path semantics — needs replay to prove):
import-time sender/recipient creation for v1 must mirror the Aug-27 code
(create always, with the same pseudo-sender exemptions). After that, iterate:
the next era boundaries (v3 custody at 5470, parallel-era blocks ~24000+,
v5/v7/v8) may expose further divergences — each is a separate bisect.

**This does NOT gate the v9 pin**: it concerns replay fidelity for already-sealed
v1-era blocks; v9 rules evaluate identically regardless. Record it as the first
known replay break for the V-5 work item.

## Backup inventory (chain = ait-hub.aitbc.bubuit.net)

- **Daily gzipped dumps** on all 5 nodes under `/var/backups/aitbc/<date>/`,
  continuous from Aug 28 → Sep 29 (earliest live-chain: `20260828_010035`,
  122 blocks; node2/hub1 also hold Aug-09 dumps which are the PRE-migration
  chain — unusable for the live chain).
- **Uncompressed full snapshots**:
  hub `/var/lib/aitbc/backups/chain.db.before_pbft.2026-09-01-124219.bak`,
  hub `/var/lib/aitbc/backups/pre-deploy-20260907/chain.db` (also hub1/node0/node1),
  node2 `…/chain.db.pre-snapshot.20260927-210059`,
  all nodes `…/chain.db.bak-20260928-27207wedge` (63.7 MB).
- Live DBs ~68.5 MB on all five hosts as of today.

## Plan change (2026-09-30): checkpoint replay, not genesis-to-tip

The genesis replay proved the inputs but failed at height 11 on a
historical-parity gap — and blocks 5470/11000/24000-era rules may each hide
another. Modeling all pre-checkpoint history is the wrong blast radius for
V-5. Revised strategy (operator direction):

**Replay forward from a state-bearing checkpoint whose root is trusted, and
verify each later block's recorded root.** A backup's `chain.db` IS a
checkpoint: blocks up to its tip plus the full account/aux state at that
tip. The backup chain itself supplies the checkpoints:

- `20260828_010035` dump → state@122 (earliest post-migration)
- `chain.db.before_pbft.2026-09-01-124219.bak` → pre-PBFT state
- `pre-deploy-20260907/chain.db` → Sep-7 state
- `chain.db.pre-snapshot.20260927-210059` / `.bak-20260928-27207wedge` →
  near-tip state

Needed tooling: a `--checkpoint`/`--from-height` mode in
`replay-chain.py` — seed the workdir DB verbatim from the checkpoint
snapshot (blocks AND state tables), then apply blocks H+1..N read from a
second source (a live-DB copy or the next backup) and compare each recorded
root.

**Verify the seed before trusting it.** Recompute the state root from the
seeded account table and compare it against the recorded root at the
checkpoint height — a silently wrong backup would otherwise poison every
block after it. Then use the ladder itself as the test: replay checkpoint A
forward to checkpoint B's height and compare the resulting accounts against
backup B's state wholesale — a complete check that does not depend on
getting the early-era rules right at all.

Two layers of verification fall out:

1. **Per-block roots** H+1..N against the block source.
2. **Checkpoint-to-checkpoint**: replay only to the next backup's tip and
   compare the resulting account/aux state wholesale — bounds each era
   independently and names the exact block range that diverges.

Suggested order: newest checkpoint backward is wrong (shortest coverage
wins correctness last); start at the oldest checkpoint that postdates the
era under test, or run the ladder 122 → Sep-1 → Sep-7 → Sep-27 → tip so a
divergence is attributed to exactly one era.

The v1 creation fix (import-time recipient creation mirroring `602ba8a45f`)
then becomes **nice-to-have for proving heights 11–122** rather than a V-5
blocker — blocks 1–10 already verify, 11+ is only reachable via the genesis
path. If the era-ladder is clean end to end, the residual question is
exactly that 122-block window.

## Mechanical recipe (checkpoint replay — implemented as `--checkpoint`)

```bash
# 1. materialize the oldest checkpoint dump
gunzip -c backup/chain.db-20260828_010035.sql.gz > /tmp/ckpt-122.db   # or .backup on the live file

# 2. snapshot a block source covering the range to verify
ssh hub 'sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
    ".backup /tmp/chain-live.db"' && scp hub:/tmp/chain-live.db /tmp/

# 3. env: merge per precedence (secrets stripped) — needed even though
#    post-checkpoint blocks are versioned; replay still applies code
ssh hub 'cat /etc/aitbc/node.env /etc/aitbc/aitbc-blockchain-node.env /etc/aitbc/blockchain.env' \
    | grep -vE 'KEY|SECRET|TOKEN|PASSWORD|PASS|MNEMONIC|SEED' > /tmp/replay.env

# 4. run on a dev node (node2): the checkpoint DB is copied into the replay
#    target wholesale; its tip C seeds state and replay runs C+1..tip.
#    Lineage, state-bearing root proof, and a post-seed root re-check all
#    gate the first import.
PYTHONPATH=apps/blockchain-node/src venv/bin/python scripts/ops/replay-chain.py \
    --checkpoint /tmp/ckpt-122.db --snapshot /tmp/chain-live.db \
    --chain-id ait-hub.aitbc.bubuit.net --env-file /tmp/replay.env

# 5. ladder step — replay to the NEXT checkpoint's tip and compare the
#    rebuilt non-history state wholesale against that checkpoint file:
PYTHONPATH=apps/blockchain-node/src venv/bin/python scripts/ops/replay-chain.py \
    --checkpoint /tmp/ckpt-122.db --snapshot /tmp/chain-live.db \
    --to-height <tip-of-next-backup> --compare-state-with /tmp/ckpt-sep01.db \
    --chain-id ait-hub.aitbc.bubuit.net --env-file /tmp/replay.env
```

Note: the planned `--from-height` flag did not get implemented — the
checkpoint DB's own tip IS the start height, which cannot disagree with the
file's actual state the way a separate height argument could.
