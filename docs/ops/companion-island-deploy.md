# Companion island deploy — `bc-2-island-1` (RUNBOOK SKELETON)

> **Status: SKELETON — this is the locked design, not a deploy record.**
> Coder B's deploy lane annotates deltas post-deploy — this skeleton is
> the design, the deploy records what actually ran. Every value marked
> `<recorded at deploy>` is a placeholder the deploy lane fills in from
> the live run; anything that diverges from the design gets annotated
> here, not silently corrected. Refs #659.
>
> The consuming documents are
> [bridge-release-exercise.md](bridge-release-exercise.md) (governing
> runbook — its operator sign-off authorizes the live locks, this doc
> authorizes nothing) and
> [88_bridge_island_lock_release.md](../scenarios/88_bridge_island_lock_release.md)
> (the scenario play that fires them).

## What this deploys — the locked design

| item | locked value |
|---|---|
| chain id | `bc-2-island-1` |
| validators | **hub1 = island-proposer, node1 = island-validator** — 2-of-2 PBFT, island blocks carry `block_metadata.attestations` |
| units | `aitbc-i2-blockchain-node` + `aitbc-i2-blockchain-rpc` — **real unit files**, not symlinks to the bc-2 units (see the cardinal rule below) |
| ports | RPC **8302**, metrics **8309** (`AITBC_NODE_METRICS_PORT`, default 9009 — `observability/exporters.py:78`), gossip **8370** |
| data | `/var/lib/aitbc/data/bc-2-island-1/` — the **standard root** (`AITBC_DATA_DIR=/var/lib/aitbc`; operator correction — NO separate root, see below) |
| gossip | mesh ×2 — each island unit's `GOSSIP_MESH_PEER_URLS` points at the other island validator; **no redis** (no island-dedicated broker) |
| mempool | sqlite (`MEMPOOL_BACKEND` unset/sqlite — no postgres, no redis) |
| keys | **fresh island validator keys** — newly generated, never borrowed from a bc-2 host's `VALIDATOR_KEYS`/`PROPOSER_*` |
| transition heights | `STATE_TRANSITION_*_HEIGHT=1` for **all** versions — the island starts at v17 rules (newest code, no history to replay) |
| hub1 memory | node `MemoryMax=512M` / rpc `MemoryMax=256M` — hub1 is a small VPS; these are deploy limits, not fleet values |
| genesis | standard genesis builder — `scripts/ops/build-genesis.py` (over `aitbc_chain.genesis_builder`) + `scripts/ops/verify-genesis-root.py`, the same pair the reset harness drives (`scripts/reset-harness/rehearsal.py:392`) — seeding `bridge_validators` (trusting **bc-2's** set) + island-side `bridge_release_authority` |

## The cardinal safety rule — `%N.env` only, never bc-2's env files

The units are named `aitbc-i2-blockchain-node` /
`aitbc-i2-blockchain-rpc` because systemd expands `%N` to the unit name:
`EnvironmentFile=/etc/aitbc/%N.env` in the island unit files therefore
loads **only** `/etc/aitbc/aitbc-i2-blockchain-node.env` and
`/etc/aitbc/aitbc-i2-blockchain-rpc.env` respectively.

The stock bc-2 units (`apps/blockchain-node/aitbc-blockchain-node.service`,
`aitbc-blockchain-rpc.service`) load, in order, `%N.env` +
`blockchain.env` + `node.env` + `blockchain-secrets.env` +
`validator-secrets.env`. The island unit files must **not** inherit that
list: `blockchain.env`/`node.env` carry `CHAIN_ID=bc-2` and the bc-2
`SUPPORTED_CHAINS`/`BLOCK_PRODUCTION_CHAINS`, and the `*-secrets.env`
files carry **live bc-2 proposer keys**. Loading any of them would put
bc-2's identity and key material into the island process — the cardinal
safety rule of this deploy.

- The island units are real files (per
  [service-unit-symlinks.md](service-unit-symlinks.md), repo units
  install as symlinks into the checkout — the island units deliberately
  are **not** the repo units; their EnvironmentFile list is shorter).
- Exactly one env file each: `EnvironmentFile=/etc/aitbc/%N.env` —
  mode `600`, owner `aitbc` — holding every name the process needs,
  secrets included. Unit file paths: `<recorded at deploy>`.
- Key material (fresh `VALIDATOR_KEYS`/`PROPOSER_KEY`,
  `BRIDGE_RELEASE_PRIVATE_KEY`/`ESCROW_RELEASE_PRIVATE_KEY`) lives in
  the same `%N.env`; if B splits it into an
  `aitbc-i2-*-secrets.env`, that file is still `aitbc-i2-*`-scoped —
  record the split at deploy.
- `EnvironmentFile=` does not strip inline `#` comments — annotate on
  their own lines (repo convention, `AGENTS.md`).

## 1. Prerequisites

- [ ] hub1 + node1 on the intended commit, clean tree —
      `cd /opt/aitbc && git rev-parse HEAD && git status --porcelain`
      (a dirty checkout mutates the *bc-2* units that are symlinks into
      it — `service-unit-symlinks.md`).
- [ ] bc-2 healthy on both hosts — the island units' finalizer reads the
      shared bc-2 store (below); a stalled bc-2 stalls the mirror.
- [ ] bc-2 head past `STATE_TRANSITION_V17_HEIGHT` (8900) **before** the
      bc-2-side `BRIDGE_SUPPORTED_CHAINS` wiring in §6 — the v17 drift
      canary stays clean during the armed window
      ([v17-activation-runbook.md](v17-activation-runbook.md)); the
      island deploy itself is not gated on 8900, only the wiring is.
- [ ] Fresh island validator keypair ×2 generated and held in operator
      custody — new keys, not borrowed from any bc-2 host.
- [ ] Fresh island recipient address generated for the exercise —
      `recipient: <recorded at deploy>` — the release mints credit to
      it; the exercise runbook's Phase 0 consumes this value.

## 2. Genesis

Standard builder, same pair the reset harness drives:

```bash
# run from the repo venv so aitbc_chain imports; builder is scratch-only
# (refuses writes under /var/lib/aitbc — build to a scratch dir, then
# distribute the identical file to both hosts by hand)
PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/blockchain-node/src \
  /opt/aitbc/venv/bin/python scripts/ops/build-genesis.py \
    --manifest manifest.json \            # {"chain_id":"bc-2-island-1", "expected_total_units":<...>}
    --allocations allocations.json \      # treasury + floats + the two bond system accounts at 0
    --parameters parameters.json \        # bridge_release_authority=<island authority addr>, …
    --bridge-validators bridge-validators.json \  # [{address,public_key,epoch}] — trusting bc-2's set
    --data-dir <scratch>
/opt/aitbc/venv/bin/python scripts/ops/verify-genesis-root.py \
    <scratch>/data/bc-2-island-1/genesis.json
```

Locked inputs:

- `bridge_validators` rows = **bc-2's validator set** — the multisig
  check in `_validate_proof` resolves the set for the *source* chain, so
  the island genesis must carry the bc-2 rows it trusts
  (`BRIDGE_MULTISIG_THRESHOLD=2`); the island-side table is what
  `ensure_supported_chain_validators` checks at startup.
- `bridge_release_authority` = the island-side release authority
  (genesis `parameters` row — the emitted `BRIDGE_RELEASE`'s
  `payload.bridge_signature` verifies against it; the signing key lives
  in the island units' `%N.env`).
- The bond system accounts allocated at balance `0` (init rows win over
  funded allocations — the env-set doc's rehearsal evidence).
- **Custody invariant** (harness rule): every authority address baked
  into genesis must have its private key in operator custody before
  height 1 seals — `rehearsal.py:_check_authority_custody` enforces it
  in the harness; the deploy applies the same gate by hand.
- Identical `genesis.json` file-loaded on **both** island hosts —
  `/var/lib/aitbc/data/bc-2-island-1/genesis.json`. No RPC bootstrap:
  a node that bootstraps mints a local block-0 timestamp, the
  timestamp-derived proposer round disagrees, and every imported block
  fails the schedule check (env-set rehearsal item 1).

## 3. Units and env

Two real unit files per host — `aitbc-i2-blockchain-node.service`,
`aitbc-i2-blockchain-rpc.service` — derived from the stock units with:

- **EnvironmentFile list = `%N.env` only** (cardinal rule, above).
- `User=aitbc`, `WorkingDirectory=/opt/aitbc`, same `PYTHONPATH` —
  the island runs the same checkout; only env and ports differ.
- Memory limits (hub1 constraint): node `MemoryHigh`/`MemoryMax` =
  `512M`, rpc `MemoryHigh`/`MemoryMax` = `256M` — deploy limits,
  tighter than the stock units' 2G/512M.
- RPC unit binds `RPC_BIND_PORT=8302`; metrics exporter on the node
  unit reads `AITBC_NODE_METRICS_PORT=8309`; gossip endpoint **8370**
  — serving mechanism `<recorded at deploy>` (mesh peers dial the
  peer's `/rpc/gossip/ws`; whether 8370 is a dedicated listener or the
  bound port the peer URLs use is the one open wiring detail).

`aitbc-i2-blockchain-node.env` — the env set (one file per host; ports
identical on both, key material differs):

```bash
# identity — island only; the bc-2 store comes from the shared root
CHAIN_ID=bc-2-island-1
SUPPORTED_CHAINS=bc-2-island-1
BLOCK_PRODUCTION_CHAINS=bc-2-island-1
AITBC_DATA_DIR=/var/lib/aitbc           # standard root — see below

# the island finalizer must see BOTH stores: _known_chains() is the
# union of SUPPORTED_CHAINS + BRIDGE_SUPPORTED_CHAINS + CHAIN_ID
# (cross_chain/bridge_transfer.py:1062); bc-2 membership is what makes
# the finalizer mirror bc-2 headers and relay bc-2 locks island-side
BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1
BRIDGE_RELEASE_ENABLED=true
BRIDGE_REQUIRE_MERKLE_PROOF=true
BRIDGE_MULTISIG_ENABLED=true
BRIDGE_MULTISIG_THRESHOLD=2
BRIDGE_MULTISIG_VALIDATORS=<count trusting bc-2's set — recorded at deploy>
BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true

# consensus — 2-of-2 PBFT over the fresh island keys
MULTI_VALIDATOR_CONSENSUS_ENABLED=true
MULTI_VALIDATOR_MIN_ATTESTATIONS=2
PBFT_CONSENSUS_ENABLED=true            # island runs PBFT, unlike bc-2's attestation mode
VALIDATOR_SET=[{"address":"<island-val-1>","stake":1000},{"address":"<island-val-2>","stake":1000}]
VALIDATOR_KEYS={"<island-val-1>":"<key>","<island-val-2>":"<key>"}   # per-host scope
PROPOSER_ID=<this host's island validator address>                  # hub1 = island-proposer
PROPOSER_KEY=<key>
TRUSTED_PROPOSERS=genesis,<island-val-1>,<island-val-2>
ENABLE_BLOCK_PRODUCTION=true            # both island validators produce (2-of-2)

# gossip — mesh ×2, no island redis; the mesh local bus still needs a
# GOSSIP_BROADCAST_URL (broker.py:215 refuses mesh without it) —
# the host's existing redis is the bus; record the actual URL at deploy
GOSSIP_BACKEND=mesh
GOSSIP_MESH_PEER_URLS=ws://<other-island-host>:8370/rpc/gossip/ws
GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=256

# every transition height = 1 — newest rules from block 1, nothing replayed
STATE_TRANSITION_V2_HEIGHT=1   # … through V17 — ALL versions, recorded at deploy
BRIDGE_LOCK_LEAF_V2_HEIGHT=1

# ports / mempool / sync
RPC_BIND_HOST=<bind — recorded at deploy>   # 127.0.0.1 if gossip has its own 8370 listener
RPC_BIND_PORT=8302
AITBC_NODE_METRICS_PORT=8309
MEMPOOL_BACKEND=sqlite
P2P_NODE_ID=i2-<host>
BLOCK_TIME_SECONDS=60
MAX_EMPTY_BLOCK_INTERVAL=60
```

`aitbc-i2-blockchain-rpc.env` — same chain/store/bridge names (the RPC
process runs the finalizer and serves `/rpc/gossip/ws`), with
`ENABLE_BLOCK_PRODUCTION=false` and the same port set. Per-host deltas:
`<recorded at deploy>`.

**Why the standard root matters:** `AITBC_DATA_DIR=/var/lib/aitbc` puts
the island store at `data/bc-2-island-1/chain.db` *and* opens
`data/bc-2/chain.db` — the same file the host's bc-2 unit writes —
when the finalizer opens a session for `bc-2` (`_session_for` resolves
`DATA_DIR/data/<chain_id>/chain.db`). That shared store is how "the
island units host both stores" works; a separate data root would leave
the bc-2 store unreachable and `_chain_db_ready` would skip it.

## 4. Gossip / firewall

- `GOSSIP_MESH_PEER_URLS` lists exactly the other island validator —
  a two-node mesh; hub1 ↔ node1 connectivity on the gossip port
  (8370) is the only inter-host path the island needs.
- Firewall: open the gossip port **between hub1 and node1 only**;
  nothing else reaches the island (no fleet gossip, no public RPC).
  Rules applied: `<recorded at deploy>`.
- `GOSSIP_AUTH_ENABLED` stays default-true — the restricted topics
  (`blocks.*`, `pbft.*`, `consensus.*`) sign with the fresh island
  `PROPOSER_*` keys; the bc-2 keys are not in the file, which is also
  why nothing island-side can publish to bc-2 topics.
- No redis is stood up for the island; the mesh local-bus URL is
  recorded at deploy (host redis or in-process equivalent).

## 5. Seal gate — the island must produce before any lock fires

**Hard gate: `bc-2-island-1` must be sealing blocks before any
`BRIDGE_LOCK` is submitted on bc-2.** The release seals *on the island*
— a shadow ledger is the historical failure mode: lock @27251 targeted
`ait-shop-island`, which had `accounts` + `cross_chain_transfer` but no
block/transaction tables, so even a passed confirm had nowhere to seal
(`bridge-release-exercise.md` — known failure modes).

Verification (both hosts, before handoff):

```bash
systemctl is-active aitbc-i2-blockchain-node aitbc-i2-blockchain-rpc
curl -s http://127.0.0.1:8302/rpc/head | python3 -m json.tool   # height advancing
sqlite3 /var/lib/aitbc/data/bc-2-island-1/chain.db \
  "SELECT height,proposer,json_extract(block_metadata,'$.attestations') \
   FROM block ORDER BY height DESC LIMIT 3;"
#   → heights advancing, attestations ≥ 2 per block (2-of-2 PBFT —
#     also what the island's own blocks prove; lock proofs still draw
#     validator_signatures from bc-2's attestations)
```

The same gate is the exercise runbook's second hard precondition —
both sides check it; the deploy is not done until it holds.

## 6. bc-2-side wiring — post-8900 only

Held until the bc-2 head is past `STATE_TRANSITION_V17_HEIGHT` (8900)
so the v17 drift canary stays clean during the armed window —
[v17-activation-runbook.md](v17-activation-runbook.md). Coder A holds
this step; the island deploy records that it ran:

1. `BRIDGE_SUPPORTED_CHAINS=bc-2,bc-2-island-1` in
   `/etc/aitbc/blockchain.env` on **all five** bc-2 hosts.
2. Restart `aitbc-blockchain-rpc` on each — the **RPC unit only**; no
   producer restart (`/rpc/bridge/lock` admission is evaluated in the
   RPC process).
3. Do **not** touch `SUPPORTED_CHAINS`/`BLOCK_PRODUCTION_CHAINS` on the
   bc-2 units — the island is hosted only by its own units; bc-2-only
   nodes skip the island store in finalizer passes via
   `_chain_db_ready`.

Without the edit, `/rpc/bridge/lock` refuses
`target_chain=bc-2-island-1` at admission.

## 7. Handoff to the lock exercise

When the seal gate holds and §6's wiring is verified fleet-wide:

- Hand off to [bridge-release-exercise.md](bridge-release-exercise.md)
  Phase 1 → Phase 2 (the two locks fire under that runbook's operator
  sign-off, not this doc) and
  [88_bridge_island_lock_release.md](../scenarios/88_bridge_island_lock_release.md).
- Report the values the exercise consumes:
  `recipient: <recorded at deploy>` (fresh island address), the island
  RPC endpoint (`http://<host>:8302/rpc`), and the journal units the
  observation phases grep (`aitbc-i2-blockchain-node` on hub1/node1).

## Deploy record — filled by Coder B's lane

| value | design | as deployed |
|---|---|---|
| unit file paths | real files, `%N.env` only | `<recorded at deploy>` |
| env file paths | `/etc/aitbc/aitbc-i2-blockchain-{node,rpc}.env` (600) | `<recorded at deploy>` |
| island validator addresses | fresh ×2 (hub1 proposer, node1 validator) | `<recorded at deploy>` |
| recipient address | fresh island addr | `<recorded at deploy>` |
| `bridge_release_authority` | island-side authority | `<recorded at deploy>` |
| gossip 8370 serving mechanism | mesh peer endpoint | `<recorded at deploy>` |
| `GOSSIP_BROADCAST_URL` | host redis local bus | `<recorded at deploy>` |
| first sealed island height / tx | — | `<recorded at deploy>` |
| any port that diverged | 8302 / 8309 / 8370 | `<recorded at deploy>` |
