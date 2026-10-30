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
