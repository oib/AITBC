# MATURITY — lock_days calendar for once-mode plays

`lock_days >= 1` is consensus-bound: a RELEASE cannot seal before
`lock_height + 1440`. Once-mode plays fire the LOCK early in the round and
the RELEASE on a later pass. The script must verify maturity
(`locked_until` / height) and exit 77 `SKIP_MATURE` when unripe.

| play | lock leg | release leg | window | status |
|---|---|---|---|---|
| 09-bond | BOND_LOCK | BOND_RELEASE | lock_height + 1440 | pending first lock |
| (stake-lane if revived) | STAKE_LOCK | STAKE_RELEASE | lock_height + 1440 | gated at v17 (#649) |

Per-round rule: each `run.sh --include-once` pass may fire a new lock;
the release leg targets the OLDEST matured lock, not the one just fired.

## Governance EXECUTE armed timers (verify-first, next round)

Stress-3 sealed these propose+vote legs with execute pending voting-end.
The leg (#752) is **close at each `voting_ends_block`, then ONE serial
execute batch at h20831+** (~65s cadence between submits):

| proposal | close at/after | EXECUTE-eligible ≥ | ~close when | armed in |
|---|---|---|---|---|
| prop_71d5bd49 | 18346 | 19636 | ~Nov-05 19:05 CET | stress-2 (#720) |
| prop_0b91289d | 18437 | 19727 | ~Nov-05 20:46 CET | stress-2 (#720) |
| prop_bfc73030 | 19525 | 20815 | ~Nov-06 17:25 CET | stress-3 |
| prop_b84b545e | 19534 | 20824 | ~Nov-06 17:35 CET | stress-3 |
| prop_6bbc21b3 | 19541 | 20831 | ~Nov-06 17:44 CET | stress-3 |

Leg (both legs pinned to hub, serial):
1. `aitbc governance close --proposal-id <id>` at/after each
   `voting_ends_block` — tallies the vote, status → succeeded/failed.
   One close per prop; closable any time after its end height.
2. At h≥20831: `aitbc governance execute --proposal-id <id>` ×5, one
   serial submit per block cadence, signed with the `0xD9CC189c…`
   executor wallet — **operator stages the key on hub before
   2026-11-05 ~22:00 CET** (verify address only; never print the key).
3. Check each `execution_tx_hash` sealed; status → executed.

An armed timer that never lands = finding class 1 (lost timer). Refusals
before the eligible height are legal lifecycle answers, not findings.
The other `active` proposals in `governance list`
(76855f71/9cfe1215/532fac8b/3017437a, `voting_ends_block: null`) are not
part of this batch — tracked separately.

Evidence on #752: commit hash, hub position before the ff, and a seal
height per prop; set `needs-verify`, do not close the issue. Post-batch
hygiene: **remove the staged executor key from hub** — it retires at
genesis under R8, so its residency is timeboxed to this batch.

Note (stress-3 observed semantics): agent-stake unbond is **wall-clock**
gated (`locked_until`), complete is **block** gated (`lock_height+1440`) —
two different maturity clocks on the same lifecycle.
