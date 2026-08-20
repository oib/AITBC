# AITBC Agent Scenarios

**Levels**: Beginner (scenarios 01-20), Intermediate (scenarios 21-35)
**Prerequisites**: AITBC CLI (`aitbc`) installed, basic Python knowledge
**Estimated Time**: 10-30 minutes per scenario
**Last Updated**: 2026-08-20
**Version**: 1.4

## Navigation Path

[Documentation Home](../README.md) > **Agent Scenarios** > *You are here*

breadcrumb: Home > Scenarios > Overview

---

## What's in this directory

This directory contains 35 scenarios (20 beginner + 15 intermediate) demonstrating how AI agents use AITBC features via the real `aitbc` CLI and the `aitbc_agent` SDK, plus live verification scenarios for shop-node fixes. Each scenario focuses on one feature category and includes both CLI workflows and Python SDK examples grounded in the current API surface.

> **Note**: These scenarios replace the earlier hermes-era scenario docs that were removed in the "AI Trusted Blockchain Computing" rebrand. They target the **real** CLI command groups and the **real** `aitbc_agent` SDK package (`packages/py/aitbc-agent-sdk/`), not the retired mock training infrastructure.

### Beginner Scenarios (Single-Feature Focus)

| # | Scenario | Focus | CLI Group |
|---|----------|-------|-----------|
| 01 | [Wallet Basics](./01_wallet_basics.md) | Create, manage, backup wallets | `aitbc wallet` |
| 02 | [Transaction Sending](./02_transaction_sending.md) | Send and track transactions | `aitbc transactions` |
| 03 | [Genesis Deployment](./03_genesis_deployment.md) | Initialize and verify a chain | `aitbc genesis` |
| 04 | [Messaging Basics](./04_messaging_basics.md) | Agent-to-agent messaging | `aitbc messaging`, `aitbc agent` |
| 05 | [Island Creation](./05_island_creation.md) | Create and join blockchain islands | `aitbc node island` |
| 06 | [Basic Trading](./06_basic_trading.md) | Buy/sell on the exchange | `aitbc exchange-island` |
| 07 | [AI Job Submission](./07_ai_job_submission.md) | Submit and monitor AI jobs | `aitbc ai` |
| 08 | [Marketplace Bidding](./08_marketplace_bidding.md) | List and buy on the marketplace | `aitbc marketplace` |
| 09 | [GPU Listing](./09_gpu_listing.md) | Register and allocate GPUs | `aitbc gpu`, `aitbc gpu-onchain` |
| 10 | [Agent SDK Identity](./10_agent_sdk_identity.md) | Create and configure agents | `aitbc agent`, `aitbc_agent` |
| 11 | [IPFS Storage](./11_ipfs_storage.md) | Store and retrieve data on IPFS | `aitbc_agent` (IPFS ops) |
| 12 | [Reputation Management](./12_reputation_management.md) | Query and contribute reputation | `aitbc reputation` |
| 13 | [Mining Setup](./13_mining_setup.md) | Start and monitor mining | `aitbc mining` |
| 14 | [Staking Basics](./14_staking_basics.md) | Stake and unstake tokens | `aitbc wallet` |
| 15 | [Blockchain Monitoring](./15_blockchain_monitoring.md) | Dashboards, metrics, alerts | `aitbc monitor`, `aitbc explorer` |
| 16 | [Agent Registration](./16_agent_registration.md) | Register on the coordinator network | `aitbc agent-comm` |
| 17 | [Governance Voting](./17_governance_voting.md) | Propose and vote on governance | `aitbc operations governance` |
| 18 | [Analytics Collection](./18_analytics_collection.md) | Summaries, monitoring, predictions | `aitbc analytics` |
| 19 | [Security Setup](./19_security_setup.md) | Audit, scan, and patch | `aitbc security` |
| 20 | [Cross-Chain Transfer](./20_cross_chain_transfer.md) | Swaps and bridge operations | `aitbc crosschain`, `aitbc bridge` |

### Intermediate Scenarios (Shop-Node Live Verification)

These scenarios verify fixes applied to shop-node services (v0.10.3). They test real running services on a live shop node and confirm that bugs (A3-A14, B5-B15) have been resolved.

| # | Scenario | Tasks | Focus |
|---|----------|-------|-------|
| 21 | [Service Startup & Connectivity](./21_service_startup_connectivity.md) | A3, B9 | Service startup, port corrections, edge registration logging |
| 22 | [Bridge RPC Input Validation](./22_bridge_rpc_validation.md) | B13 | Pydantic 422 validation on all bridge RPC endpoints |
| 23 | [Mempool Eviction Order](./23_mempool_eviction_order.md) | B15 | Oldest low-fee tx evicted first (not newest) |
| 24 | [Fire-and-Forget Task Error Logging](./24_task_error_logging.md) | B8, B9 | Background task exceptions logged, not swallowed |
| 25 | [Job Submission with Payment Failure](./25_job_payment_failure.md) | B12 | Payment rollback, no orphaned records, job proceeds |
| 26 | [GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md) | B14 | Batch-fetch GPUs in single WHERE IN query |
| 27 | [CLI Commands](./27_cli_commands.md) | A2, A7, A8, A3 | CLI commands work, correct ports, no crashes |
| 28 | [HTTP Client Resource Cleanup](./28_http_client_cleanup.md) | A12, A13, A14 | `__del__` warnings, context managers, FD stability |
| 29 | [Database Connection Leak](./29_database_connection_leak.md) | B7 | `__del__` closes connections, context manager support |
| 30 | [Secret Manager Thread Safety](./30_secret_manager_thread_safety.md) | A11 | Concurrent access with threading.Lock, 0 errors |
| 31 | [Async HTTP Client Non-Blocking](./31_async_http_client.md) | B5 | `httpx.AsyncClient` (not `requests` + `run_in_executor`) |
| 32 | [Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md) | A4, A5 | Production rejects missing/default/short secrets |
| 33 | [Exchange Financial Correctness — Gap Analysis](./33_exchange_financial_correctness.md) | B1, B2, B3, B4 | Audit which exchange implementation is running; test float drift, race conditions, session handling |
| 34 | [Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md) | A6 | Cross-network job submission, bridge queries, exchange trading; verify no hardcoded localhost URLs |
| 35 | [Fire-and-Forget Logging (B10/B11)](./35_fire_and_forget_logging_b10_b11.md) | B10, B11 | Agent-coordinator TaskRegistry + coordinator-api create_task_with_logging; exceptions logged, not swallowed |

---

## How to Use These Scenarios

1. **Install the AITBC CLI** — the `aitbc` binary should be on `$PATH` (entry point: `aitbc_cli.core.main:main`).
2. **Install the Agent SDK** — `pip install aitbc-agent-sdk` (package import: `aitbc_agent`).
3. **Run a local node** — most scenarios assume a blockchain node reachable at `http://localhost:8202` (RPC) and the coordinator API at `http://localhost:8203`.
4. **Work through scenarios in order** — each builds on the previous. Start with [01 Wallet Basics](./01_wallet_basics.md).
5. **Use the template** — [_TEMPLATE.md](./_TEMPLATE.md) is the structural template for all scenarios.

---

## Conventions

- All CLI examples use the real `aitbc` binary (not the retired `aitbc-cli`).
- All Python examples import from `aitbc_agent` (the real SDK package), e.g. `from aitbc_agent import Agent, AgentIdentity, AgentCapabilities`.
- Service ports: blockchain RPC `8202`, coordinator API `8203`, agent-coordinator `8107`. See [Service Ports Reference](../reference/SERVICE_PORTS.md) for the authoritative list.
- No references to the retired hermes context or mock training infrastructure.

---

## See Also

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Agents Documentation](../agents/README.md)
- [Getting Started for AI Agents](../agents/getting-started.md)

---

## Megaplan Status

The current codebase megaplan is the two-node hub/shop marketplace end-to-end flow (hub `hub.aitbc` ↔ shop `aitbc3`):

- GPU offers are advertised from the shop.
- AI jobs are submitted from the hub using authenticated coordinator API calls.
- The shop miner picks up, executes, and completes the job.
- Results and payment/escrow state are queried from the hub.
- The Agent SDK `ComputeConsumer` now supports `auth_token` and `coordinator_url` in `create(...)`.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.

Each scenario below has been refreshed to reflect the current API paths, ports, and JWT auth requirements.

---

*Last updated: 2026-08-20*
*Version: 1.4*
