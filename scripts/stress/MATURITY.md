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
EXECUTE-eligible = `voting_ends_block + timelock_blocks` — the live
timelock on bc-2 is **1290** (chain param; repo default 43200 is overridden).
Executor key is provisioned on **hub** (`governance_executors` param);
the leg is a `13-governance` execute pass pinned to hub. All four land
inside one batchable window at h20831+.

| proposal | voting_ends_block | EXECUTE-eligible ≥ | ~when | armed in |
|---|---|---|---|---|
| prop_71d5bd49 | 18346 | 19636 | ~2026-11-05 23:44 CET | stress-2 (#720) |
| prop_0b91289d | 18437 | 19727 | ~2026-11-06 01:26 CET | stress-2 (#720) |
| prop_bfc73030 | 19525 | 20815 | ~2026-11-06 ~21:40 CET | stress-3 |
| prop_b84b545e | 19534 | 20824 | ~2026-11-06 ~21:50 CET | stress-3 |
| prop_6bbc21b3 | 19541 | 20831 | ~2026-11-06 ~22:00 CET | stress-3 |

Verify: at/after each EXECUTE-eligible height, `governance execute
--proposal-id <id>` on hub with the executor wallet, then check
`execution_tx_hash` sealed. An armed timer that never lands = finding
class 1 (lost timer). Refusals before the eligible height are legal
lifecycle answers, not findings. (Heights updated 31 Oct for the verified
live `timelock_blocks: 1290` — earlier table assumed eligibility at
voting_ends_block itself.)

Note (stress-3 observed semantics): agent-stake unbond is **wall-clock**
gated (`locked_until`), complete is **block** gated (`lock_height+1440`) —
two different maturity clocks on the same lifecycle.
