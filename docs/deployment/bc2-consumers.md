# bc-2 Consumers

Everything outside the node environment set that assumes the old chain —
the cut-day table for the `bc-2` reset, beside `bc2-environment-set.md`
(which owns the per-unit env names).

Decided facts only:

- chain id `bc-2`;
- every `STATE_TRANSITION_V<N>_HEIGHT` is `1` (all rules from the first
  block after genesis; no activation events exist);
- treasury at genesis `100M AIT` (`3.6e15` base units at 36,000,000
  units/AIT); no faucet balance at genesis;
- `PBFT_CONSENSUS_ENABLED=false`; multi-validator attestation minimum `2`;
- `NATIVE_CHAIN_ID`: drop the old-chain pin or set it to `bc-2` in the
  same env edit as `CHAIN_ID` (row 6 in `bc2-environment-set.md`).

Old-chain heights, hashes, genesis documents, allocations, and golden
vectors stay as history; `docs/releases/*` is untouched.

This document names no order and no timing. Classes: `at the cut`,
`after the cut`, `follows later`, `never needed`. Owners: `repo`
(a tracked change) or `host config` (a host-side action).

## Consumer table

| consumer | site | assumes | change for bc-2 | class | owner | verification |
|---|---|---|---|---|---|---|
| Prometheus rules, repo copy | `scripts/monitoring/aitbc_rules.yml` | old id only via `{{ $labels.chain_id }}` templates — generic | none; file is chain-agnostic | never needed | repo | `promtool check rules` passes unchanged |
| Prometheus rules, deployed copies | `/etc/prometheus/aitbc_rules.yml` on all five hosts — **all present, all sha256 `44b2997c778117a35669b6203f475402bec1e8e91acf4253fda86ef5b3e1b227` = repo file** | same as repo copy | none today; any future repo change must be copied to all five | at the cut (only if the repo file changes then) | host config | per-host `sha256sum` equals repo file |
| v9 shadow tripwires | `scripts/monitoring/aitbc_rules.yml:192-206` (`V9ShadowRejection` + attestation variant) | v9 height unset → `v9_would_reject_*` shadow counters exist | dead on bc-2 (v9 at height 1 → counters never emitted); removal is a cut-day repo+deploy action, deliberately not in this change | at the cut | repo + host config | alerts absent after removal; `promtool test` passes |
| v9 fixture series | `scripts/monitoring/aitbc_rules_test.yml:21-26` | shadow counters | drop the v9 series together with the alerts above | at the cut | repo | `promtool test rules` |
| Height in comment | `scripts/monitoring/aitbc_rules.yml:330` | "block 35400" residue-era reference in a comment | optional text fix, deferred with the file | follows later | repo | — |
| Backup good-dump glob | `scripts/maintenance/aitbc-backup.sh:28` `BACKUP_GOOD_CHAIN_GLOB` (default `chain_ait-hub.aitbc.bubuit.net_chain.db.gz`, consulted at `:453`) | dump filename for the old chain id | set `BACKUP_GOOD_CHAIN_GLOB=chain_bc-2_chain.db.gz` in `/etc/aitbc/aitbc-backup.env` — the service loads `EnvironmentFile=-/etc/aitbc/aitbc-backup.env` and `aitbc-backup.timer` fires it daily; the env file exists on all five hosts and carries no override today. Repo default intentionally unchanged | at the cut | host config | post-cut backup passes the good-dump floor check |
| Website render chain id | `scripts/ops/render-website.sh:42` `DEFAULT_CHAIN_ID` (target resolved from `WEBSITE_CHAIN_ID` in `/etc/aitbc/website.env`, fallback `CHAIN_ID` in node.env) | old id is the baked default | set `WEBSITE_CHAIN_ID=bc-2` in `/etc/aitbc/website.env` — `update.sh` re-renders after the next pull; the default stays for today's renders. Cut-day alignment: the hub also needs `CHAIN_ID=bc-2` so the explorer resolves `/var/lib/aitbc/data/bc-2/chain.db` | at the cut | repo + host config | rendered `config.js`/`dashboard.js` carry `bc-2` |
| Genesis-builder refusal list | `apps/blockchain-node/src/aitbc_chain/genesis_builder.py:54` `LIVE_CHAIN_IDS` (checked at `:268`) | refusal list names live chains | add `bc-2` **only after** bc-2 is live — adding earlier would refuse the pre-cut genesis build this milestone still needs | after the cut | repo | builder refuses to rebuild `bc-2` |
| Archived old-chain exporters | `scripts/monitoring/attestation-arrival-textfile.py:70-72` (`data/*/chain.db` scan) + `scripts/monitoring/escrow-residue-textfile.py` | scans every `chain.db` under the data dir | no code change: if the archived old-chain directory stays under `AITBC_DATA_DIR`, metrics keep reporting it — operator decision at the cut whether to move it out | at the cut | host config | exporter metrics report only `db=bc-2` |
| Website chain id | `website/config.js:13` `chainId`; `website/dashboard.js:17` fallback literal | hard-coded old id | set `bc-2` — hand-off list below; not edited in this row | at the cut | repo | site renders bc-2 stats |
| nginx genesis alias | `/etc/nginx/sites-enabled/aitbc` → `location = /agent/genesis.json` alias | serves `/etc/aitbc/genesis.json` by path | none — serves whichever genesis file is present | never needed | host config | GET returns the bc-2 genesis post-cut |
| Prometheus alert watcher | `aitbc-prometheus-watch.service` → `aitbc prometheus alerts --watch` | renders rule annotations, no chain assumption | none | never needed | host config | watch log shows bc-2 labels post-cut |
| First-sweep checker | `scripts/ops/first-sweep-check.py` (chain id resolution at `:515-537`) | silent old-chain default — removed this row | `--chain-id` wins, then the chain the sweep rows carry, then `CHAIN_ID`; errors out naming both when none yields an id | follows later (use as needed) | repo | runs against bc-2 db snapshots: `first-sweep-check.py --latest <db>` / `--job-id <id> <db> [<db>...]` |
| Post-activation audit | `scripts/ops/post_activation_audit.py` (`CHAIN_DB` at `:79` + docstring) | audits the v14/v13 activation event at height 46,100 | no bc-2 use — all gates at height 1 means no activation event; header marks it old-chain-only | never needed | repo | — |
| Stale genesis builders | `apps/blockchain-node/scripts/make_genesis.py`, `apps/blockchain-node/scripts/create_bootstrap_genesis.py`, `apps/blockchain-node/create_enhanced_genesis.py`, `apps/blockchain-node/scripts/setup_production.py`, `scripts/workflow/02_genesis_authority_setup.sh`, `scripts/workflow-agent/02_genesis_authority_setup_agent.sh` | EVM-scale / 1B / ait-mainnet-era models — none can emit the loader-valid bc-2 document (no canonical `state_root`/bridge-validator digest) | hard-stopped this row, each naming `aitbc_chain/genesis_builder.py` (via `scripts/ops/build-genesis.py`) as the only builder | never needed | repo | refusals verified; `test_v064_multi_chain.py` B7 asserts them |
| Devnet genesis callers | `apps/blockchain-node/scripts/devnet_up.sh:16`; `apps/blockchain-node/scripts/setup_production.py:165` (invokes `make_genesis` internally — already hard-stopped itself); `scripts/deployment/deploy/deploy-blockchain-and-explorer.sh:64`, `deploy-blockchain-remote.sh:84`, `deploy-first-node.sh:48`, `deploy-in-container.sh:89`, `deploy-second-node.sh:56`; `scripts/workflow/setup_multinode_blockchain.sh:51,71` and `scripts/workflow-agent/05_complete_workflow_agent.sh:86-87` invoke the stopped `02_genesis_authority_setup*.sh` pair | call `make_genesis.py` or the stopped `02_` pair | all hit the refusal — re-wire to `build-genesis.py` if devnet flows are still wanted; **no unit, timer, cron entry or setup/update script runs any of them on hub, hub1, node0, node1 or node2** (read-only check all five hosts) | follows later | repo | scripts fail with the clear do-not-use message |
| `aitbc genesis init` → `unified_genesis.py` | `cli/aitbc_cli/commands/genesis.py:72` → `apps/blockchain-node/scripts/unified_genesis.py` | legacy EVM-scale genesis model | not a safety issue — `unified_genesis.py` already runs `aitbc.utils.reset_guard` (`:255-277`): writes are confined to a declared `AITBC_RESET_SCRATCH` root, live chain ids are refused, and with no marker it exits `AITBC_RESET_SCRATCH is not set — refusing to run a destructive reset tool outside a declared scratch root. These legacy tools no longer have a live mode; reset-day writes go through scripts/ops/build-genesis.py.` (verified `aitbc genesis init --chain-id bc-2`, no marker). The open question is wiring only: it cannot emit the canonical bc-2 document even inside a scratch root | follows later | repo | `aitbc genesis init` behaviour per wiring decision |
| `bridge-leaf-audit.py` | `scripts/ops/bridge-leaf-audit.py:67-93` | `--v2-height` → env → settings → `/etc/aitbc/blockchain.env` | none — picks `BRIDGE_LOCK_LEAF_V2_HEIGHT=1` from the env set | never needed | repo | run on a bc-2 `chain.db`, leaves match v2 shape |
| `env-watch-textfile.py` | `scripts/monitoring/env-watch-textfile.py` | watched names from `AITBC_ENV_WATCH` | none — name-presence only | never needed | repo | `aitbc_env_var_present{var="CHAIN_ID"}=1` |
| Golden corpus / topology / release docs | `docs/releases/*`, golden vectors, `TOPOLOGY/` | old heights and hashes | stay as history — no edits | never needed | repo | untouched |
| Supply / 1B-era docs | `docs/getting-started/node/blockchain-setup.md` genesis example (`:164`, 1e9 *units* — not a 1B-AIT claim); `ait-value-model.md` (fee-split already corrected by `14f73e2c5`, treasury text current) | none stale enough to edit | none this row | never needed | repo | — |

## Website hand-off (for the website session)

- `website/config.js:13` — `chainId: 'ait-hub.aitbc.bubuit.net'` → `bc-2`.
- `website/dashboard.js:17` — same literal in the `AITBC_CONFIG` fallback → `bc-2`.
- Rendered copies: `scripts/ops/render-website.sh` re-renders `config.js`
  and `dashboard.js` (file list at `:50`); drive it with
  `WEBSITE_CHAIN_ID=bc-2` in `/etc/aitbc/website.env` so the rendered pair
  match the repo edit.

## Host evidence

- `/etc/prometheus/aitbc_rules.yml` exists on **all five hosts** (hub,
  hub1, node0, node1, node2); all five hash to
  `44b2997c778117a35669b6203f475402bec1e8e91acf4253fda86ef5b3e1b227`,
  identical to the repo file at base `03da53ef2`.
- `aitbc-backup.timer` runs daily; `aitbc-backup.service` loads
  `EnvironmentFile=-/etc/aitbc/aitbc-backup.env` and executes
  `/opt/aitbc/scripts/maintenance/aitbc-backup.sh`. The env file exists on
  all five hosts; no host sets `BACKUP_GOOD_CHAIN_GLOB` today.
