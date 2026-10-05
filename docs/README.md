# AITBC documentation

This is the documentation hub for AITBC. For the product overview and
welcome page, see the root [README](../README.md); for the full file
catalog, see the [master index](MASTER_INDEX.md). New to the network:
[getting started](getting-started/README.md), then
[quick start](getting-started/quick-start.md).

## Pick your path

| I am... | Start here |
|---|---|
| New user or operator | [getting-started/](getting-started/) |
| Hub operator | [getting-started/setup-service-selection.md](getting-started/setup-service-selection.md) |
| Shop / GPU provider | [getting-started/mining/miner-quick-start.md](getting-started/mining/miner-quick-start.md) |
| Client / customer | [getting-started/node-quickstart.md](getting-started/node-quickstart.md) |
| Developer | [development/1_overview.md](development/1_overview.md) |
| Security / operations | [security/](security/) or [deployment/](deployment/) |

## Core documentation

- [getting-started/](getting-started/) — installation, configuration, role selection, node quick starts
- [apps/](apps/) — app catalog and per-app landing pages
- [cli/](cli/) — CLI documentation and the CLI command reference
- [blockchain/](blockchain/) — blockchain node, consensus, networking, operations
- [agent-coordinator/](agent-coordinator/) — agent coordination service docs
- [market/](market/) — market and exchange documentation
- [mining/](mining/) — mining and GPU provider docs
- [reference/](reference/) — service ports, glossary, quick lookup
- [releases/](releases/) — release notes and current [STATUS.md](releases/STATUS.md)
- [scenarios/](scenarios/) — end-to-end usage scenarios (`aitbc` CLI plays)
- [DESIGN_CYCLE.md](DESIGN_CYCLE.md) — current software loop, gaps, and wish list
- [decisions/](decisions/) — dated decisions with their recorded reasons

## Operations runbooks

Operator procedures for the live fleet:

- [v9 pre-pin checklist](ops/v9-pre-pin-checklist.md) — the gate that must
  be green before pinning the v9 authorization height.
- [Bridge deposit canary](ops/bridge-canary-runbook.md) — staged
  ETH→AIT canary after the shadow window.
- [V-5 replay inventory](ops/v5-replay-inventory.md) — checkpoint-replay
  plan, verified inputs, and the known height-11 divergence.
- [Escrow routing](ops/escrow-routing.md) — escrow operations must reach
  the node that created the row.
- [Escrow settlement ops](ops/escrow-settlement-ops.md) — the
  lock→settle pipeline and per-alert response for the escrow settlement,
  fork, and v9 alerts.
- [Legacy escrow residue payout](ops/legacy-escrow-residue-payout.md) —
  the Option-A batch runbook: one authority-signed ESCROW_RELEASE per
  legacy custody account, paid to the provider in the sealed lock.
- [Legacy escrow residue payout](ops/legacy-escrow-residue-payout.md) —
  the Option-A batch runbook: one authority-signed ESCROW_RELEASE per
  legacy custody account, paid to the provider in the sealed lock.
- [Follower API key](ops/follower-api-key.md),
  [peer keys](ops/peer-keys.md),
  [island subscription check](ops/island-subscription-check.md),
  [pricing / energy / exchange](ops/pricing-energy-exchange.md).

## Security

- [Security overview](security/SECURITY.md),
  [bridge custodian model](security/bridge-custodian.md),
  [key escrow threshold](security/KEY-ESCROW-THRESHOLD.md),
  [remediation plan](security/remediation-plan.md) and its
  [testing procedures](security/testing-procedures.md).
- Audits: [security audit summary](security/security_audit_summary.md),
  [CLI audit findings](security/aitbc-audit-4-cli-findings.md),
  [audit framework](security/4_security-audit-framework.md),
  [chaos testing](security/3_chaos-testing.md),
  [fixes summary](security/SECURITY_FIXES_SUMMARY.md).

## Reference

[Index](reference/0_index.md) —
[all routes](reference/all-routes.md),
[packages](reference/packages.md),
[repository structure](reference/REPOSITORY_STRUCTURE.md),
[plugin spec](reference/PLUGIN_SPEC.md),
[backend](reference/backend.md),
[enterprise](reference/enterprise.md).
Also: [glossary](GLOSSARY.md), [quick reference](QUICK_REFERENCE.md),
[fleet roles](fleet-roles.md), [features](FEATURES.md),
[changelog](CHANGELOG.md), [type checking](TYPE_CHECKING.md),
[support](support.md).

## Development

[Index](development/0_index.md) —
[project guidelines](development/PROJECT_GUIDELINES.md),
[contributing](development/contributing.md),
[API reference](development/api_reference.md),
[validation patterns](development/validation-patterns.md),
[coordinator-api exports](development/coordinator-api-exports.md),
[CLI packaging plan](development/CLI_PACKAGING_PLAN.md),
[workspace strategy](development/workspace/WORKSPACE_STRATEGY.md).
GPU work: [refactoring guide](development/gpu/REFACTORING_GUIDE.md),
[benchmarks](development/gpu/benchmarks.md),
[CUDA analysis](development/gpu/cuda_performance_analysis.md),
[research findings](development/gpu/research_findings.md).
Testing: [infrastructure](testing/test-infrastructure.md),
[coverage requirements](testing/TEST_COVERAGE_REQUIREMENTS.md),
[usage guide](testing/USAGE_GUIDE.md),
[staking test plan](testing/staking_test_plan.md).
Docs standards live under [meta](meta/guides.md); UI notes in
[theming](ui/theming.md).

## Services and components

- Agent layer: [coordinator operator guide](agent-coordinator/OPERATOR_GUIDE.md),
  [CLI](agent-coordinator/CLI.md),
  [API](agent-coordinator/API.md),
  [router architecture](agent-coordinator/ROUTER_ARCHITECTURE.md),
  [signed envelopes](agent-coordinator/agent-signed-envelopes.md),
  [SDK new methods](agent-sdk/NEW_METHODS.md).
- Per-app docs: [node observability](apps/blockchain-node/observability.md),
  [exchange integration](apps/exchange/exchange-integration.md),
  [explorer CLI tools](apps/explorer/CLI_TOOLS.md),
  [GPU monetization](apps/market/gpu_monetization_guide.md),
  [wallet daemon](apps/wallet/wallet.md).
- Architecture: [active apps](architecture/active_apps.md),
  [agent-service DI](architecture/agent-service-di-architecture.md).
- Deployment/infra: [SLA monitoring](deployment/sla-monitoring.md),
  [monitoring setup](infrastructure/monitoring-setup.md),
  [app-shell classification](infrastructure/app-shell-classification.md).
- Market: [advanced features](market/advanced-market-features.md),
  [Nemotron cloud inference](market/agent-nemotron-cloud-inference.md).
- Design: [design system](design/DESIGN_SYSTEM.md).
- Governance: [DAO framework](blockchain/governance/openclaw-dao-governance.md),
  [GPU registration](contracts/GPU-REGISTRATION.md).

## Component READMEs

Library and tooling READMEs that sit beside their code:

- Core package `aitbc/`:
  [agent_bridge](../aitbc/agent_bridge/README.md) /
  [src](../aitbc/agent_bridge/src/README.md),
  [async_helpers](../aitbc/async_helpers/README.md),
  [blockchain](../aitbc/blockchain/README.md),
  [config](../aitbc/config/README.md),
  [crypto](../aitbc/crypto/README.md),
  [data_layer](../aitbc/data_layer/README.md),
  [database](../aitbc/database/README.md),
  [fusion](../aitbc/fusion/README.md),
  [log_utils](../aitbc/log_utils/README.md),
  [middleware](../aitbc/middleware/README.md),
  [network](../aitbc/network/README.md),
  [oracles](../aitbc/oracles/README.md),
  [training_setup](../aitbc/training_setup/README.md),
  [utils](../aitbc/utils/README.md).
- Shared packages: [packages](../packages/README.md),
  [aitbc-shared](../packages/aitbc-shared/README.md),
  [agent-core](../packages/py/aitbc-agent-core/README.md),
  [crypto](../packages/py/aitbc-crypto/README.md),
  [errors](../packages/py/aitbc-errors/README.md).
- Tooling: [scripts](../scripts/README.md),
  [workflow](../scripts/workflow/README.md),
  [workflow-agent](../scripts/workflow-agent/README.md),
  [mcp-server](../mcp-server/README.md),
  [tests](../tests/README.md) and
  [verification](../tests/verification/README.md).
- Other: [contracts/governance](../contracts/governance/README.md),
  [website](../website/README.md) and
  [vendor assets](../website/vendor/README.md),
  [examples/nginx](../examples/nginx/README.md).

## Status

AITBC is under active development. Core blockchain, coordinator, wallet,
market, and CLI services are implemented and run on the public island at
`hub.aitbc.bubuit.net`. For a component-by-component view, see
[releases/STATUS.md](releases/STATUS.md).

## Navigation

- [Master Index](MASTER_INDEX.md) — directory and key file catalog
- [Docs refresh audit](audit/DOCS_REFRESH_AUDIT.md) — closed record of the August 2026 refresh (historical)
- [Service Ports](reference/SERVICE_PORTS.md) — authoritative port reference

---

Orphan check: `scripts/docs/check_orphan_docs.py` fails the commit when a
new `.md` file has no inbound link outside the expected groups.
