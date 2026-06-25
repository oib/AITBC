# AITBC Agent Scenarios

**Level**: Beginner track (20 scenarios)
**Prerequisites**: AITBC CLI (`aitbc`) installed, basic Python knowledge
**Estimated Time**: 15-30 minutes per scenario
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > **Agent Scenarios** > *You are here*

breadcrumb: Home > Scenarios > Overview

---

## What's in this directory

This directory contains 20 beginner scenarios demonstrating how AI agents use AITBC features via the real `aitbc` CLI and the `aitbc_agent` SDK. Each scenario focuses on one feature category and includes both CLI workflows and Python SDK examples grounded in the current API surface.

> **Note**: These scenarios replace the earlier hermes-era scenario docs that were removed in the "AI Trusted Blockchain Computing" rebrand. They target the **real** CLI command groups and the **real** `aitbc_agent` SDK package (`packages/py/aitbc-agent-sdk/`), not the retired mock training infrastructure.

### Beginner Scenarios (Single-Feature Focus)

| # | Scenario | Focus | CLI Group |
|---|----------|-------|-----------|
| 01 | [Wallet Basics](./01_wallet_basics.md) | Create, manage, backup wallets | `aitbc wallet` |
| 02 | [Transaction Sending](./02_transaction_sending.md) | Send and track transactions | `aitbc transactions` |
| 03 | [Genesis Deployment](./03_genesis_deployment.md) | Initialize and verify a chain | `aitbc genesis` |
| 04 | [Messaging Basics](./04_messaging_basics.md) | Agent-to-agent messaging | `aitbc messaging`, `aitbc agent` |
| 05 | [Island Creation](./05_island_creation.md) | Create and join blockchain islands | `aitbc node island` |
| 06 | [Basic Trading](./06_basic_trading.md) | Buy/sell on the exchange | `aitbc exchange_island` |
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

*Last updated: 2026-06-25*
*Version: 1.0*
