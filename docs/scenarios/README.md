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

45 operator plays of **the AITBC software as it actually runs** on the public island (`hub.aitbc` ↔ shop `aitbc3`). Each play is driven by the real `aitbc` CLI. Python SDK examples are optional extras. Curl, `journalctl`, and `pytest` appear only as **validation** after a CLI step.

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
| 08 | [Marketplace Bidding](./08_marketplace_bidding.md) | List and buy **chains** | `aitbc marketplace` |
| 09 | [GPU Listing](./09_gpu_listing.md) | Register local GPUs; on-chain GPU records | `aitbc gpu`, `aitbc gpu-onchain` |
| 10 | [Agent SDK Identity](./10_agent_sdk_identity.md) | Create and configure agents | `aitbc agent` |
| 11 | [IPFS Storage](./11_ipfs_storage.md) | Store and retrieve content-addressed artifacts | `aitbc ipfs`, `aitbc oracle` |
| 12 | [Reputation Management](./12_reputation_management.md) | Query and contribute reputation | `aitbc reputation` |
| 13 | [Mining Setup](./13_mining_setup.md) | Start and monitor mining | `aitbc mining` |
| 14 | [Staking Basics](./14_staking_basics.md) | Stake and unstake tokens | `aitbc wallet` |
| 15 | [Blockchain Monitoring](./15_blockchain_monitoring.md) | Dashboards, metrics, alerts | `aitbc monitor`, `aitbc explorer` |
| 16 | [Agent Registration](./16_agent_registration.md) | Register on the coordinator network | `aitbc agent-comm` |
| 17 | [Governance Voting](./17_governance_voting.md) | Propose and vote | `aitbc governance`, `aitbc operations governance` |
| 18 | [Analytics Collection](./18_analytics_collection.md) | Summaries, monitoring, predictions | `aitbc analytics` |
| 19 | [Security Setup](./19_security_setup.md) | Audit, scan, and patch | `aitbc security` |
| 20 | [Cross-Chain Transfer](./20_cross_chain_transfer.md) | Swaps and bridge operations | `aitbc crosschain`, `aitbc bridge` |

GPU **software offers** (Ollama/Whisper/FFmpeg) use `aitbc market`, not `aitbc marketplace`. Scenario 08 is the older **chain listing** marketplace. Scenario 34 is the live shop-offer path.

### Intermediate Scenarios (Live Operator Plays)

These are operator hardening plays (21–35). The A/B task ids in each play are change-log cross-references to the original v0.10.3 hardening items (A3–A14, B5–B15), not bug-ticket reproductions.

| # | Scenario | Tasks | CLI group |
|---|----------|-------|-----------|
| 21 | [Service Startup & Connectivity](./21_service_startup_connectivity.md) | A3, B9 | `aitbc start`, `aitbc system`, `aitbc mining`, `aitbc edge`, `aitbc bridge` |
| 22 | [Bridge RPC Input Validation](./22_bridge_rpc_validation.md) | B13 | `aitbc bridge` |
| 23 | [Mempool Eviction Order](./23_mempool_eviction_order.md) | B15 | `aitbc transactions`, `aitbc simulate` |
| 24 | [Fire-and-Forget Task Logging](./24_task_error_logging.md) | B8, B9 | `aitbc system`, `aitbc network`, `aitbc edge` |
| 25 | [Job Payment Failure Handling](./25_job_payment_failure.md) | B12 | `aitbc ai` |
| 26 | [GPU Marketplace N+1 Query](./26_gpu_nplus1_query.md) | B14 | `aitbc market`, `aitbc gpu` |
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
| 37 | [On-Chain Performance Bonds](./37_performance_bonds.md) | P2.3 | `aitbc bond`, `aitbc market` |
|| 38 | [ZK Proofs for High-Value Jobs](./38_zk_high_value_jobs.md) | P2.1 | `aitbc ai` |

---

## How to Use These Scenarios

1. **Install the AITBC CLI** — `aitbc` on `$PATH` (entry point: `aitbc_cli.core.main:main`). Version on the live nodes is `0.10.18`.
2. **Prefer CLI over HTTP.** If a step cannot be done with `aitbc`, that is a CLI gap: fix the CLI, then keep the scenario in sync.
3. **Know which node you are on.** Hub services (coordinator 8203, exchange 8106, agent-coordinator 8107) often bind `127.0.0.1`. Shop/customer CLIs reach them through nginx (`https://hub.aitbc.bubuit.net/…`) or an SSH tunnel, not raw LAN ports. See scenario 34.
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
| `aitbc market` | coordinator / marketplace service | no | — |
| `aitbc wallet` | wallet daemon (8108) | no | — |
| `aitbc transactions` | blockchain RPC (8202) | no | — |
| `aitbc bridge` | blockchain RPC | no | — |
| `aitbc reputation` | coordinator reputation service | `(Simulated)` | coordinator not reachable |
| `aitbc messaging` | messaging RPC | `(Simulated)` | messaging service not reachable |
| `aitbc exchange-island` | exchange service (8106) | `(Simulated)` | exchange not reachable |
| `aitbc ipfs` | local Kubo daemon | filesystem CID shim | Kubo daemon not running |
| `aitbc tee launch` | local TEE runtime | `(Simulated)` | no TEE runtime present |
| `aitbc simulate` | — | always simulated | explicit simulation |

Scenario files that touch these groups include a note near the top. Live product-path scenarios (e.g. 34, 07, 48) produce real on-chain/coordinator data when the services are running.

## See Also

- [Closed design cycle & wish list](../DESIGN_CYCLE.md)
- [Release status and configuration drift](../releases/STATUS.md)
- [Agent SDK Documentation](../agent-sdk/README.md)
- [CLI README](../../cli/README.md)
- [Service Ports](../reference/SERVICE_PORTS.md)
- [Getting Started](../getting-started/README.md)

---

## Megaplan Status

The current product path is the two-node hub/shop marketplace loop:

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
|| 37 | [ZK Proof for High-Value Jobs](./37_zk_high_value_jobs.md) | High-value jobs require and verify a ZK receipt proof | `aitbc ai` |
|| 38 | TEE Attestation for Confidential Jobs | Confidential jobs require and verify a TEE attestation | `aitbc ai`, `aitbc tee` |
|| 39 | [Automatic Reinvestment from Released Escrow](./40_auto_reinvestment.md) | Auto-stake provider earnings on escrow release | `aitbc ai` |
|| 40 | [Whisper and FFmpeg Default Shop Offers](./41_whisper_ffmpeg_shop_offers.md) | Run transcription and media re-encode jobs via marketplace offers | `aitbc market` |
|| 41 | [Real IPFS Daemon behind `aitbc ipfs`](./42_ipfs_daemon.md) | Use Kubo for real CIDs and cross-node retrieval | `aitbc ipfs` |
|| 42 | [Compliance, Plugins, and White-Label Expansion](./43_compliance_plugins_white_label.md) | Brand plugins, compliance hooks, and plugin discovery | `aitbc brand`, `aitbc plugin`, `aitbc ai` |
|| 43 | [Refund a Failed TEE Job Escrow](./44_stuck_tee_refund.md) | Recover escrowed payment after TEE attestation is rejected | `aitbc ai refund`, `aitbc market escrow refund` |
|| 45 | [Agent-Message Workflow](./45_agent_msg_workflow.md) | Send, ping, and receive agent-to-agent messages with delivery status | `aitbc agent-msg` |
|| 46 | [Confidential TEE Jobs](./46_tee_confidential_jobs.md) | Confidential jobs require and verify a TEE attestation via the new CLI surface | `aitbc ai`, `aitbc tee` |
|| 47 | [ZK Proofs for High-Value Jobs](./47_zk_high_value_jobs.md) | High-value jobs require and verify a ZK receipt proof | `aitbc ai`, `aitbc zk` |
|| 48 | [Performance Bonds for High-Value Jobs](./48_performance_bonds_high_value.md) | High-value jobs require an active provider performance bond | `aitbc ai`, `aitbc bond` |
|| 49 | [Auto-Reinvest from Released Escrow](./49_auto_reinvest_escrow.md) | Escrow release automatically stakes a provider-defined percentage of earnings | `aitbc ai` |
|| 51 | [Multi-Validator PoA Soak](./51_multi_validator_poa_soak.md) | P1.4 multi-validator consensus soak before live enablement | `aitbc blockchain status`, `aitbc monitor metrics` |
| 50 | [Default Whisper, FFmpeg, and Ollama Shop Offers](./50_default_shop_offers.md) | Shop auto-publishes default software offers and customers run jobs with `aitbc market` | `aitbc market` |
