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
Each becomes EXECUTE-eligible at `voting_ends_block` — executor key is
provisioned on **hub** (`governance_executors` param); the leg is a
`13-governance` execute pass pinned to hub.

| proposal | voting_ends_block | est | armed in |
|---|---|---|---|
| prop_0b91289d | 18437 | ~2026-11-06 09:58Z | stress-2 (#720) |
| prop_bfc73030 | 19525 | ~2026-11-07 06:26Z | stress-3 |
| prop_b84b545e | 19534 | ~2026-11-07 06:36Z | stress-3 |
| prop_6bbc21b3 | 19541 | ~2026-11-07 06:44Z | stress-3 |

Verify: after each ends_block, `governance execute --proposal-id <id>` on
hub with the executor wallet, then check `execution_tx_hash` sealed. An
armed timer that never lands = finding class 1 (lost timer). Refusals
before ends_block are legal lifecycle answers, not findings.

Note (stress-3 observed semantics): agent-stake unbond is **wall-clock**
gated (`locked_until`), complete is **block** gated (`lock_height+1440`) —
two different maturity clocks on the same lifecycle.
