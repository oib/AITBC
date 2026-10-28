# Companion island deploy — `bc-2-island-1` (RUNBOOK + DEPLOY RECORD)

> **Status: DEPLOYED — this doc now carries the verified actuals from
> Coder B's deploy; it remains the design record.** Every `<recorded at
> deploy>` placeholder has been filled from the live run, and anything
> that diverged from the locked design is annotated inline below, not
> silently corrected. Headline deltas: the real units are
> `aitbc-blockchain-node-island` / `aitbc-blockchain-rpc-island` (not
> the spec'd `aitbc-i2-*`), gossip has no dedicated 8370 listener — the
> mesh dials the nginx `/island/` proxy, the only inter-host channel —
> and the mesh local bus is the host redis rebased to db 9 (the
> skeleton said "no redis"). Refs #659.
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
| validators | **hub1 = island-proposer `0xc64117A4…9759`, node1 = island-validator `0xA40C46F8…F5f5`** — 2-of-2 PBFT, island blocks carry `block_metadata.attestations` |
| units | `aitbc-i2-blockchain-node` + `aitbc-i2-blockchain-rpc` — **real unit files**, not symlinks to the bc-2 units (see the cardinal rule below). **Deploy delta:** deployed names are `aitbc-blockchain-node-island` + `aitbc-blockchain-rpc-island`, not the `aitbc-i2-*` spec |
| ports | RPC **8302**, metrics **8309** (`AITBC_NODE_METRICS_PORT`, default 9009 — `observability/exporters.py:78`), gossip **8370** |
| data | `/var/lib/aitbc/data/bc-2-island-1/` — the **standard root** (`AITBC_DATA_DIR=/var/lib/aitbc`; operator correction — NO separate root, see below) |
| gossip | mesh ×2 — each island unit's `GOSSIP_MESH_PEER_URLS` points at the other island validator. **Deploy deltas:** no dedicated 8370 listener was stood up — the peers dial the nginx `/island/` path (the only inter-host channel); and the mesh local bus uses the host's existing redis **rebased to db 9** (the design said "no redis" — a dedicated island broker is still absent, but the bus does ride the host redis) |
| mempool | sqlite (`MEMPOOL_BACKEND` unset/sqlite — no postgres) — as deployed: the sqlite mempool sits beside the island `chain.db` |
| keys | **fresh island validator keys** — newly generated, never borrowed from a bc-2 host's `VALIDATOR_KEYS`/`PROPOSER_*` |
| transition heights | `STATE_TRANSITION_*_HEIGHT=1` for **all** versions — the island starts at v17 rules (newest code, no history to replay) |
| hub1 memory | node `MemoryMax=512M` / rpc `MemoryMax=256M` — hub1 is a small VPS; these are deploy limits, not fleet values. As deployed: the caps were **lowered to these values post-deploy** and confirmed live |
| genesis | standard genesis builder — `scripts/ops/build-genesis.py` (over `aitbc_chain.genesis_builder`) + `scripts/ops/verify-genesis-root.py`, the same pair the reset harness drives (`scripts/reset-harness/rehearsal.py:392`) — seeding `bridge_validators` (trusting **bc-2's** set) + island-side `bridge_release_authority`. As deployed: `genesis_hash 0x4a55d897…`, `state_root 0x329bd94e…`, byte-identical `genesis.json` at `/var/lib/aitbc/data/bc-2-island-1/genesis.json` on both hosts |

## The cardinal safety rule — `%N.env` only, never bc-2's env files

The units are named `aitbc-blockchain-node-island` /
`aitbc-blockchain-rpc-island` (deploy delta — the design spec'd
`aitbc-i2-blockchain-*`) because systemd expands `%N` to the unit name:
`EnvironmentFile=/etc/aitbc/%N.env` in the island unit files therefore
loads **only** `/etc/aitbc/aitbc-blockchain-node-island.env` and
`/etc/aitbc/aitbc-blockchain-rpc-island.env` respectively.

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
  secrets included. Unit file paths as deployed:
  `/etc/systemd/system/aitbc-blockchain-node-island.service` and
  `/etc/systemd/system/aitbc-blockchain-rpc-island.service`.
- Key material (fresh `VALIDATOR_KEYS`/`PROPOSER_KEY`,
  `BRIDGE_RELEASE_PRIVATE_KEY`/`ESCROW_RELEASE_PRIVATE_KEY`) lives in
  the same `%N.env`. As deployed: the custody keyset is held at
  `/etc/aitbc/credentials/bc-2-island-1.keys.json` (mode `600`) —
  every authority baked into genesis is recorded there.
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
      `recipient: 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` (recorded
      at island deploy; 10 AIT genesis alloc) — the release mints credit
      to it; the exercise runbook's Phase 0 consumes this value.

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
- **KNOWN TRAP (live-verified + resolved 28 Oct):** serving a chain_id
  before its real validator set is registered backfills the LOCAL set
  under that id — on the 12:54:58 rpc restart,
  `ensure_supported_chain_validators` installed bc-2's local 4
  validators under `chain_id='bc-2-island-1'` in the bc-2 `chain.db`s.
  **Cleanup:** the phantoms were **deleted** on hub/hub1/node0/node2
  (4 each; node1 was never polluted — the backfill raced the real
  registrations there), restoring `bc-2`=4 + `bc-2-island-1`=2 rows.
  Deactivation would NOT have worked: `load_validator_set`
  (`cross_chain/bridge_validator.py:139-150`) has **no `is_active`
  filter** — deactivated rows still count toward verification, so
  removal requires `DELETE`. Sequence rule: register the real set
  **before** adding the chain to
  `SUPPORTED_CHAINS`/`BRIDGE_SUPPORTED_CHAINS`, or `DELETE` the phantom
  rows post-registration. Refs #659.
- **I-2 registration notes (as run):** `target_chain_id` binds the
  *destination* node's chain — registration payloads for
  `bc-2-island-1` posted to bc-2 nodes needed
  `target_chain_id=bc-2`. The bridge admin key is workstation-custody:
  the `BOND_SLASH_PRIVATE_KEY` source line in `bridge-reg-run.env` is
  stale and derives `0x9aCC…` — do not source it for admin signatures.
  node1's pre-existing bc-2 replica gap closed inside I-2 (0 → real 4
  rows under `bc-2`) — it had been silently degrading node1's own
  bridge verification.
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

Two real unit files per host — deployed as
`aitbc-blockchain-node-island.service`,
`aitbc-blockchain-rpc-island.service` (design spec'd `aitbc-i2-*`;
same `%N.env` mechanism) — derived from the stock units with:

- **EnvironmentFile list = `%N.env` only** (cardinal rule, above).
- `User=aitbc`, `WorkingDirectory=/opt/aitbc`, same `PYTHONPATH` —
  the island runs the same checkout; only env and ports differ.
- Memory limits (hub1 constraint): node `MemoryHigh`/`MemoryMax` =
  `512M`, rpc `MemoryHigh`/`MemoryMax` = `256M` — deploy limits,
  tighter than the stock units' 2G/512M.
- RPC unit binds `RPC_BIND_PORT=8302`; metrics exporter on the node
  unit reads `AITBC_NODE_METRICS_PORT=8309`; gossip endpoint **8370**
  — **deploy delta:** no dedicated 8370 listener was stood up. As
  deployed, the mesh peers dial the peer's nginx `/island/` path,
  which proxies to `127.0.0.1:8302` on both island vhosts — the public
  nginx path is the **only** inter-host channel the island uses.

`aitbc-blockchain-node-island.env` — the env set (one file per host;
ports identical on both, key material differs):

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
BRIDGE_MULTISIG_VALIDATORS=4          # trusting bc-2's 4-validator set — recorded at deploy
BRIDGE_LOCK_REQUIRE_REPLAY_GUARD=true

# consensus — 2-of-2 PBFT over the fresh island keys
MULTI_VALIDATOR_CONSENSUS_ENABLED=true
MULTI_VALIDATOR_MIN_ATTESTATIONS=2
PBFT_CONSENSUS_ENABLED=true            # island runs PBFT, unlike bc-2's attestation mode
# recorded at deploy: hub1 = 0xc64117A4…9759 (island-proposer),
# node1 = 0xA40C46F8…F5f5 (island-validator)
VALIDATOR_SET=[{"address":"0xc64117A4…9759","stake":1000},{"address":"0xA40C46F8…F5f5","stake":1000}]
VALIDATOR_KEYS={"0xc64117A4…9759":"<key>","0xA40C46F8…F5f5":"<key>"}   # per-host scope
PROPOSER_ID=<this host's island validator address>                  # hub1 = 0xc64117A4…9759
PROPOSER_KEY=<key>
TRUSTED_PROPOSERS=genesis,0xc64117A4…9759,0xA40C46F8…F5f5
ENABLE_BLOCK_PRODUCTION=true            # both island validators produce (2-of-2)

# gossip — mesh ×2; the mesh local bus still needs a
# GOSSIP_BROADCAST_URL (broker.py:215 refuses mesh without it).
# Deploy delta: the bus is the host's existing redis REBASED to db 9
# (design said "no redis"); and no 8370 listener exists — peers dial
# the nginx /island/ path → 127.0.0.1:8302 (the only inter-host channel)
GOSSIP_BACKEND=mesh
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379/9     # recorded at deploy
GOSSIP_MESH_PEER_URLS=ws://<other-island-host>/island/rpc/gossip/ws   # via nginx, recorded at deploy
GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP=256

# every transition height = 1 — newest rules from block 1, nothing replayed
STATE_TRANSITION_V2_HEIGHT=1   # … through V17 — ALL versions = 1, recorded at deploy
BRIDGE_LOCK_LEAF_V2_HEIGHT=1

# ports / mempool / sync
RPC_BIND_HOST=127.0.0.1   # recorded at deploy — gossip reaches it via the nginx /island/ proxy
RPC_BIND_PORT=8302
AITBC_NODE_METRICS_PORT=8309
MEMPOOL_BACKEND=sqlite
P2P_NODE_ID=i2-<host>
BLOCK_TIME_SECONDS=60
MAX_EMPTY_BLOCK_INTERVAL=60
```

`aitbc-blockchain-rpc-island.env` — same chain/store/bridge names (the
RPC process runs the finalizer and serves `/rpc/gossip/ws`), with
`ENABLE_BLOCK_PRODUCTION=false` and the same port set. Per-host deltas
recorded at deploy: none beyond the env-file name (identical chain id,
ports, and bridge names on both hosts; key material is per-host in the
custody keyset `/etc/aitbc/credentials/bc-2-island-1.keys.json`).

**Why the standard root matters:** `AITBC_DATA_DIR=/var/lib/aitbc` puts
the island store at `data/bc-2-island-1/chain.db` *and* opens
`data/bc-2/chain.db` — the same file the host's bc-2 unit writes —
when the finalizer opens a session for `bc-2` (`_session_for` resolves
`DATA_DIR/data/<chain_id>/chain.db`). That shared store is how "the
island units host both stores" works; a separate data root would leave
the bc-2 store unreachable and `_chain_db_ready` would skip it.

**Deploy-time gotcha (caught by Coder B):** listing `bc-2` in the
island unit's `SUPPORTED_CHAINS` (e.g. `SUPPORTED_CHAINS=bc-2-island-1,bc-2`)
lets the island node open bc-2's **live** `chain.db` — read-only, but
against the production store. A wrong-chain open like that should be
refused (it is not the "genesis already exists" case); keep `bc-2` in
`BRIDGE_SUPPORTED_CHAINS` only, and treat this as a deploy trap to
document for future island deploys.

## 4. Gossip / firewall

- `GOSSIP_MESH_PEER_URLS` lists exactly the other island validator —
  a two-node mesh. **Deploy delta:** no dedicated gossip port (8370)
  was opened — hub1 ↔ node1 gossip rides the **nginx `/island/`**
  path, proxied to `127.0.0.1:8302` on both island vhosts. The public
  nginx path is the only inter-host channel the island needs.
- Firewall: no additional inter-host port was opened for the island;
  the nginx vhosts on each host expose `/island/` → `127.0.0.1:8302`
  (recorded at deploy). Nothing else reaches the island (no fleet
  gossip).
- `GOSSIP_AUTH_ENABLED` stays default-true — the restricted topics
  (`blocks.*`, `pbft.*`, `consensus.*`) sign with the fresh island
  `PROPOSER_*` keys; the bc-2 keys are not in the file, which is also
  why nothing island-side can publish to bc-2 topics.
- **Deploy delta — redis:** no island-dedicated redis is stood up
  (that part of the design held), but the mesh local bus does ride the
  host's existing redis, rebased to **db 9**
  (`GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379/9`).

## 5. Seal gate — the island must produce before any lock fires

**Hard gate: `bc-2-island-1` must be sealing blocks before any
`BRIDGE_LOCK` is submitted on bc-2.** The release seals *on the island*
— a shadow ledger is the historical failure mode: lock @27251 targeted
`ait-shop-island`, which had `accounts` + `cross_chain_transfer` but no
block/transaction tables, so even a passed confirm had nowhere to seal
(`bridge-release-exercise.md` — known failure modes).

Verification (both hosts, before handoff):

```bash
systemctl is-active aitbc-blockchain-node-island aitbc-blockchain-rpc-island
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
  `recipient: 0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` (fresh island
  address, recorded at island deploy — 10 AIT genesis alloc), the island
  RPC endpoint (`http://<host>:8302/rpc`, also reachable via the nginx
  `/island/` path), and the journal units the observation phases grep
  (`aitbc-blockchain-node-island` on hub1/node1).

## Deploy record — filled by Coder B's lane

| value | design | as deployed |
|---|---|---|
| unit file paths | real files, `%N.env` only | `/etc/systemd/system/aitbc-blockchain-node-island.service` + `aitbc-blockchain-rpc-island.service` — **delta:** named `*-island`, not `aitbc-i2-*` |
| env file paths | `/etc/aitbc/aitbc-i2-blockchain-{node,rpc}.env` (600) | `/etc/aitbc/aitbc-blockchain-{node,rpc}-island.env` (600) — follows the units' `%N` names |
| island validator addresses | fresh ×2 (hub1 proposer, node1 validator) | hub1 `0xc64117A4…9759` (island-proposer), node1 `0xA40C46F8…F5f5` (island-validator) |
| recipient address | fresh island addr | `0xc1B940CE2c2a046aCEb624A5d3C63b553C555E40` (10 AIT genesis alloc) |
| `bridge_release_authority` | island-side authority | baked in genesis; custody keyset `/etc/aitbc/credentials/bc-2-island-1.keys.json` (mode 600) records every baked authority |
| genesis identity | standard builder | `genesis_hash 0x4a55d897…`, `state_root 0x329bd94e…`; byte-identical `/var/lib/aitbc/data/bc-2-island-1/genesis.json` on both hosts |
| gossip 8370 serving mechanism | mesh peer endpoint | **delta:** no 8370 listener — peers dial the nginx `/island/` path → `127.0.0.1:8302` on both vhosts (the only inter-host channel) |
| `GOSSIP_BROADCAST_URL` | host redis local bus | `redis://127.0.0.1:6379/9` — host redis rebased to db 9 (**delta:** design said "no redis") |
| mempool | sqlite | sqlite db beside the island `chain.db` |
| hub1 memory caps | node 512M / rpc 256M | as spec'd — lowered to these post-deploy and confirmed live |
| first sealed island height / tx | — | island sealing confirmed live (2-of-2 PBFT); height/tx not transcribed here — read `/var/lib/aitbc/data/bc-2-island-1/chain.db` |
| any port that diverged | 8302 / 8309 / 8370 | rpc 8302 / metrics 8309 as spec'd; 8370 not served (nginx `/island/` carries gossip instead) |
