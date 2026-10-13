# v14 activation runbook — height 46,100

Audience: the operator on call when the chain does something odd at or after
block 46,100. Read §1 once before the height; use §3 when something breaks.

Fleet: node0, node1, node2, hub1, hub — chain `ait-hub.aitbc.bubuit.net`,
RPC on `127.0.0.1:8202`, chain DB at
`/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db` on every host.
Code references are against the deployed commit (`ce99ea30c` lineage).

## 1. What activates at 46,100

One shared activation height (`SHARED_ACTIVATION_HEIGHT` in
`apps/blockchain-node/src/aitbc_chain/config.py`) arms three rungs at once.
`get_block_version_for_height` checks v14 before v13
(`state/state_transition.py:965-970`), so a height ≥ both thresholds is a
v14 block that also carries the v13 behaviour.

| rung | plain meaning | where |
|---|---|---|
| v13 (V-2) | GOVERNANCE_EXECUTE applies the **sealed** PROPOSE payload, not the payload the tx carries; a proposal executes at most once per sealed height | `state/state_transition.py:2251-2263` (`_sealed_propose_execution_payload`, `_sealed_execute_exists`) |
| v14 (V-3) | Every sealed block header carries `aux_state_root` = deterministic fingerprint over the 13 apply-written tables (`COMMITTED_TABLES`); importers recompute and **reject** on mismatch | seal: `consensus/poa.py:1264-1267`; reject: `sync_block_import.py:800-816`; table set: `state/side_root_shadow.py:62-76` |
| v14 (V-4) | A BRIDGE_LOCK whose leaf data cannot be re-derived from the tx (payload fields or signed envelope) is refused — at apply and at RPC admission. Post-activation, every sealed lock's leaf is provable from the block itself; pre-activation underivable locks are grandfathered | apply gate: `state/state_transition.py:1445-1447`; admission: `rpc/transactions.py:189-196`; derivation: `cross_chain/bridge_lock_guard.py` |

Config names and overrides (env files in `/etc/aitbc/`):

- `state_transition_v13_height` ← `STATE_TRANSITION_V13_HEIGHT`
- `state_transition_v14_height` ← `STATE_TRANSITION_V14_HEIGHT`
- `V13_HEIGHT_NOT_ARMED = 2**62` is the sentinel: a rung set to it is
  parked (unreachable), not deleted. Setting both heights to the sentinel
  cancels the activation.
- `SIDE_ROOT_SHADOW_ENABLED` — compare-only shadow fingerprint written to
  the node-local `shadow_side_root` table on every sealed/imported block
  (`consensus/poa.py:1524`, `sync_block_import.py:822`). Already `true` on
  all five hosts since 12 Oct. Shadow is never consensus input; it is the
  independent reference for the at-height check.

Before H (`<46,100`): headers stamp `state_transition_version: 12`,
`aux_state_root: null`; unreadable locks pass admission (dry-run guard only
logs); governance executes the tx-carried payload.
At/after H: version 14 headers with `aux_state_root` set; unreadable locks
refused; sealed-payload execution bound.

## 2. Healthy signs around 46,098–46,111

All commands run per host (`for h in node2 hub1 node1 node0 hub; do ssh $h
'<cmd>'; done`). All are read-only.

Heads equal and advancing (~68 s/block):

```bash
ssh $h "curl -s 127.0.0.1:8202/rpc/chain/head"   # height + hash, identical ×5
```

Per-block stamps — `state_transition_version` and `aux_state_root`:

```bash
ssh $h "curl -s 127.0.0.1:8202/rpc/blocks/46099" | jq '.state_transition_version, .aux_state_root'
# expect 12, null
ssh $h "curl -s 127.0.0.1:8202/rpc/blocks/46100" | jq '.state_transition_version, .aux_state_root'
# expect 14, non-null — and the SAME aux value on all five hosts
```

The block-46,100 aux root must equal the fleet shadow fingerprint at that
height (shadow was armed pre-activation):

```bash
ssh $h "sqlite3 'file:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db?mode=ro' \
  'SELECT fingerprint FROM shadow_side_root WHERE block_height=46100;'"
```

Whole-window audit in one shot (hashes identical ×5, stamps, proposer
rotation, attestation):

```bash
cd /opt/aitbc && venv/bin/python scripts/ops/post_activation_audit.py \
  --activation-height 46100 --window 12
```

Alerts — none of these should fire in the 46,090→now window:

```bash
curl -s 'http://127.0.0.1:9090/api/v1/query?query=ALERTS{alertstate="firing"}'   # on hub
curl -s 'https://hub.aitbc.bubuit.net/explorer-api/api/alerts'
```

Watched rules: `ChainDiverged`, `ChainDivergenceSeen`, `ServiceDown`,
`AttestationValidatorSilent`, `sync_aux_root_rejected_total` (metric, counts
post-H aux rejections — must stay 0).

Proposers rotate per `VALIDATOR_SET`, attestations fresh (validator gossip /
`remote_attestation` log lines), mempool drains normally. The validator set
must be identical on all five (`VALIDATOR_SET` in env, or compare the
attester address set across a few post-H blocks).

## 3. Failure decision tree

Every branch: first checks are read-only; the forbidden column is absolute.
"Decide" = who may authorise a change — operator (default) or the operator
after a written finding (finding first). **Never restart two validators in
the same window; never act before stating the pre-check result.**

### (a) Head stops on ALL hosts

- Checks: `systemctl is-active aitbc-blockchain-node` ×5; journal tail
  `journalctl -u aitbc-blockchain-node -n 80 --no-pager`; is the same height
  rejected everywhere (`sync_aux_root_rejected_total` > 0, "BLOCK REJECTED"
  lines)? `ServiceDown` firing?
- Likely cause: the block at/after H fails a check every host shares (aux
  reject, V-4 refuse, signature) — i.e. the *first* post-H block is bad,
  or all proposers stopped.
- Safe action: capture the first rejected block's payload + the journals;
  report. If every validator is wedged, deliberate-halt is already the
  state — nothing to stop.
- Forbidden: restarting services to "unstick"; touching chain.db;
  re-proposing by hand; env edits during diagnosis.
- Decide: operator. Escalate to §4 halt rules if > ~10 min.

### (b) ONE host stops or forks; others continue

- Checks: that host's journal for "Aux state root mismatch" /
  "BLOCK REJECTED"; its `shadow_side_root` fingerprint at the contested
  height vs a healthy host's; its head+hash vs the fleet's; its checkout
  (`git -C /opt/aitbc rev-parse HEAD`) and env diff vs a healthy host.
- Likely cause: that host diverged (dirty tree, wrong env, older code,
  local table corruption). A single-host aux mismatch means *that host's*
  side state differs — the other four agreeing is the strong signal.
- Safe action: stop poking it; record `journalctl --since`, the contested
  block, its fingerprint row; let the other four keep producing. The
  straggler can be rebuilt/re-synced later.
- Forbidden: "fixing" the four to match the one; restarting the straggler
  before capture; re-applying the block.
- Decide: operator after a written finding (do not auto-fix divergence —
  ACT-1 rule).

### (c) Blocks rejected for aux_state_root mismatch

- Symptom: "Aux state root mismatch at height N: expected X computed Y -
  BLOCK REJECTED" in sync journal; `sync_aux_root_rejected_total`
  increments.
- Checks: which hosts reject (all = proposed block's aux is wrong vs the
  committed state; one = that host's committed state differs); shadow
  fingerprint at N per host; whether the proposer is the same host that
  diverged at N-1; diff the proposer's committed tables via the fleet
  digest spec.
- Likely cause: a node-local (non-deterministic) write reached a committed
  table — e.g. a service writing where apply owns the field (the exact
  class V-3 exists to detect). On an isolated host it's a local-drift
  event, not a consensus split.
- Safe action: **this runbook's default is deliberate halt if mismatch is
  fleet-wide** — see §4. Per-host: hold the rejecter, capture rows.
- Forbidden: disabling the aux check mid-flight (it is not env-gated
  post-activation — the reject is the feature); "patching" a committed
  table by hand; restarting to re-roll the block.
- Decide: operator.

### (d) V-2 rejections / governance execution mismatch

- Checks: `GOVERNANCE_EXECUTE` txs in the window — "not sealed in an
  earlier block" or "already executed" warnings (`state_transition.py`
  2251-2263); whether the execute predates its propose's seal; proposals
  stuck in `pending` with no sealed PROPOSE.
- Likely cause: an execute tx submitted before its proposal sealed, or a
  re-execute attempt — both now correctly refused; or an RPC path that
  pre-fills payload fields no longer used.
- Safe action: confirm the sealed PROPOSE exists and the execute is a
  genuine duplicate/out-of-order; re-issue the execute *after* seal if
  legitimate (chain write → operator).
- Forbidden: replaying execute txs; editing `governance_proposal` rows;
  assuming v13 reverted.
- Decide: operator.

### (e) Attestation drop / quorum lost (`AttestationValidatorSilent`)

- Checks: which validator went silent (gossip listener logs,
  `remote_attestation` journal, `validator_attestations` freshness); is
  the silent one a validator node that stopped (b) or is wedged on a
  reject (c)?
- Likely cause: one validator's node halted → attestations short one
  member. Blocks still seal (attestations are liveness evidence, not the
  seal gate) but finality evidence degrades.
- Safe action: treat as (b) for the silent host; monitor remaining
  attesters. Restarting the silent validator's `aitbc-blockchain-node`
  only is permitted under the one-at-a-time rule if its service died
  (pre-check: service actually dead, not just quiet).
- Forbidden: restarting multiple validators; forcing attestation traffic.
- Decide: operator.

### (f) A validator proposes a pre-activation header after H

- Checks: the offending block's `state_transition_version` (12 with H≤
  height), proposer address → host; that host's `git rev-parse HEAD`
  (`/opt/aitbc`) and `STATE_TRANSITION_V14_HEIGHT` env vs the fleet; its
  `aitbc-blockchain-node` start time vs its checkout time.
- Likely cause: that host runs pre-merge code (old checkout, service
  started before pull — the exact failure the ACT-1 checkout/start-time
  table guards) or a wrong/missing env height.
- Safe action: a post-H v12 block is a wrong-version proposal — the fleet
  may still seal it (version is a stamp, not a gate) but its aux will be
  null where ≥H requires a value → expect (c) symptoms. Capture the
  header; the fix is the host's code/env, not the chain.
- Forbidden: accepting the block as fine because it sealed; touching the
  proposer's key material.
- Decide: operator.

### (g) Mempool jam / bridge ops failing after H

- Checks: `/rpc/mempool` size trend; journal for refused BRIDGE_LOCK lines
  ("unreadable"); are the failing locks legacy-style (no payload fields /
  no envelope)?
- Likely cause: pre-H lock submissions that never carried derivable data
  now refused at admission (V-4 doing its job) — client-side change, not
  a chain fault; or a mempool wedge unrelated to activation.
- Safe action: identify the refusing tx and its missing fields; the
  submitter re-issues in the derivable form (V-4 spec). Mempool itself:
  watch drain rate before acting.
- Forbidden: bypassing admission checks; re-enabling the pre-v14 path
  mid-flight; flushing mempool as a first resort.
- Decide: operator (any client-facing fix is theirs).

### (h) Alert storm

- Checks: enumerate firing rules (`ALERTS{alertstate="firing"}`); is it
  one cause fanning out (`ServiceDown` → `ChainDivergenceSeen` +
  attestation alerts) or truly independent?
- Likely cause: one root cause cascading; or scrape noise during the
  restart window.
- Safe action: work the root branch above; silence nothing until the
  cause is captured. A storm that resolves in < 5 min with heads equal
  was noise, record it.
- Forbidden: silencing alerts to clear the page; treating symptoms
  bottom-up.
- Decide: operator.

## 4. Rollback — what can and cannot be undone

**Cannot be undone:** sealed blocks. Anything ≥H already sealed stays
sealed; rolling back sealed history is chain surgery, not ops.

**Can be undone by config (operator-gated):**

- **Move H later** (before H only): set `STATE_TRANSITION_V13_HEIGHT` and
  `STATE_TRANSITION_V14_HEIGHT` to a higher height on all five hosts,
  serial restart `aitbc-blockchain-node` one at a time (node2 → hub1 →
  node1 → node0 → hub), pre-check + green post-check per host, never two
  validators in one window.
- **Cancel activation** (before H only): set both to `2**62`
  (`V13_HEIGHT_NOT_ARMED`). Sentinel is deliberate — it parks the rung
  without editing code.
- **After H has passed:** env height changes do nothing for already-sealed
  blocks. A post-H emergency brake does not exist as config — see halt.

**Deliberate halt vs keep producing:** if blocks at/after H are being
rejected fleet-wide for aux mismatch (branch c) or the first post-H block
cannot seal (a), the correct default is to let the chain **stay stopped**
while evidence is captured — a halted chain preserves state; a chain
producing rejected/forked blocks buries the evidence and can split the
DBs. Keep-producing is only right when exactly one host rejects and the
other four seal the same hash — then the one is a straggler, not a halt.

**Capture before ANY restart:**

```bash
ssh $h "curl -s 127.0.0.1:8202/rpc/chain/head"                         # head+hash
ssh $h "curl -s 127.0.0.1:8202/rpc/blocks/<first-post-H-height>"       # sealed header
ssh $h "journalctl -u aitbc-blockchain-node --since '-30 min' --no-pager > ~/j-$h.log"
ssh $h "sqlite3 'file:...chain.db?mode=ro' 'SELECT * FROM shadow_side_root
        WHERE block_height BETWEEN <H-2> AND <head>;'"
ssh $h "cd /opt/aitbc && git rev-parse HEAD && git status --porcelain"
```

## 5. Who to inform, what to record

- Inform: the operator (single-operator fleet) — same channel that issued
  the activation order; then the director's round summary.
- Record: append a dated section to `TOPOLOGY/2026-10-13-round19-a-activation.md`
  (or a new dated record if post-activation): heads/hashes (12-hex), the
  stamp table for 46,098–46,111, probe results, alert state, validator set,
  the anomaly and decision verbatim, who decided. Progress lines on
  `tasks/progress/V-2.md`, `V-3.md`, `V-4.md` with the verdict.

## 6. Post-activation follow-ups (ordered)

1. **V-5 manifest signing (agent C):** snapshot/side-state manifest signing
   proceeds only after the at-height checks confirm a stable v14 chain
   (its manifests commit the post-v14 world).
2. **O-11 — v15 decision:** `dev/block-scoped-account` (4ea1717fa) stays
   parked at `V13_HEIGHT_NOT_ARMED` until the operator picks a height —
   no earlier than the activation-settling window. The env flag
   `BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS` remains the live switch
   meanwhile.
3. **Clear the temporary watch:** the ACT-1 watcher polling head ≥ 46,111,
  plus any manual watch cron/loop added for the window — stand down once
   the Part-3 checks record green.
4. **bridge_state_root proposer-dependence (finding, ACT-2):**
   `_compute_bridge_state_root` still reads node-local
   `cross_chain_transfer` rows (`poa.py:2551-2580`); at ≥v14 the leaf data
   is guaranteed derivable from the tx envelope, so a deterministic
   rewrite is now *possible* — a post-settling design item, not an
   emergency.
