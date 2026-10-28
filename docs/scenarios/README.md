# AITBC Agent Scenarios

**Levels**: Beginner (scenarios 01–20), Intermediate (scenarios 21–36)
**Prerequisites**: AITBC CLI (`aitbc`) installed and on `$PATH`
**Estimated Time**: 10–30 minutes per scenario
**Last Updated**: 2026-08-21
**Version**: 1.5

## Navigation Path

[Documentation Home](../README.md) > **Agent Scenarios** > *You are here*

breadcrumb: Home > Scenarios > Overview

---

## What's in this directory

66 operator plays of **the AITBC software as it actually runs** on the public island (`<hub-node>` ↔ shop `<node2>`). Each play is driven by the real `aitbc` CLI. Python SDK examples are optional extras. Curl, `journalctl`, and `pytest` appear only as **validation** after a CLI step.

The closed economic loop these plays sit on (tokens → job → GPU → escrow → reputation) is documented in [DESIGN_CYCLE.md](../DESIGN_CYCLE.md). Features that are CLI shells or roadmap items are **not** given scenarios until they join that loop.

> These scenarios replace the retired hermes-era docs. They target the real `aitbc` binary (`aitbc_cli.core.main:main`) and the real `aitbc_agent` SDK (`packages/py/aitbc-agent-sdk/`).

### Beginner Scenarios (Single-Feature Focus)

| # | Scenario | Focus | CLI group |
|---|----------|-------|-----------|
| 01 | [Wallet Basics](./01_wallet_basics.md) | Create, manage, backup wallets | `aitbc wallet` |
| 02 | [Transaction Sending](./02_transaction_sending.md) | Send and track transactions | `aitbc transactions` |
| 03 | [Genesis Deployment](./03_genesis_deployment.md) | Initialize and verify a chain | `aitbc genesis` |
| 04 | [Messaging Basics](./04_messaging_basics.md) | Agent-to-agent messaging | `aitbc messaging`, `aitbc agent-msg` |
| 05 | [Island Creation](./05_island_creation.md) | Create and join blockchain islands | `aitbc node island` |
| 06 | [Basic Trading](./06_basic_trading.md) | Buy/sell on the island exchange | `aitbc exchange-island` |
| 07 | [AI Job Submission](./07_ai_job_submission.md) | Submit and monitor AI jobs | `aitbc ai` |
| 09 | [GPU Listing](./09_gpu_listing.md) | Register local GPUs; on-chain GPU records | `aitbc gpu`, `aitbc gpu-onchain` |
| 10 | [Agent SDK Identity](./10_agent_sdk_identity.md) | Create and configure agents | `aitbc agent` |
| 11 | [IPFS Storage](./11_ipfs_storage.md) | Store and retrieve content-addressed artifacts | `aitbc ipfs`, `aitbc oracle` |
| 12 | [Reputation Management](./12_reputation_management.md) | Query and contribute reputation | `aitbc reputation` |
| 13 | [Mining Setup](./13_mining_setup.md) | Start and monitor mining | `aitbc mining` |
| 14 | [Staking Basics](../archive/scenarios/14_staking_basics.md) *(retired — archived)* | Stake and unstake tokens | `aitbc wallet` |
| 15 | [Blockchain Monitoring](./15_blockchain_monitoring.md) | Dashboards, metrics, alerts | `aitbc monitor`, `aitbc explorer` |
| 16 | [Agent Registration](./16_agent_registration.md) | Register on the coordinator network | `aitbc agent-comm` |
| 17 | [Governance Voting](./17_governance_voting.md) | Propose and vote | `aitbc governance`, `aitbc operations governance` (deprecated/hidden) |
| 18 | [Analytics Collection](./18_analytics_collection.md) | Summaries, monitoring, predictions | `aitbc analytics` |
| 19 | [Security Setup](./19_security_setup.md) | Audit, scan, and patch | `aitbc security` |
| 20 | [Cross-Chain Transfer](./20_cross_chain_transfer.md) | Swaps and bridge operations | `aitbc crosschain`, `aitbc bridge` |

GPU **software offers** (Ollama/Whisper/FFmpeg) use `aitbc market`. Scenario 08 targeted the removed `aitbc market` **chain-listing** group and has been retired to `docs/archive/scenarios`. Scenario 34 is the live shop-offer path.

### Intermediate Scenarios (Live Operator Plays)

These are operator hardening plays (21–35). The A/B task ids in each play are change-log cross-references to the original v0.10.3 hardening items (A3–A14, B5–B15), not bug-ticket reproductions.

| # | Scenario | Tasks | CLI group |
|---|----------|-------|-----------|
| 21 | [Service Startup & Connectivity](./21_service_startup_connectivity.md) | A3, B9 | `aitbc start`, `aitbc system`, `aitbc mining`, `aitbc edge`, `aitbc bridge` |
| 22 | [Bridge RPC Input Validation](./22_bridge_rpc_validation.md) | B13 | `aitbc bridge` |
| 23 | [Mempool Eviction Order](./23_mempool_eviction_order.md) | B15 | `aitbc transactions`, `aitbc simulate` |
| 24 | [Fire-and-Forget Task Logging](./24_task_error_logging.md) | B8, B9 | `aitbc system`, `aitbc network`, `aitbc edge` |
| 25 | [Job Payment Failure Handling](./25_job_payment_failure.md) | B12 | `aitbc ai` |
| 26 | [GPU Market N+1 Query](./26_gpu_nplus1_query.md) | B14 | `aitbc market`, `aitbc gpu` |
| 27 | [CLI Commands](./27_cli_commands.md) | A2, A7, A8, A3 | `aitbc agent`, `aitbc pool-hub`, `aitbc mining`, `aitbc gpu`, `aitbc simulate` |
| 28 | [HTTP Client Resource Cleanup](./28_http_client_cleanup.md) | A12, A13, A14 | `aitbc agent`, `aitbc edge`, `aitbc bridge` |
| 29 | [Database Connection Leak](./29_database_connection_leak.md) | B7 | `aitbc system`, `aitbc explorer` |
| 30 | [Secret Manager Thread Safety](./30_secret_manager_thread_safety.md) | A11 | `aitbc security`, `aitbc config` |
| 31 | [Async HTTP Client Non-Blocking](./31_async_http_client.md) | B5 | `aitbc explorer`, `aitbc bridge` |
| 32 | [Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md) | A4, A5 | `aitbc security`, `aitbc config` |
| 33 | [Exchange Financial Correctness](./33_exchange_financial_correctness.md) | B1–B4 | `aitbc exchange-island` |
| 34 | [Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md) | A6 | `aitbc config`, `aitbc ai`, `aitbc wallet`, `aitbc market`, `aitbc bridge`, `aitbc exchange-island` |
| 35 | [Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md) | B10, B11 | `aitbc system`, `aitbc agent-comm` |
| 36 | [Pool Hub SLA End-to-End](./36_pool_hub_sla_e2e.md) | — | `aitbc pool-hub`, `aitbc mining` |

---

## How to Use These Scenarios

1. **Install the AITBC CLI** — `aitbc` on `$PATH` (entry point: `aitbc_cli.core.main:main`). Version on the live nodes is `0.10.18`.
2. **Prefer CLI over HTTP.** If a step cannot be done with `aitbc`, that is a CLI gap: fix the CLI, then keep the scenario in sync.
3. **Know which node you are on.** Hub services (coordinator 8203, exchange 8106, agent-coordinator 8107) often bind `127.0.0.1`. Shop/customer CLIs reach them through nginx (`https://hub.example.net/…`) or an SSH tunnel, not raw LAN ports. See scenario 34.
4. **Run a node** — blockchain RPC `8202`, coordinator `8203`, wallet `8108`. Authoritative ports: [Service Ports Reference](../reference/SERVICE_PORTS.md).
5. **Work through 01 → 20**, then the two-node product path **34 + 36**. Intermediate 21–33/35 are operator hardening, not a second beginner track.
6. **Use the template** — [_TEMPLATE.md](./_TEMPLATE.md).

---

## Conventions

- Primary tool: `aitbc` (never the retired `aitbc-cli` / `aitbc-cli.sh`).
- SDK extras import `aitbc_agent` (`from aitbc_agent import Agent, AgentIdentity, AgentCapabilities`).
- JWT for coordinator calls: use `aitbc auth login --wallet <wallet-name>` to store a token, then run commands without `--api-key`. For scripts, `aitbc auth login --wallet <wallet-name>` followed by commands that read the stored credential. Do not scrape `/etc/aitbc/*.env` for `JWT_SECRET` in a scenario.
- Label **live** vs **simulated** output. Several hub-only groups fall back to deterministic simulated data on a shop node; see the table below.
- No hermes / mock-training references.
- Do not invent commands. If `aitbc <group> --help` does not list it, it is not in the play.

---

## Live vs. simulated CLI output

Several CLI groups are **hub-only services**. When the service is not reachable, the CLI falls back to deterministic simulated output and labels it `(Simulated)`. Scenarios must say so, and operators must not mistake simulated tables for live network state.

| CLI group | Live source | Simulated fallback | Typical trigger |
|-----------|-------------|-------------------|-----------------|
| `aitbc ai` | coordinator (8203) | no | — |
| `aitbc market` | coordinator / market service | no | — |
| `aitbc wallet` | wallet daemon (8108) | no | — |
| `aitbc transactions` | blockchain RPC (8202) | no | — |
| `aitbc bridge` | blockchain RPC | no | — |
| `aitbc reputation` | coordinator reputation service | `(Simulated)` | coordinator not reachable |
| `aitbc messaging` | messaging RPC | `(Simulated)` | messaging service not reachable |
| `aitbc exchange-island` | exchange service (8106) | `(Simulated)` | exchange not reachable |
| `aitbc ipfs` | local Kubo daemon | filesystem CID shim | Kubo daemon not running |
| `aitbc tee` | coordinator TEE API + simulated quotes | simulated attestation path only | no SGX/SEV/TPM hardware in the fleet; hardware-backed TEE deferred to release 2.0 (`9079fb74a` deregistered the group briefly; `87c5f2df16` re-registered it) |
| `aitbc dispute` | blockchain RPC (`--node-url`) | no | — |
| `aitbc energy` | `IEnergyPricing` contract over `EVM_RPC_URL` | no — fails closed (`EVM RPC URL not configured`) | no EVM endpoint configured |
| `aitbc coin-requests` | agent/coordinator service + chain tx on `execute` | no | — |
| `aitbc economics` | coordinator `/v1/economic-proposals` (`propose`/`vote`/`status`, auth-gated) | `market`/`model`/`distributed` return `status: simulated` | — |
| `aitbc simulate` | — | always simulated | explicit simulation |

Scenario files that touch these groups include a note near the top. Live product-path scenarios (e.g. 34, 07, 48) produce real on-chain/coordinator data when the services are running.

**Registered groups:** the CLI currently registers ~70 top-level groups, including `agent`, `agent-comm`, `agent-msg`, `agent-task`, `gpu`, `gpu-onchain`, `tee`, `zk`, `health`, `http`, `dispute`, `bond`, `crosschain`, and `exchange-island`. `aitbc --help` is the authoritative list. Removed/absent groups: `aitbc market` (scenario 08, retired to `docs/archive/scenarios`).

## See Also

- [Closed design cycle & wish list](../DESIGN_CYCLE.md)
- [Release status and configuration drift](../releases/STATUS.md)
- [Agent SDK Documentation](../agent-sdk/README.md)
- [CLI README](../../cli/README.md)
- [Service Ports](../reference/SERVICE_PORTS.md)
- [Getting Started](../getting-started/README.md)

---

## Megaplan Status

The current product path is the two-node hub/shop market loop:

- Shop publishes GPU software offers (`aitbc market offer`).
- Hub/customer submits authenticated jobs (`aitbc auth login` followed by `aitbc ai submit`).
- Shop miner executes on Ollama; escrow releases on-chain.
- Pool hub SLA is readable from the shop (`aitbc pool-hub status`).

Live validation of that path (paid job + `ESCROW_RELEASE` + GPU offer) is recorded in scenario 34. Remaining product gaps live in [DESIGN_CYCLE.md](../DESIGN_CYCLE.md), not as extra scenarios.

---

*Last updated: 2026-08-21 (P2.5 default shop offers completed)*
*Version: 1.5*

### Advanced Scenarios (Product-Feature End-to-End)

| # | Scenario | Focus | CLI group |
|---|---|----------|-------|-----------|
|| 40 | [Automatic Reinvestment from Released Escrow](../archive/scenarios/40_auto_reinvestment.md) *(retired — archived)* | Auto-stake provider earnings on escrow release | `aitbc ai` |
|| 41 | [Whisper and FFmpeg Default Shop Offers](./41_whisper_ffmpeg_shop_offers.md) | Run transcription and media re-encode jobs via market offers | `aitbc market` |
|| 43 | [Compliance, Plugins, and White-Label Expansion](./43_compliance_plugins_white_label.md) | Brand plugins, compliance hooks, and plugin discovery | `aitbc brand`, `aitbc plugin`, `aitbc ai` |
|| 44 | [Refund a Failed TEE Job Escrow](./44_stuck_tee_refund.md) | Recover escrowed payment after TEE attestation is rejected | `aitbc ai refund`, `aitbc market escrow refund` |
|| 45 | [Agent-Message Workflow](./45_agent_msg_workflow.md) | Send, ping, and receive agent-to-agent messages with delivery status | `aitbc agent-msg` |
|| 46 | [Confidential TEE Jobs](./46_tee_confidential_jobs.md) | Confidential jobs require and verify a TEE attestation via the new CLI surface | `aitbc ai`, `aitbc tee` (registered; simulated attestation path) |
|| 47 | [ZK Proofs for High-Value Jobs](./47_zk_high_value_jobs.md) | High-value jobs require and verify a ZK receipt proof | `aitbc ai`, `aitbc zk` |
|| 48 | [Performance Bonds for High-Value Jobs](./48_performance_bonds_high_value.md) | High-value jobs require an active provider performance bond | `aitbc ai`, `aitbc bond` |
|| 49 | [Auto-Reinvest from Released Escrow](../archive/scenarios/49_auto_reinvest_escrow.md) *(retired — archived)* | Escrow release automatically stakes a provider-defined percentage of earnings | `aitbc ai` |
|| 51 | [Multi-Validator PoA Soak](./51_multi_validator_poa_soak.md) | P1.4 multi-validator consensus soak before live enablement | `aitbc blockchain status`, `aitbc monitor metrics` |
|| 52 | [Wallet Key Mismatch Recovery](./52_wallet_key_mismatch.md) | Recover or deprecate a wallet whose key does not match its expected address | `aitbc wallet info`, `aitbc wallet import-wallet` |
|| 53 | [Customer and Shop Dashboards](./53_dashboards.md) | P1.2 live customer/shop dashboards via `aitbc dashboard` | `aitbc dashboard customer`, `aitbc dashboard shop` |
|| 54 | [Paid Agent-to-Agent Delegation](./54_agent_paid_delegation.md) | Buyer agent hires a provider agent: `agent-msg` negotiation + on-chain escrow | `aitbc agent-task` |
| 50 | [Default Whisper, FFmpeg, and Ollama Shop Offers](./50_default_shop_offers.md) | Shop auto-publishes default software offers and customers run jobs with `aitbc market` | `aitbc market` |
|| 55 | [Dispute Lifecycle](./55_dispute_lifecycle.md) | File a dispute on an agreement, attach evidence, arbitrate, resolve the escrow | `aitbc dispute` |
|| 56 | [Energy Pricing & Provider Registry](./56_energy_pricing.md) | GPU energy profiles, on-chain energy floor, operator quote verification | `aitbc energy` (EVM_RPC_URL-gated) |
|| 57 | [Coin Requests](./57_coin_requests.md) | New-node initial coin grant: request → operator approve/reject → execute → reconcile | `aitbc coin-requests` |
|| 58 | [Economics & OpenClaw DAO](./58_economics_dao.md) | Economic-parameter proposals and votes via the coordinator | `aitbc economics` |
|| 59 | [Sepolia Buy/Sell AIT via the ETH Bridge](./59_sepolia_buy_sell_ait.md) | ETH→AIT deposit on node0, AIT→ETH withdraw on node2; BRIDGE_WITHDRAW sealing finding | `aitbc wallet bridge` |
| 60 | [Edge Compute & Islands](./60_edge_compute_islands.md) | Edge wallet, GPU inventory/metrics, island membership, edge databases, serve requests | `aitbc edge` |
| 61 | [Node Mesh Management](./61_node_mesh_management.md) | Node registry, probes, chain inventory, island health, bridge requests | `aitbc node` |
| 62 | [Inter-Chain Trading](./62_interchain_trade.md) | Chain registry, offer discovery, trade lifecycle, escrowed settlement | `aitbc trade` |
| 63 | [CLI Configuration](./63_cli_configuration.md) | Config keys, export/import, environments, profiles, secrets | `aitbc config` |
| 64 | [Operations Admin](./64_operations_admin.md) | Legacy umbrella group: agent registry, AI jobs, governance (deprecated surface) | `aitbc operations` |
| 65 | [Simulated Workloads](./65_simulate_workloads.md) | Local simulators: wallets, price, network, AI jobs; server-side gap documented | `aitbc simulate` |
| 66 | [Coordinator Workflows](./66_coordinator_workflows.md) | List, dry-run, execute, monitor, and stop coordinator workflows | `aitbc workflow` |
| 67 | [DAO Grants](./67_dao_grants.md) | Grant proposals, voting, milestone disbursement | `aitbc grant` |
| 68 | [RPC Performance](./68_rpc_performance.md) | Real RPC latency benchmark; tuner leaves documented as a CLI gap | `aitbc performance` |
| 69 | [Cluster Ops](./69_cluster_ops.md) | Cluster status/sync/balance (stub output documented) | `aitbc cluster` |
| 70 | [Script Runner](./70_script_runner.md) | Discover and run ops scripts through the CLI | `aitbc script` |
| 71 | [Reinvest Policy](./71_reinvest_policy.md) | Miner earnings reinvestment policy and split simulation | `aitbc reinvest` |
| 72 | [Developer Registry](./72_developer_registry.md) | DAO developer registration and listing | `aitbc developer` |
| 73 | [Contract Deploy & Call](./73_contract_deploy_call.md) | Generic contract deployment and method calls | `aitbc contract` |
| 74 | [Confidential Payments](./74_confidential_payments.md) | Confidential wallet balance and committed sends (simulated path) | `aitbc confidential` |
| 75 | [Market Escrow & Jobs Options](./75_market_escrow_jobs_options.md) | `market jobs` filters/formatting and `escrow create` optional flags (refusal play) | `aitbc market` |
| 76 | [Bridge CLI Options](./76_bridge_options.md) | `aitbc bridge` read-only flags plus money-path options exercised as free refusals | `aitbc bridge` |
| 77 | [Trade CLI Options](./77_trade_options.md) | `aitbc trade` options as reads/free refusals (401/404, array-shape drift) | `aitbc trade` |
| 80 | [Required CLI Flags](./80_required_flags.md) | last required-flag gaps exercised as free refusals | `aitbc operations`, `aitbc economics` |
| 83 | [Staking Options](./83_stake_options.md) | stake/unstake/liquidity-stake/reinvest options as wallet-gate refusals | `aitbc stake`, `aitbc unstake`, `aitbc liquidity-stake`, `aitbc reinvest` |
| 85 | [Secret-Form Coverage](./85_secret_forms.md) | password-file/stdin refusal plays across all leaves | `aitbc` all groups |
| 86 | [Bounty Lifecycle](./86_bounty_lifecycle.md) | deploy → submit → verify (`BOUNTY_PAYOUT`) + deploy → expire (`BOUNTY_REFUND`) — operator-signed via coordinator-api | coordinator-api REST, node RPC |
| 87 | [Agent Staking Lifecycle](./87_agent_staking.md) | stake → add → unbond → complete — operator-signed via coordinator-api; `locked_until` release gate | coordinator-api REST, node RPC |
| 88 | [Bridge Island Lock→Release](./88_bridge_island_lock_release.md) | bc-2 → bc-2-island-1 lock, finalizer/relayer proof, island-side BRIDGE_RELEASE | aitbc bridge, node RPC |
| 84 | [Last Uncovered Options](./84_last_options.md) | economics/trade leftovers as auth-gate refusals; census 0 non-secret | `aitbc economics`, `aitbc trade` |
| 78 | [Market CLI Options](./78_market_options.md) | `aitbc market` money-path and listing options as reads/free refusals (offer-resolution, wallet, quote-verification) | `aitbc market` |
| 79 | [Exchange CLI Options](./79_exchange_options.md) | `aitbc exchange` + `exchange-island` options as reads/free refusals (wallet gate, cap, island credentials, verifier drift) | `aitbc exchange` |
| 80 | [Required-Flag Coverage — operations & economics](./80_required_flags.md) | Last four required CLI options exercised as free refusals (wallet gate, lock-days guard, invalid choice) | `aitbc operations`, `aitbc economics` |
| 81 | [Wallet CLI Options](./81_wallet_options.md) | `aitbc wallet` options as reads/free refusals (wallet gate, dead endpoints, bridge status `--hub-url` drift) | `aitbc wallet` |
| 82 | [Moneypath Options](./82_moneypath_options.md) | operations/transactions/eth options as reads/free refusals | `aitbc operations`, `aitbc transactions`, `aitbc eth` |

---

## On-chain record coverage

The chain accepts 32 transaction types (`V9_METRIC_KNOWN_TX_TYPES` in
`apps/blockchain-node/src/aitbc_chain/state/v9_policy.py`). Scenarios are
organized by feature, not by type — this table maps every record type to
the play(s) that can seal it on-chain.

The **sealed on bc-2** column is the running 32-type ledger — append as seals land (Coder D folds).

| Record type | Emitted by | Scenario(s) | sealed on bc-2 |
|---|---|---|---|
| `TRANSFER` | `aitbc transactions send` | 02, 59 | 9037 |
| `AI_JOB` | `aitbc ai submit` | 07, 34 | 8720 `0xcaeb41d4…bd68` |
| `MESSAGE` | `aitbc messaging`, `aitbc agent-msg` | 04, 45 | 8701 `0x22dc0dcc…a76b` |
| `ESCROW_LOCK` | market job escrow | 07, 34, 54, 75 | 9042 |
| `ESCROW_RELEASE` | settlement authority on job completion | 07, 34, 48 | 9046 |
| `ESCROW_REFUND` | settlement authority / refund path | 25, 34, 44, 55 | — |
| `ESCROW_FEE_SWEEP` | settlement sweeper (protocol-emitted, authority-signed) | no scenario — ops checker: [first-sweep-observation](../ops/first-sweep-observation.md) | 8744–8749 ×5 (`0xdbbb515d…c8d4` +4) |
| `GPU_REGISTER` / `GPU_ALLOCATE` / `GPU_DEREGISTER` | `aitbc gpu-onchain` | 09 | REGISTER 8702 `0xf356e94e…5d91`; ALLOCATE 8704 `0x6703780c…fc5b`; DEREGISTER 9038 |
| `GPU_MARKET` (`offer`/`software_offer`/`software_job`) | `aitbc market offer`, job receipts | 26, 34, 41, 50 | 9040, 9044 |
| `STAKE_LOCK` / `STAKE_RELEASE` | `aitbc stake` / `aitbc unstake` (wallet-signed) → revived staking RPC; coordinator-api `/stake` lifecycle (operator `payload.auth`) | 01 steps 26–27, 17, **87**; 83 — client-side wallet-gate refusals; gated live at v17+ (`STATE_TRANSITION_V17_HEIGHT`, 410 while unarmed); **blocked** — consensus `/v1/staking/*` path unsealable at v17 (single-node committed-row defect, Refs #649, pending v18 — [v14-aux-root-nondeterminism](../design/v14-aux-root-nondeterminism.md)); agent-staking `/v1/agent-staking/*` path (scenario 87) remains exercisable | LOCK 8912 `0x4a18e3f3` (agent-staking lane); RELEASE — |
| `BOND_LOCK` / `BOND_RELEASE` / `BOND_SLASH` | `aitbc bond` | 48 | — |
| `BOUNTY_LOCK` / `BOUNTY_PAYOUT` / `BOUNTY_REFUND` | protocol escrow via revived bounty surface — coordinator-api `/bounties` lifecycle signs operator `payload.auth` server-side | **86** — deploy→submit→verify (`PAYOUT`) + deploy→expire (`REFUND`), gated live at v17+; `PAYOUT`/`REFUND` were unsealable unsigned under v9–v16 | LOCK 8904 `0x49dc1b37` (+8908 `0xa3a804f3`); PAYOUT 8908 `0x693ef99a`; REFUND 8912 `0xf8c98983` |
| `BRIDGE_LOCK` / `BRIDGE_WITHDRAW` | `aitbc wallet bridge`, `aitbc bridge` | 20, 59, 76; **88** — first live bc-2 → bc-2-island-1 lock at both finality tiers (pending the island deploy) | LOCK 8932 `0xfb2bb32c…` + 9004 `0x1dc9a5d8…`; WITHDRAW 8723 `0x74301648…a3656` |
| `BRIDGE_RELEASE` / `BRIDGE_REFUND` | bridge monitor (authority-issued credits) | 59 end-to-end; **88** — the live `BRIDGE_RELEASE` exercise reserved per V-1 (pending the island deploy) — governing runbook: [bridge-release-exercise](../ops/bridge-release-exercise.md) | RELEASE island @156 `b13a6cdc…` + @198 `0aca483b…` **and bc-2 @9349 ×2** (reverse direction — island locks @532/@558, recipient `0x08aB…` → 1,115,390) — sealed on both chains; REFUND 9116 (lock @9111 `pending`→`refunded`, +5000 net of 5 fee) |
| `GOVERNANCE_PROPOSE` / `GOVERNANCE_VOTE` / `GOVERNANCE_EXECUTE` | `aitbc governance` (client-signed, relayed) | 17 | PROPOSE 8708 `0xee997ce3…282c`; VOTE 8716 `0xdfe148c9…dcd6`; EXECUTE 9278 (executor `0xD9CC189c`, `governance_sweep_marker=bc-2-live-exercise` applied — #issuecomment-5226) |
| `LIQUIDITY_DEPOSIT` / `LIQUIDITY_WITHDRAW` / `LIQUIDITY_CLAIM` | `aitbc wallet liquidity-stake` / `liquidity-unstake` / `liquidity-claim` | 01; 83 (refusals only) | — |
| `RECEIPT_CLAIM` | settlement RPC — emitted by the node at escrow release when the coordinator hands over the signed receipt of record (#687); the claim carries the issuance record so apply materialises the row | no scenario — replay suite only | — (live emitter wired #687; replay-suite coverage stands) |
| `IPFS_SUBSCRIPTION` | `aitbc ipfs` | 11 | 9040 |
| `EXCHANGE` | `aitbc exchange` trading order anchors (buy/sell/cancel) | — | 5564, 5565 |

### Why four types have no play

`ESCROW_FEE_SWEEP` and `RECEIPT_CLAIM` are emitted by the node
or the settlement authority — a wallet cannot submit them — and
`BRIDGE_RELEASE`/`BRIDGE_REFUND` are reserved internal issuance. (`BOUNTY_*`
is no longer replay-only: scenario 86 plays the operator-signed lifecycle
once v17 is armed.) Per
operator decision
[V-1](../decisions/v1-v9-live-exercise-waivers.md), live exercise of the
types that never sealed under v9 is waived in favor of
`test_v9_type_coverage_replay.py::test_v9_type_replayed[<TYPE>]`
(fixture-signed blocks replayed twice asserting identical state). That
suite — not this directory — is the canonical per-type coverage.

Post-v17 note (28 Oct): under v9–v16 the protocol-emitted
`STAKE_*`/`BOUNTY_*` transfers were *unsealable* (unsigned top level,
v9 exempts only `BRIDGE_*`). v17 — `STATE_TRANSITION_V17_HEIGHT` —
admits them carrying verified `payload.auth`, and the retired RPC
surfaces return behind an activation gate (HTTP 410 while unarmed): see
[v17 resolution](../design/v9-unsigned-protocol-transfers.md#v17-resolution--option-1-implemented-staking--bounty)
and [v17-activation-runbook](../ops/v17-activation-runbook.md). The
`HTLC_*` and unsigned `AUTO_STAKE` shapes remain dead — no auth to
verify — so their replay-suite citations still stand.
