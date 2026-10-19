# Gate-semantics table — RESET-VECTORS-2

Every height/activation setting that shapes consensus or admission behavior,
its code default, its deployed (live `ait-hub.aitbc.bubuit.net`) value, the
comparison the code applies, the value that turns the rule **on from the first
produced block** of a `bc-2`-style chain, and what `0` actually does.

The trap this table exists for: **a gate height of `0` does not mean "on from
genesis" for most gates.** The version-resolution code treats `0`/falsy
thresholds as *inactive* — the rule never activates. Only the `>=`-style
non-version gates (`bridge_lock_leaf_v2_height`, `escrow_fee_sweep_pass_min_height`)
treat `0` as "on". The uniform bc-2 value is therefore **`1`**: every produced
block (heights >= 1) resolves to v14, the newest ruleset, on both the
producer and the replay path. Proven empirically by the `gates1` profile.

Env names are the pydantic field names uppercased (`STATE_TRANSITION_V9_HEIGHT`,
`BRIDGE_LOCK_LEAF_V2_HEIGHT`, `ESCROW_FEE_SWEEP_PASS_MIN_HEIGHT`, ...).

## Version-resolution gates (consensus apply)

| setting | default | deployed | compare | on from block 1 | `0` does | source |
|---|---|---|---|---|---|---|
| `state_transition_v2_height` | 0 | 0 | `> 0 and h >= t` | 1 | v2 inactive — replay falls to v1, producer still emits v2 (its tail is `if t > 0 and h < t: return 1; return 2`) | `state_transition.py:952-954, 1001-1004`; default `config.py:769` |
| `state_transition_v3_height` | 0 | 5470 | `> 0 and h >= t` | 1 | v3 inactive (no custody escrow) | `state_transition.py:949-951, 998-1000`; default `config.py:773` |
| `state_transition_v4_height` | 11000 | 11000 | `> 0 and h >= t` | 1 | v4 inactive | `state_transition.py:946-948, 995-997`; default `config.py:779` |
| `state_transition_v5_height` | 24000 | 24000 | `> 0 and h >= t` | 1 | v5 inactive — lenient authorities (no fail-closed) | `state_transition.py:943-945, 992-994`; default `config.py:787` |
| `state_transition_v6_height` | 0 | 0 | `> 0 and h >= t` | 1 | v6 inactive — bridge refunds unbound | `state_transition.py:940-942, 989-991`; default `config.py:794` |
| `state_transition_v7_height` | 24650 | 24650 | `> 0 and h >= t` | 1 | v7 inactive | `state_transition.py:937-939, 986-988`; default `config.py:802` |
| `state_transition_v8_height` | 24800 | 24800 | `> 0 and h >= t` | 1 | v8 inactive — and below it the unauthenticated `block_metadata.state_transition_version` stamp **wins** (any relay picks the rules); at/above it the stamp is advisory | `state_transition.py:923-936, 983-985`; default `config.py:817` |
| `state_transition_v9_height` | 30400 | 30400 | truthy `and h >= t` | 1 | v9 inactive — signatures not enforced | `state_transition.py:980-982`; default `config.py:832` |
| `state_transition_v10_height` | 32100 | 32100 | truthy `and h >= t` | 1 | v10 inactive | `state_transition.py:977-979`; default `config.py:843` |
| `state_transition_v11_height` | 35400 | 35400 | truthy `and h >= t` | 1 | v11 inactive | `state_transition.py:974-976`; default `config.py:858` |
| `state_transition_v12_height` | 37500 | 37500 | truthy `and h >= t` | 1 | v12 inactive | `state_transition.py:971-973`; default `config.py:873` |
| `state_transition_v13_height` | 46100 (`SHARED_ACTIVATION_HEIGHT`, `config.py:57`; `V13_HEIGHT_NOT_ARMED=2**62` parks it, `config.py:47`) | 46100 | truthy `and h >= t` | 1 | v13 inactive — executes unbound to proposals | `state_transition.py:968-970`; default `config.py:881` |
| `state_transition_v14_height` | 46100 | 46100 | truthy `and h >= t` | 1 | v14 inactive — no aux-state-root commit/check, unreadable bridge leaves grandfathered | `state_transition.py:965-967`; default `config.py:890` |

Replay-path readers: `get_block_version` (`state_transition.py:906-955`)
checks the v8 switch first (`:923-924`), then walks v7..v2 with `> 0 and
height >= t`, stamp wins below v8.
Producer-path readers: `get_block_version_for_height`
(`state_transition.py:958-1004`) walks v14..v9 on truthiness, v8..v3 on
`> 0`, and has the v2 special tail (`if t > 0 and h < t: return 1;
return 2` — with t=0 the `return 2` always hits). The two tails disagree
under all-zero: replay v1, producer v2 — a produced block would not replay
under the rules it was built with. `gates1` removes the divergence: both
paths resolve **1** at height 0 and **14** at every height >= 1.

### Producer-side stamp

- `poa.py:786` — new blocks stamp
  `block_metadata.state_transition_version = get_block_version_for_height(next_height)`;
  under `gates1` every produced block (h >= 1) stamps **14**.
- `poa.py:1153, 1265, 2126` — block building uses the same function; the
  `>= 14` at `:1265` gates aux-root production.
- `remote_attestation.py:183` — `>= 9` check on produced heights.
- `sync_block_import.py:719` — aux root recorded only `block_version >= 14`;
  `:801` — v14 aux-root recompute-and-reject on import.
- `state_transition.py:1445` — v14 BRIDGE_LOCK unreadable-leaf refusal.

## Non-version `>=` gates

| setting | default | deployed | compare | on from block 1 | `0` does | source |
|---|---|---|---|---|---|---|
| `bridge_lock_leaf_v2_height` | `None` | 51000 | `threshold is not None and height >= threshold` | 1 | **active from every nonnegative height** (opposite trap: 0 turns it ON, not off); `None` disables | `cross_chain/bridge_leaf.py:19-24`; read at `bridge_root_shadow.py:61,67`; default `config.py:710` |
| `escrow_fee_sweep_pass_min_height` | 35400 | 35400 | `min_height < setting` ⇒ RPC refuses | 1 | sweep pass allowed from height 0 — same "on" direction as 1 for first-block purposes; RPC/sweeper side only, never consulted by apply/replay | `rpc/escrow_routes.py:1103-1109`; `rpc/escrow_settlement_sweeper.py:304,617,628,931`; default `config.py:208` |

## RPC / admission-side height reads (not apply-path)

These mirror consensus gates for early client-visible refusals. With all
version gates at 1 they evaluate "post-gate" on a bc-2 chain from block 1 —
consistent with apply.

| read site | setting | compare | effect |
|---|---|---|---|
| `rpc/staking.py:259`, `rpc/agent_staking.py:250` | `state_transition_v4_height` | `current_height >= t` | stake-release maturity precheck (mirrors v4 window) |
| `rpc/escrow_routes.py:636` | `state_transition_v3_height` | `block_height < t` ⇒ v2-era warning | custody-era routing hint |
| `rpc/transactions.py:206` | v11 via `get_block_version_for_height` | `< 11` ⇒ refuse | ESCROW_FEE_SWEEP admission |
| `rpc/transactions.py:216` | v10 via `get_block_version_for_height` | `< 10` ⇒ refuse | GPU_DEREGISTER admission |

## Boolean flags — not height gates, keep at release values

`bridge_lock_require_replay_guard` (`config.py:535`),
`cross_chain_require_replay_guard` (`:542`), `bridge_root_shadow_check`
(`:701`), `side_root_shadow_enabled` (`:718`),
`parallel_tx_validation` (`:638`), `consensus_enforce_proposer_schedule`
(`:970`), `proposal_freshness_check_enabled` (`:976`), plus
`bridge_release_enabled` (`:516`), `bridge_multisig_enabled` (`:585`) and the
sync/gossip flag family. These are on/off switches, not activation heights —
do not fold them into the "every gate at 1" statement; the release sets each
deliberately.

## Proven answers (gates1 profile, 67-case synthetic + 389-block real stream)

- **Uniform `1` is sufficient.** No gate needs another value: every falsy-skip
  gate activates at h>=1 with `height >= 1` true; both `>=`-style gates
  activate at h>=1 too. No stop-trigger setting exists where `1` would trip
  an early boundary.
- **h0:** replay `get_block_version` = 1, producer `for_height` = 1 — agree.
  Genesis is prebuilt, not produced, so this only matters for replaying a
  supplied block 0.
- **h1+:** both paths = **14**. A producer-built block (stamped 14) is
  accepted by the replay path at the same height; an unstamped or mis-stamped
  (stamp=1) block also resolves 14 — stamps cannot downgrade post-v8 blocks.
- **v14 aux-root from block 1:** the v14 rule requires `aux_state_root` on
  import (`sync_block_import.py:801`) and refuses unreadable bridge leaves
  (`state_transition.py:1445`) — both live on the empty h1 block; recorded in
  `firstblock-empty-h1`.
- **`escrow_fee_sweep_pass_min_height=1`:** RPC/sweeper only; apply never
  reads it. `1` is the semantically right "from block 1" value (0 would also
  permit it but means "no minimum").
- **Rejects preserved under gates1:** double bridge-refund, unsigned
  transfer/lock/release (v9), unsigned/mis-signed execute (v9 +
  executors fail-closed), no-payload propose (v13), unknown/duplicate
  proposal (v13 binding), bad-value parameter_change (v12), wrong-authority
  release (v5), deactivated-GPU allocate / non-registrant deregister (v10),
  wrong-recipient fee sweep (v11), unreadable bridge leaf (v14),
  immature/spent stake release (v4) — all recorded in
  `expected/gates1/synthetic/`.
- **Era-dependent diffs vs `deployed`:** 48 of 60 original cases differ —
  every one because the case deliberately sits below a deployed pin
  (unsigned txs at v1-v8 heights, executes before v13 binding, sweeps
  before v11). No unexpected diff exists; the 12 post-gate cases
  (v13/v14/leafv2/aux-root band) are byte-identical between `deployed`
  and `gates1`.
