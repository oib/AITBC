# bc-2 Environment Set

The environment-variable set a node must carry to run the `bc-2` chain,
derived from a verified inventory of the live fleet's `/etc/aitbc` files,
`config.py` code defaults, and the five-node `bc-2` dress rehearsal on
unmodified consensus code.

Scope rules for this document:

- Values are shown for non-secret names only. Secret-class names
  (`*KEY*`, `*SECRET*`, `*PASS*`, `*TOKEN*`, `*MNEMONIC*`, `*SEED*`,
  `*PRIVATE*`) are listed by name only; their values live in the operator's
  custody and are deliberately absent here.
- Names whose values are operator decisions (addresses, amounts, keys, the
  validator set) are grouped in their own section — the tables reference
  that section instead of repeating placeholders.
- This document names no order and no timing. The checklist at the end is a
  flat list of named actions, not a runbook sequence.
- Nothing here is applied anywhere; it records what must be true when the
  operator chooses to apply it.

## Node unit (`aitbc-blockchain-node`)

| name | bc-2 value | basis |
|---|---|---|
| `CHAIN_ID` | `bc-2` | reset chain id |
| `SUPPORTED_CHAINS` | `bc-2` | admission list |
| `BLOCK_PRODUCTION_CHAINS` | `bc-2` | proposers only |
| `NETWORK_ID` | — | inert: no reader in the code — `NETWORK_ID=1337` appears only in `scripts/workflow/01_preflight_setup.sh:70` and `scripts/workflow-agent/01_preflight_setup_agent.sh:108` for their own preflight output; no action at the cut |
| `STATE_TRANSITION_V2_HEIGHT` … `STATE_TRANSITION_V14_HEIGHT` | `1` each | falsy thresholds are *inactive*, not height-0; `1` makes producer and replay agree v14 from block 1 (GATES.md `gates1` proof) |
| `BRIDGE_LOCK_LEAF_V2_HEIGHT` | `1` | `>=` gate — activates from block 1 |
| `ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT` | `1` | permits first-block sweep |
| `MULTI_VALIDATOR_CONSENSUS_ENABLED` | `true` | fleet value |
| `MULTI_VALIDATOR_MIN_ATTESTATIONS` | `2` | fleet value; rehearsal sealed with quorum 2 |
| `MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS` | `15` | fleet value — **write explicitly on node0** (it currently drifts to the 1.0 default) |
| `ATTESTATION_POST_QUORUM_LINGER_SECONDS` | `2.0` | fleet value — **write explicitly on node0** (it drifts today) |
| `PBFT_CONSENSUS_ENABLED` | `false` | fleet runs attestation mode, not PBFT certificates |
| `PBFT_VIEW_CHANGE_TIMEOUT` | `30` | fleet value — **write explicitly on node0** (it drifts today) |
| `ENABLE_BLOCK_PRODUCTION` | `true` on the proposer units, `false` on followers | per-role |
| `MAX_EMPTY_BLOCK_INTERVAL` | `60` | fleet value — **write explicitly on node0** (it drifts today) |
| `BLOCK_TIME_SECONDS` | `60` | fleet value |
| `PARALLEL_TX_VALIDATION` | `true` | fleet value; selects the alternate apply implementation for block versions 2–8 — **inert on bc-2**: under the `1` gate values every produced height resolves v14, outside the 2–8 window. The flag-on golden re-run returned 0 mismatches on both profiles; the `deployed` run is the evidence that the two implementations agree on the old history (`gates1` is vacuous for this flag) |
| `GOSSIP_BACKEND` | `mesh` | node-unit value (see RPC unit for the fleet split) |
| `GOSSIP_AUTH_ENABLED` | unset → `true` (default) | publish-side only; see harness items |
| `GOSSIP_PROTOCOL_VERSION` | unset → `2` | code default |
| `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` | `256` recommended | live differs per host (64 on hub/node1/node2, 128 on hub1, 256 on node0); the rehearsal hit a low cap — `256` uniform is a recommendation and an operator choice, not a fleet fact |
| `GOSSIP_MESH_PEER_URLS` | the bc-2 peer WS list (per node, self excluded) | deployment wiring |
| `GOSSIP_WEBSOCKET_URL` | the bc-2 hub gossip WS URL | deployment wiring |
| `SYNC_MANAGER_ENABLED` | `true` | fleet value |
| `SYNC_STATE_ROOT_VALIDATION_ENABLED` | `true` | fleet value |
| `SYNC_VALIDATE_SIGNATURES` | unset → default | code default |
| `AUTO_SYNC_ENABLED` | `true` | fleet value — **write explicitly on node0 and hub1** (both drift today) |
| `AUTO_SYNC_THRESHOLD` | `0` | fleet value — **write explicitly on node0** (it runs the `10` default); `0` makes any nonzero gap trigger bulk pull, removing the 1–10-block dead zone for a follower whose push paths fail |
| `STATE_SYNC_MAX_GAP` | `-1` on all five hosts, **node0 included** | `-1` disables snapshot pull and delta state-sync entirely (post-V23-90 hardening); `0` permits only gap-0 head rechecks; `10` permits syncs within 10 blocks. node0 today runs the `10` code default — **decided 20 Oct: node0 writes `-1` like the fleet** (operator answer: "Write the fleet values for node0") |
| `SUBSCRIPTION_ENABLED` | `true` | code default equals fleet value |
| `SUBSCRIPTION_TRANSPORT` | `websocket` | fleet value |
| `P2P_NODE_ID` | per-node stable id (e.g. `node-<name>`) | bound identity for peer keys and subscription |
| `P2P_BIND_HOST` / `P2P_BIND_PORT` | per-node bind | deployment wiring |
| `RPC_BIND_HOST` / `RPC_BIND_PORT` | per-node bind | deployment wiring |
| `BRIDGE_MULTISIG_ENABLED` | `true` | fleet value |
| `BRIDGE_MULTISIG_THRESHOLD` | `2` | fleet value; threshold is a count, not an address — kept here, validator list is operator-owned below |
| `BRIDGE_MULTISIG_TIMEOUT` | unset → `3600` | code default |
| `BRIDGE_VALIDATOR_SET_GRACE_PERIOD` | unset → `7200` | code default |
| `BRIDGE_RELEASE_ENABLED` | `true` | fleet value |
| `BRIDGE_RELAYER_ENABLED` | unset → `true` | code default; AND-gated on release |
| `BRIDGE_LOCKS_PAUSED` | `false` | fleet value |
| `BRIDGE_SUPPORTED_CHAINS` | `bc-2` | admission list |
| `BRIDGE_REQUIRE_MERKLE_PROOF` | `true` | fleet value |
| `BRIDGE_MIN_CONFIRMATIONS` / `BRIDGE_FINALITY_BLOCKS` | unset → `3` / `6` | code defaults |
| `BRIDGE_BLOCK_SIGNATURE_REQUIRED` | unset → `true` | code default |
| `BRIDGE_VERIFICATION_MODE` | unset → `in_process` | code default |
| `BRIDGE_LOCK_REQUIRE_REPLAY_GUARD` | `true` | fleet value |
| `CROSS_CHAIN_REQUIRE_REPLAY_GUARD` | `true` | fleet value |
| `SIDE_ROOT_SHADOW_ENABLED` | `true` | fleet value (`aitbc-blockchain-node.env`) |
| `BRIDGE_ROOT_SHADOW_CHECK` | `false` uniform | hub/node1/node2 already run it off; a fresh chain shadows nothing |
| `GPU_RETIRED_IDS` | carry the live list | operational, not consensus |
| `MEMPOOL_BACKEND` | unset → default | node1 currently drifts (unset) |
| `DEFAULT_PEER_RPC_URL` / `HUB_RPC_URL` / `HUB_BLOCKCHAIN_RPC_URL` / `HUB_DISCOVERY_URL` / `AITBC_SYNC_SOURCE` / `AITBC_SYNC_IMPORT_URL` | the bc-2 hub RPC URL | deployment wiring |
| `AITBC_CHAIN_ENV_FILE` | per deployment | file loading |
| `AITBC_DATA_DIR` / `AITBC_CONFIG_DIR` / `AITBC_LOG_DIR` | fresh per-node paths | fresh data directory at the cut |

## RPC unit (`aitbc-blockchain-rpc`) — deltas from the node table

| name | bc-2 value | basis |
|---|---|---|
| `GOSSIP_BACKEND` | `redis` | **required, proven in rehearsal**: the `/rpc/subscribe/ws` forwarder subscribes the RPC process's own broker; under `mesh` it stays silent and subscribed followers starve. The live fleet already resolves `redis` here (secrets file wins). |
| `ENABLE_BLOCK_PRODUCTION` | `false` | hub pins this today via `aitbc-blockchain-rpc-override.env` |
| `BLOCKCHAIN_RPC_API_KEY` / `BLOCKCHAIN_RPC_API_KEY_PEERS` | by name only | RPC key + accepted peer keys — the subscribe/heartbeat/lease auth list |

All other names are identical to the node-unit table.

## P2P unit (`aitbc-blockchain-p2p`)

Carries the same consensus set. Effective values match the node table
except where `aitbc-blockchain-p2p.env` pins its own (`PROPOSER_ID`,
`P2P_*`, gossip names). Load order observed on the fleet:
`blockchain.env → blockchain-secrets.env → node.env → %N.env`.

## Other service classes

Every unit whose env chain includes `CHAIN_ID` needs the new id at the
cut. The live inventory found `CHAIN_ID=ait-hub.aitbc.bubuit.net` (and
matching `SUPPORTED_CHAINS`/`BRIDGE_SUPPORTED_CHAINS`/
`BLOCK_PRODUCTION_CHAINS`) across 101 file assignments; the classes are:

- `aitbc-coordinator-api` — `CHAIN_ID`, `BLOCKCHAIN_RPC_URL`,
  `COORDINATOR_API_KEY` (secret), `NATIVE_CHAIN_ID` (hub only — see the
  missed-name note below).
- `aitbc-exchange` / `exchange` — `CHAIN_ID`, `DATABASE_URL` (postgres,
  credentials masked), `*_KEY` (secret); `PROPOSER_ID`/`VALIDATOR_SET`
  present but inert.
- `aitbc-market` / `aitbc-marketplace` — `CHAIN_ID`, `MARKET_ROLE`,
  `*_KEY` (secret); `PROPOSER_ID`/`VALIDATOR_SET` inert.
- `aitbc-wallet` — `CHAIN_ID`, `AITBC_DEFAULT_WALLET`, `WALLET_DIR`,
  `WALLET_PORT` (inert: no reader — the port is the `aitbc/constants.py:61`
  constant; no action at the cut), `DATABASE_URL`, `*_KEY` (secret).
- `aitbc-api-gateway` — `CHAIN_ID`, `*_KEY` (secret).
- `aitbc-pool-hub` — `CHAIN_ID`, `DATABASE_URL` (postgresql+asyncpg —
  pool-hub keeps PostgreSQL at the cut; every other service store starts
  as fresh SQLite), `POOL_HUB_URL`.
- `governance` — `CHAIN_ID`, `DB_TYPE` (`postgresql` on node0/node2,
  `sqlite` on hub/hub1 — live drift, not a reset decision), `DB_*`,
  `DB_PASS` (secret).
- miner / gpu / ffmpeg / whisper / hermes / edge / explorer /
  cache-monitor / monitoring / recovery / backup / journal-errors /
  island-* / chain-isolation-monitor / escrow-settlements /
  prometheus-watch / cli — template copies of `CHAIN_ID`/`VALIDATOR_SET`/
  `PROPOSER_ID`/`BLOCK_TIME_SECONDS`/`STATE_TRANSITION_V2_HEIGHT` (largely
  inert; rewrite uniformly anyway so no file straddles the cut).

`NATIVE_CHAIN_ID` — a name the earlier errata missed. It is read by the
coordinator's `config.py` and bound into GPU energy quotes at
`market_gpu.py`. Live it is set only on hub
(`ait-hub.aitbc.bubuit.net`; unset on the other four hosts). On bc-2 the
hub pin is a stale old-chain value: **drop the line** in the same env
edit as `CHAIN_ID` — setting it to `bc-2` is equivalent, and dropping is
the safe default because the coordinator now derives the quote chain
from `CHAIN_ID` when `NATIVE_CHAIN_ID` is unset (#307). A hub that
keeps the old pin emits quotes bound to `ait-hub.aitbc.bubuit.net`, and
a configured CLI verifier refuses them.

## Operator-decision names

These are operator-owned. Values are not in this document; each is named
with what the code expects. Rotation of any key material is an operator
decision and is proposed by nothing here.

| name | what the code expects |
|---|---|
| `VALIDATOR_SET` | JSON list of `{address, stake}` — the post-rotation validator addresses (the rehearsal used 4 entries, stake 1000 each) |
| `VALIDATOR_KEYS` | JSON map `address → private key` on each proposer unit (secret) |
| `PROPOSER_ID` / `PROPOSER_KEY` | the unit's own validator address / key (secret); only `aitbc-blockchain-node` reads them — needed also for gossip publish auth on restricted topics |
| `TRUSTED_PROPOSERS` | `genesis,<validator addresses>` or unset — a non-empty set turns on a membership check for **every** imported block (only listed proposers accepted, so any later validator-set change must also update it or the new proposer's blocks are refused) and lets unsigned blocks through only for listed proposers; unset is today's live behaviour (unsigned blocks fail closed). Every bc-2 node file-loads genesis, so block 0 never reaches the import validator — `genesis` matters only for a node that bulk-pulls from height 0 without the file. Operator decision; recommended `genesis,<validator addresses>` to keep that joiner path open (`sync_validator.py`) |
| `GENESIS_ADDRESS` / `GENESIS_WALLET_ADDRESS` | the new genesis identity per the allocation plan |
| `BRIDGE_ADMIN_ADDRESSES` | operator admin set |
| `BRIDGE_RELEASE_AUTHORITY` | operator authority (consensus-visible release admission) |
| `BRIDGE_MULTISIG_VALIDATORS` | count/list of the bc-2 bridge validators — selected set is the post-rotation validator addresses, threshold `2` per the table above |
| `BRIDGE_MAX_LOCK_AMOUNT` | recommended keep `36000000000` base units = **1000 AIT** (36,000,000 units/AIT); `0`/unset fails closed — production refuses locks |
| `ESCROW_RELEASE_ADDRESS` | operator address; live value `0x11741E1A…` is already public in repo docs |
| `ESCROW_FEE_RECIPIENT` | operator address; live value `0x34FFfAd1…` is already public in repo docs |
| `BOND_BURN_ADDRESS` / `BOND_SLASH_AUTHORITY_ADDRESS` | carry the live identities — the two init-time bond system accounts must be allocated at balance `0` in genesis (init rows win over funded allocations — rehearsal evidence) |
| `STATE_SYNC_MAX_GAP` (node0 only) | **answered 20 Oct 2026** — node0 takes the fleet value `-1` (operator answer: "Write the fleet values for node0"). Written explicitly in node0's bc-2 env set like the other four hosts; the small-gap window is not kept |
| `GOSSIP_MESH_PEER_URLS`, `GOSSIP_WEBSOCKET_URL`, hub/sync URL names | bc-2 hostnames/ports — deployment wiring |
| All `*KEY*` / `*SECRET*` / `*PASS*` / `*TOKEN*` / `*MNEMONIC*` / `*SEED*` / `*PRIVATE*` names | presence-only; values supplied by the operator at the cut |

## Harness-proven requirements (five-node dress rehearsal)

These are not optional preferences — each was a verified failure in the
rehearsal until the env made it true:

1. **Every node file-loads the same `genesis.json`.** A node that
   RPC-bootstraps genesis mints a *local* block-0 timestamp; the
   timestamp-derived proposer round then disagrees and every imported
   block fails the schedule check. RPC bootstrap also omits the
   genesis-seeded `chain_parameter` and `bridge_validator` rows.
2. **Followers need `P2P_NODE_ID` + `BLOCKCHAIN_RPC_API_KEY`.**
   `/rpc/subscribe` and `/rpc/heartbeat` return 403 without a key the hub
   accepts (`verify_rpc_peer_key` accepts the hub's own key, any
   `BLOCKCHAIN_RPC_API_KEY_PEERS` member, or an issued `/rpc/join` key
   bound to the `node_id`). The subscription stream is push-only with no
   backlog; an unauthenticated follower can only recover via bulk pull.
3. **`AUTO_SYNC_THRESHOLD` decides whether a keyless follower can catch
   up.** `gap > threshold` triggers bulk pull: `0` rescues any gap; the
   `10` default leaves a 1–10-block dead zone when all push paths fail
   (the rehearsal starvation mode). Fleet pins `0`.
4. **`GOSSIP_BACKEND=redis` on the RPC unit**, `mesh` on the node unit —
   the fleet's effective split; see the RPC table.
5. **`peer_keys.db` does not survive a fresh data directory** — it lives
   at `DATA_DIR/data/peer_keys.db` and starts empty. Fleet-internal
   followers are unaffected (shared `BLOCKCHAIN_RPC_API_KEY`). Self-serve
   joiners re-enroll via `POST <hub-rpc>/rpc/join {"node_id": "…"}` —
   self-serve, no admin credential, rate-limited (5/hour, 10 keys/IP/day,
   `node_id` unique while active; re-issue needs operator revocation via
   `scripts/ops/manage-peer-keys.sh`), key returned once, enrolled as
   `BLOCKCHAIN_RPC_API_KEY` + matching `P2P_NODE_ID`.
6. **Bond system accounts allocated at `0` in genesis** — database-init
   rows win over funded allocations for the two init-time bond accounts;
   the genesis input must allocate them at balance `0`.

## Apply-on-reset-day checklist

Named actions only — order and timing are deliberately absent:

- Write `CHAIN_ID=bc-2` (plus `SUPPORTED_CHAINS`,
  `BLOCK_PRODUCTION_CHAINS`, `BRIDGE_SUPPORTED_CHAINS`) across every env
  file that carries the id — all service classes listed above.
- Drop (or set to `bc-2`) the `NATIVE_CHAIN_ID` line in hub's
  `aitbc-coordinator-api.env` in the same edit as `CHAIN_ID` — a kept
  old-chain pin binds quotes to the old id and verifiers refuse them.
- Write all 15 gate heights to `1` (`STATE_TRANSITION_V2`–`V14`,
  `BRIDGE_LOCK_LEAF_V2`, `ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT`).
- Write the operator-supplied `VALIDATOR_SET`, `VALIDATOR_KEYS`,
  `PROPOSER_ID`/`PROPOSER_KEY`, `TRUSTED_PROPOSERS`, genesis/bridge/escrow
  addresses, and `BRIDGE_MULTISIG_VALIDATORS`.
- Ensure `GOSSIP_BACKEND=redis` on every `aitbc-blockchain-rpc` unit and
  `mesh` on every `aitbc-blockchain-node` unit.
- Ensure every node loads the identical `genesis.json` from file — no
  RPC genesis bootstrap.
- Enroll each follower's `P2P_NODE_ID` and `BLOCKCHAIN_RPC_API_KEY`
  (shared fleet key, or an issued key via `POST /rpc/join` on the hub
  RPC).
- Pin node0's drifted names to the fleet values — write each of these
  explicitly in node0's bc-2 env set:
  `MULTI_VALIDATOR_ATTESTATION_TIMEOUT_SECONDS=15`,
  `ATTESTATION_POST_QUORUM_LINGER_SECONDS=2.0`,
  `PBFT_VIEW_CHANGE_TIMEOUT=30`, `MAX_EMPTY_BLOCK_INTERVAL=60`,
  `AUTO_SYNC_ENABLED=true`, `AUTO_SYNC_THRESHOLD=0`,
  `STATE_SYNC_MAX_GAP=-1` (decided 20 Oct — node0 takes the fleet
  value), plus its per-node `P2P_NODE_ID` and `P2P_BIND_PORT`.
- Keep `AUTO_SYNC_THRESHOLD=0` on every host and
  `STATE_SYNC_MAX_GAP=-1` on all five hosts.
- Provision fresh data directories (service stores start as fresh
  SQLite; pool-hub keeps PostgreSQL; `peer_keys.db` starts empty —
  re-enroll any issued-key joiners).
- Remove the stale `GOSSIP_WEBSOCKET_URL=wss://hub.example.net/…` line
  found in one hub env file (losing order today — inert, but it must not
  survive into the new set).
