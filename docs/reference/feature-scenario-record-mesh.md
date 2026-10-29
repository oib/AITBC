# Feature ↔ Scenario ↔ Record Mesh

**Purpose**: one-hop cross-index between the four namespaces that describe
"what the chain records, what emits it, what proves it, and what documents
it":

```
record type  →  emitting `aitbc` CLI path  →  scenario(s)  →  feature doc(s)
```

Given any one of the four, this page gets you to the other three in ≤1 hop.

**The spine is the coverage ledger** in
[docs/scenarios/README.md — *On-chain record coverage*](../scenarios/README.md#on-chain-record-coverage):
its 19 record-type rows (covering the 32 `V9_METRIC_KNOWN_TX_TYPES` in
`apps/blockchain-node/src/aitbc_chain/state/v9_policy.py`) are the
authoritative record-type → emitter → scenario map, and its **"sealed on
bc-2"** column is the canonical live-seal evidence. That column is *not*
duplicated here — follow the link.

CLI paths are the canonical group names registered in
`cli/aitbc_cli/core/main.py` (e.g. `gpu-onchain`, `agent-msg`,
`exchange-island`, `liquidity-stake`).

---

## Table A — record types → the mesh

One row per record-type row of the coverage ledger. "protocol-internal"
means no wallet-facing CLI emits the type (the node or an authority signs
it). Live-seal heights/tx hashes: see the
[coverage ledger](../scenarios/README.md#on-chain-record-coverage).

| Record type | aitbc CLI path | Scenario(s) | Feature doc(s) | Notes |
|---|---|---|---|---|
| `TRANSFER` | `aitbc transactions send` | [02](../scenarios/02_transaction_sending.md), [59](../scenarios/59_sepolia_buy_sell_ait.md) | [create-payment](../features/create-payment.md), [payment-status](../features/payment-status.md), [9-wallet](../features/9-wallet.md) | plain value transfer |
| `AI_JOB` | `aitbc ai submit` | [07](../scenarios/07_ai_job_submission.md), [34](../scenarios/34_hub_customer_node_e2e.md) | [submit-compute-request](../features/submit-compute-request.md), [get-compute-request](../features/get-compute-request.md), [list-compute-requests](../features/list-compute-requests.md), [compute-result-cache](../features/compute-result-cache.md) | |
| `MESSAGE` | `aitbc messaging`, `aitbc agent-msg` | [04](../scenarios/04_messaging_basics.md), [45](../scenarios/45_agent_msg_workflow.md) | [agent-messaging-paths](../features/agent-messaging-paths.md), [messaging-contracts](../features/messaging-contracts.md), [messaging-spam-economics](../features/messaging-spam-economics.md), [message-moderation](../features/message-moderation.md), [forum-topics](../features/forum-topics.md) | |
| `ESCROW_LOCK` | `aitbc market` jobs / `aitbc ai submit` (escrow created by market path) | [07](../scenarios/07_ai_job_submission.md), [34](../scenarios/34_hub_customer_node_e2e.md), [54](../scenarios/54_agent_paid_delegation.md), [75](../scenarios/75_market_escrow_jobs_options.md) | [escrow-verification](../features/escrow-verification.md), [create-payment](../features/create-payment.md), [3-market](../features/3-market.md) | |
| `ESCROW_RELEASE` | protocol-internal (settlement authority on job completion) | [07](../scenarios/07_ai_job_submission.md), [34](../scenarios/34_hub_customer_node_e2e.md), [48](../scenarios/48_performance_bonds_high_value.md) | [escrow-verification](../features/escrow-verification.md), [payment-status](../features/payment-status.md) | authority-signed, not wallet-submitted |
| `ESCROW_REFUND` | protocol-internal (settlement / refund path; `aitbc ai refund`, `aitbc market escrow refund` trigger it) | [25](../scenarios/25_job_payment_failure.md), [34](../scenarios/34_hub_customer_node_e2e.md), [44](../scenarios/44_stuck_tee_refund.md), [55](../scenarios/55_dispute_lifecycle.md) | [escrow-verification](../features/escrow-verification.md) | unsealed on bc-2 per ledger |
| `ESCROW_FEE_SWEEP` | protocol-internal (settlement sweeper, authority-signed) | no scenario — ops checker: [first-sweep-observation](../ops/first-sweep-observation.md) | — | sealed ×5; no feature doc |
| `GPU_REGISTER` / `GPU_ALLOCATE` / `GPU_DEREGISTER` | `aitbc gpu-onchain` | [09](../scenarios/09_gpu_listing.md) | [gpu-registration](../features/gpu-registration.md), [gpu-allocation](../features/gpu-allocation.md), [get-gpu-listing](../features/get-gpu-listing.md), [remove-gpu-listing](../features/remove-gpu-listing.md), [8-edge-gpu](../features/8-edge-gpu.md) | |
| `GPU_MARKET` (`offer`/`software_offer`/`software_job`) | `aitbc market offer`, job receipts | [26](../scenarios/26_gpu_nplus1_query.md), [34](../scenarios/34_hub_customer_node_e2e.md), [41](../scenarios/41_whisper_ffmpeg_shop_offers.md), [50](../scenarios/50_default_shop_offers.md) | [advertise-to-market](../features/advertise-to-market.md), [dynamic-pricing](../features/dynamic-pricing.md), [offer-history](../features/offer-history.md), [plugin-offers](../features/plugin-offers.md), [match-request](../features/match-request.md), [3-market](../features/3-market.md) | |
| `STAKE_LOCK` / `STAKE_RELEASE` | `aitbc stake` / `aitbc unstake`; `aitbc agent-staking` (8 leaves, `3465dc438`); coordinator-api `/stake` + `/v1/agent-staking/*` lifecycle (operator `payload.auth`) | [01](../scenarios/01_wallet_basics.md) (steps 26–27), [17](../scenarios/17_governance_voting.md), [83](../scenarios/83_stake_options.md) (refusals), **[87](../scenarios/87_agent_staking.md)** | [9-wallet](../features/9-wallet.md) | revived at v17 (`STATE_TRANSITION_V17_HEIGHT`); consensus `/v1/staking/*` unsealable at v17 (Refs #649, pending v18); agent-staking lane sealed via scenario 87; **no dedicated staking feature doc** |
| `BOND_LOCK` / `BOND_RELEASE` / `BOND_SLASH` | `aitbc bond` | [48](../scenarios/48_performance_bonds_high_value.md) | — | no feature doc; unsealed on bc-2 |
| `BOUNTY_LOCK` / `BOUNTY_PAYOUT` / `BOUNTY_REFUND` | `aitbc bounty` (deploy/submit/verify/dispute/expire/status — operator-signed, `3465dc438`); protocol-internal (coordinator-api `/bounties` signs `payload.auth` server-side) | **[86](../scenarios/86_bounty_lifecycle.md)** | — | revived at v17; `PAYOUT`/`REFUND` were unsealable unsigned under v9–v16; **no feature doc** |
| `BRIDGE_LOCK` / `BRIDGE_WITHDRAW` | `aitbc wallet bridge`, `aitbc bridge` | [20](../scenarios/20_cross_chain_transfer.md), [59](../scenarios/59_sepolia_buy_sell_ait.md), [76](../scenarios/76_bridge_options.md), **[88](../scenarios/88_bridge_island_lock_release.md)** | [2-bridge-cross-chain](../features/2-bridge-cross-chain.md), [bridge-router](../features/bridge-router.md), [bridge-monitoring](../features/bridge-monitoring.md) | |
| `BRIDGE_RELEASE` / `BRIDGE_REFUND` | protocol-internal (bridge monitor, authority-issued credits) | [59](../scenarios/59_sepolia_buy_sell_ait.md) end-to-end, **[88](../scenarios/88_bridge_island_lock_release.md)**; runbook: [bridge-release-exercise](../ops/bridge-release-exercise.md) | [bridge-monitoring](../features/bridge-monitoring.md) | reserved internal issuance; sealed on both bc-2 and island |
| `GOVERNANCE_PROPOSE` / `GOVERNANCE_VOTE` / `GOVERNANCE_EXECUTE` | `aitbc governance` (client-signed, relayed) | [17](../scenarios/17_governance_voting.md) | [4-governance](../features/4-governance.md), [apply-parameters](../features/apply-parameters.md), [arbitration-voting](../features/arbitration-voting.md), [authorize-arbitrator](../features/authorize-arbitrator.md) | |
| `LIQUIDITY_DEPOSIT` / `LIQUIDITY_WITHDRAW` / `LIQUIDITY_CLAIM` | `aitbc wallet liquidity-stake` / `liquidity-unstake` / `liquidity-claim`; `aitbc liquidity-stake`; `aitbc liquidity build-deposit`/`build-claim`/`build-withdraw` (RPC builder surface, `3465dc438`) | [01](../scenarios/01_wallet_basics.md), [83](../scenarios/83_stake_options.md) (refusals only) | [9-wallet](../features/9-wallet.md) | unsealed on bc-2; no dedicated feature doc |
| `RECEIPT_CLAIM` | protocol-internal (settlement RPC at escrow release, #687) | no scenario — replay suite only | — | live emitter wired (#687); replay-suite coverage stands |
| `IPFS_SUBSCRIPTION` | `aitbc ipfs` | [11](../scenarios/11_ipfs_storage.md) | [register-subscription](../features/register-subscription.md), [get-subscribers](../features/get-subscribers.md) | |
| `EXCHANGE` | `aitbc exchange` trading order anchors (buy/sell/cancel) | — | [7-trading](../features/7-trading.md), [exchange-rates](../features/exchange-rates.md) | sealed (5564, 5565) but no scenario plays it |

---

## Table B — feature docs → the mesh

One row per `docs/features/*.md` (all 92). `—` = no entry in that
namespace (internal/read-side features mostly emit no chain records and
are covered by no scenario).

| Feature doc | Record type(s) emitted | Scenario(s) | CLI path |
|---|---|---|---|
| [1-blockchain-core](../features/1-blockchain-core.md) | all (apply path) | 03, 15, 51 | `aitbc blockchain`, `aitbc monitor`, `aitbc explorer` |
| [2-bridge-cross-chain](../features/2-bridge-cross-chain.md) | `BRIDGE_LOCK`, `BRIDGE_WITHDRAW`, `BRIDGE_RELEASE`, `BRIDGE_REFUND` | 20, 59, 88 | `aitbc bridge`, `aitbc crosschain`, `aitbc wallet bridge` |
| [3-market](../features/3-market.md) | `GPU_MARKET`, `ESCROW_LOCK`/`RELEASE`/`REFUND` | 26, 34, 41, 50, 75, 78 | `aitbc market` |
| [4-governance](../features/4-governance.md) | `GOVERNANCE_*` | 17, 67, 80 | `aitbc governance`, `aitbc grant`, `aitbc economics` |
| [5-mining-pool-hub](../features/5-mining-pool-hub.md) | — | 13, 36 | `aitbc mining`, `aitbc pool-hub` |
| [6-agent-coordination](../features/6-agent-coordination.md) | `MESSAGE` | 04, 10, 16, 45, 54 | `aitbc agent`, `agent-comm`, `agent-msg`, `agent-task` |
| [7-trading](../features/7-trading.md) | `EXCHANGE` | 06, 33, 62, 77, 79 | `aitbc exchange`, `exchange-island`, `trade` |
| [8-edge-gpu](../features/8-edge-gpu.md) | `GPU_*` | 09, 26, 60 | `aitbc gpu`, `gpu-onchain`, `edge` |
| [9-wallet](../features/9-wallet.md) | `TRANSFER`, `STAKE_*`, `LIQUIDITY_*` | 01, 52, 81, 83 | `aitbc wallet`, `stake`, `unstake`, `liquidity-stake` |
| [10-security](../features/10-security.md) | — | 19, 30, 32 | `aitbc security`, `aitbc config` |
| [11-cli](../features/11-cli.md) | — | 27, 63 | `aitbc` (all groups) |
| [12-infrastructure](../features/12-infrastructure.md) | — | 21, 51 | `aitbc system`, `aitbc start` |
| [add-nodes-edges](../features/add-nodes-edges.md) | — | — | — |
| [advertise-to-market](../features/advertise-to-market.md) | `GPU_MARKET` | 34, 41, 50 | `aitbc market offer` |
| [agent-messaging-paths](../features/agent-messaging-paths.md) | `MESSAGE` | 04, 45 | `aitbc agent-msg`, `aitbc messaging` |
| [agent-reputation](../features/agent-reputation.md) | — | 12 | `aitbc reputation` |
| [apply-parameters](../features/apply-parameters.md) | `GOVERNANCE_EXECUTE` | 17, 58 | `aitbc governance`, `aitbc economics` |
| [arbitration-voting](../features/arbitration-voting.md) | — | 55 | `aitbc dispute` |
| [authorize-arbitrator](../features/authorize-arbitrator.md) | — | 55 | `aitbc dispute` |
| [auto-import](../features/auto-import.md) | — | 63 | `aitbc config` |
| [blockchain-registration](../features/blockchain-registration.md) | — | 05, 61 | `aitbc node` |
| [bridge-monitoring](../features/bridge-monitoring.md) | `BRIDGE_RELEASE`, `BRIDGE_REFUND` (authority side) | 59, 88 | `aitbc bridge` |
| [bridge-router](../features/bridge-router.md) | `BRIDGE_LOCK`, `BRIDGE_WITHDRAW` | 20, 88 | `aitbc bridge`, `aitbc crosschain` |
| [call-contract](../features/call-contract.md) | — | 73 | `aitbc contract` |
| [compute-result-cache](../features/compute-result-cache.md) | — | 07 | `aitbc ai` |
| [coordinator-heartbeat](../features/coordinator-heartbeat.md) | — | 16 | `aitbc agent-comm` |
| [create-knowledge-graph](../features/create-knowledge-graph.md) | — | — | — |
| [create-payment](../features/create-payment.md) | `TRANSFER`, `ESCROW_LOCK` | 02, 07 | `aitbc transactions send`, `aitbc market` |
| [create-pool](../features/create-pool.md) | — | 36 | `aitbc pool-hub` |
| [delete-pool](../features/delete-pool.md) | — | — | `aitbc pool-hub` |
| [deploy-contract](../features/deploy-contract.md) | — | 73 | `aitbc contract`, `aitbc deploy` |
| [dynamic-pricing](../features/dynamic-pricing.md) | `GPU_MARKET` (offer repricing) | 41, 50 | `aitbc market` |
| [edge-advertise](../features/edge-advertise.md) | — | 60 | `aitbc edge` |
| [edge-health](../features/edge-health.md) | — | 60 | `aitbc edge`, `aitbc health` |
| [edge-node-query](../features/edge-node-query.md) | — | 60 | `aitbc edge` |
| [edge-node-registration](../features/edge-node-registration.md) | — | 60 | `aitbc edge` |
| [escrow-verification](../features/escrow-verification.md) | `ESCROW_*` (verify/read) | 34, 44, 55, 75 | `aitbc market escrow` |
| [exchange-rates](../features/exchange-rates.md) | — (reads) | 06, 33 | `aitbc exchange-island` |
| [file-dispute](../features/file-dispute.md) | — | 55 | `aitbc dispute` |
| [forum-topics](../features/forum-topics.md) | `MESSAGE` | 04 | `aitbc messaging` |
| [get-agent-identity](../features/get-agent-identity.md) | — | 10 | `aitbc agent` |
| [get-compute-request](../features/get-compute-request.md) | — | 07 | `aitbc ai` |
| [get-gpu-listing](../features/get-gpu-listing.md) | — | 09, 26 | `aitbc gpu`, `gpu-onchain` |
| [get-knowledge-graph](../features/get-knowledge-graph.md) | — | — | — |
| [get-lease-status](../features/get-lease-status.md) | — | — | — |
| [get-pool](../features/get-pool.md) | — | 36 | `aitbc pool-hub` |
| [get-ratings](../features/get-ratings.md) | — | 12 | `aitbc reputation` |
| [get-subscribers](../features/get-subscribers.md) | — | 11 | `aitbc ipfs` |
| [gpu-allocation](../features/gpu-allocation.md) | `GPU_ALLOCATE` | 09 | `aitbc gpu-onchain` |
| [gpu-metrics](../features/gpu-metrics.md) | — | 60 | `aitbc gpu`, `aitbc edge` |
| [gpu-query](../features/gpu-query.md) | — | 09, 26 | `aitbc gpu` |
| [gpu-registration](../features/gpu-registration.md) | `GPU_REGISTER` | 09 | `aitbc gpu-onchain` |
| [heartbeat](../features/heartbeat.md) | — | 16 | `aitbc agent-comm` |
| [http-rpc-compression](../features/http-rpc-compression.md) | — | 68 | `aitbc http` |
| [install-plugin](../features/install-plugin.md) | — | 43 | `aitbc plugin` |
| [join-pool](../features/join-pool.md) | — | 36 | `aitbc mining`, `pool-hub` |
| [leave-pool](../features/leave-pool.md) | — | — | `aitbc pool-hub` |
| [list-compute-requests](../features/list-compute-requests.md) | — | 07 | `aitbc ai` |
| [list-contracts](../features/list-contracts.md) | — | 73 | `aitbc contract` |
| [list-edge-nodes](../features/list-edge-nodes.md) | — | 60 | `aitbc edge` |
| [list-gpus](../features/list-gpus.md) | — | 09, 60 | `aitbc gpu` |
| [list-plugins](../features/list-plugins.md) | — | 43 | `aitbc plugin` |
| [list-pools](../features/list-pools.md) | — | 36 | `aitbc pool-hub` |
| [market-analytics](../features/market-analytics.md) | — | 18 | `aitbc analytics` |
| [market-stats](../features/market-stats.md) | — | 18 | `aitbc analytics`, `market` |
| [match-request](../features/match-request.md) | `GPU_MARKET` (match → job) | 07, 34 | `aitbc market`, `aitbc ai` |
| [message-moderation](../features/message-moderation.md) | `MESSAGE` | 04 | `aitbc messaging` |
| [messaging-contracts](../features/messaging-contracts.md) | `MESSAGE` | 04, 45 | `aitbc messaging` |
| [messaging-spam-economics](../features/messaging-spam-economics.md) | `MESSAGE` | — | `aitbc messaging` |
| [offer-history](../features/offer-history.md) | — | 26, 78 | `aitbc market` |
| [payment-status](../features/payment-status.md) | — (reads `TRANSFER`/`ESCROW_*`) | 02, 07 | `aitbc transactions`, `aitbc market escrow` |
| [performance-logging](../features/performance-logging.md) | — | 68 | `aitbc performance` |
| [plugin-offers](../features/plugin-offers.md) | `GPU_MARKET` | 43 | `aitbc plugin`, `aitbc market` |
| [pool-miners](../features/pool-miners.md) | — | 36 | `aitbc pool-hub` |
| [pool-stats](../features/pool-stats.md) | — | 36 | `aitbc pool-hub` |
| [prometheus-metrics](../features/prometheus-metrics.md) | — | 15 | `aitbc prometheus`, `aitbc monitor` |
| [query-disputes](../features/query-disputes.md) | — | 55 | `aitbc dispute` |
| [rate-offer](../features/rate-offer.md) | — | 12 | `aitbc reputation`, `aitbc market` |
| [readiness-checks](../features/readiness-checks.md) | — | 21 | `aitbc health`, `aitbc system` |
| [register-agent-identity](../features/register-agent-identity.md) | — | 10, 16 | `aitbc agent`, `agent-comm` |
| [register-subscription](../features/register-subscription.md) | `IPFS_SUBSCRIPTION` | 11 | `aitbc ipfs` |
| [remove-gpu-listing](../features/remove-gpu-listing.md) | `GPU_DEREGISTER` | 09 | `aitbc gpu-onchain` |
| [request-logging](../features/request-logging.md) | — | — | — |
| [scan-gpus](../features/scan-gpus.md) | — | 09, 60 | `aitbc gpu` |
| [submit-compute-request](../features/submit-compute-request.md) | `AI_JOB` | 07, 34 | `aitbc ai submit` |
| [submit-evidence](../features/submit-evidence.md) | — | 55 | `aitbc dispute` |
| [sync-ratings](../features/sync-ratings.md) | — | 12 | `aitbc reputation` |
| [update-capabilities](../features/update-capabilities.md) | — | 10, 16 | `aitbc agent` |
| [update-pool](../features/update-pool.md) | — | — | `aitbc pool-hub` |
| [verify-agent-identity](../features/verify-agent-identity.md) | — | 10 | `aitbc agent` |
| [verify-evidence](../features/verify-evidence.md) | — | 55 | `aitbc dispute` |
| [wallet-balance-info](../features/wallet-balance-info.md) | — (reads `TRANSFER` effects) | 01, 81 | `aitbc wallet` |

---

## Asymmetries observed

- **Scenario → feature-doc links are absent.** Zero of the 92 feature docs
  reference `docs/scenarios/`; the mesh is currently maintained only from
  the scenario side (the coverage ledger). This table is the first
  reverse index.
- **Revived v17 record types lack feature docs.** `BOUNTY_*` (scenario 86)
  and the staking types exercised via `/v1/agent-staking/*` (scenario 87)
  have no `docs/features/*.md` counterpart; `BOND_*` (scenario 48) also
  has none — Table A marks them `—`.
- **Protocol-internal emitters have no CLI column entry** by design:
  `ESCROW_RELEASE`, `ESCROW_REFUND` (triggered but authority-signed),
  `ESCROW_FEE_SWEEP`, `RECEIPT_CLAIM`, `BRIDGE_RELEASE`/`BRIDGE_REFUND`,
  `BOUNTY_*` — their only coverage is the replay suite, an ops checker,
  or an operator-signed coordinator path, per decision
  [V-1](../decisions/v1-v9-live-exercise-waivers.md).
- **`EXCHANGE` is sealed but scenario-less** — the only record type with
  seal evidence yet no play; trading scenarios (06/33/77/79) exercise the
  CLI surface without anchoring the type.
- **`LIQUIDITY_*` is unsealed and lightly documented** — only
  [9-wallet](../features/9-wallet.md) covers the wallet side; no
  dedicated liquidity feature doc exists.
- **Scenario coverage ≠ record coverage.** Many scenarios (21–33 hardening
  plays, 53 dashboards, 60–85 option/refusal plays) intentionally seal no
  new type; they validate CLI/service behaviour, which is why Table B's
  record column is mostly `—`.

## See also

- [Scenario index & coverage ledger](../scenarios/README.md) — the spine
- [Features overview](../FEATURES.md) — feature-doc catalog
- [CLI reference](./1_cli-reference.md) — full command list
- [GLOSSARY](./GLOSSARY.md)
