# Technical Expansion Plan: AITBC Platform Builder & White-Label SDK

## 1. Executive Expansion Vision and Phase 4 Alignment

The strategic objective for this technical expansion is the immediate
transition of the AITBC ecosystem from its current monolithic marketplace
architecture into a modular "Platform-as-a-Service" (PaaS) model. This shift
is a prerequisite for the Q4 2026 "Developer Ecosystem & DAO Grants" roadmap
milestone.

The architecture mandates the "Platform Builder" as the primary vehicle for
achieving Phase 4 success. We are moving beyond internal-only deployment tools
to provide a public-facing developer suite that empowers third-party
integrators to deploy specialized, brand-aligned instances of the AITBC
infrastructure. This expansion ensures that the network scales through a
"Swarm Intelligence" model, where decentralized entry points drive compute
discovery rather than a centralized portal.

## 2. Modular White-Label Architecture for Agent Frameworks

To facilitate rapid, brand-specific ecosystem deployment, the architecture
must support full white-labeling of the OpenClaw (agent logic) and Hermes
frameworks. For clarity, Hermes is defined as the orchestration layer for
multi-agent workflows, managing the handoff between specialized agents.

The following abstraction layers are required to move from the current
hardcoded state to a configuration-driven expansion:

### Abstraction Layers for White-Labeling

| Component | Current State | Expansion State (Engineering Mandate) |
|---|---|---|
| UI Theme | Hardcoded CSS in `/website` | Configuration-driven CSS variables (Tailwind/SCSS) and remote asset injection |
| API Endpoints | Static `.env` variables | Dynamic registry via `.yaml` or `.json` manifest; supports multi-tenant gateway routing |
| Smart Contract Logic | Standardized AITBC logic | Modular logic hooks for custom settlement rules and brand-specific "Performance Bonds" |
| Branding Metadata | Embedded in source code | Metadata-driven (Logos, titles, SEO/OpenGraph) stored in decentralized storage |
| Framework Orchestration | Rigid OpenClaw execution | Dynamic Hermes workflow injection via JSON manifests |

All branding assets, metadata, and visual variables must be managed via `.yaml`
configuration files, requiring zero code changes for basic visual re-skinning or
marketplace redirection.

## 3. Maturation of `aitbc-core` for Headless Operations

The current repository structure shows a tight coupling between the website and
`coordinator-api` components. The engineering mandate requires a significant
refactoring of `packages/aitbc-core` to function as a truly headless logic
provider.

### Extraction and Isolation

Logic must be migrated out of the `apps/website` and `apps/coordinator-api`
packages and consolidated into `packages/aitbc-core`. This eliminates the
UI-dependency of the core engine. The following modules must be isolated:

- **Autonomous Agent Wallet Management:** Logic for OpenClaw agent smart
  contract wallets, enabling independent GPU power negotiation.
- **Dynamic Pricing Engine Integration:** Full extraction of the 7 existing
  pricing strategies (Market Analysis, Forecasting, etc.) into a standalone
  library.
- **Zero-Knowledge (ZK) Performance Verification:** Decoupled protocols for
  off-chain performance verification and on-chain dispute resolution.
- **GPU Marketplace Discovery Logic:** Standardized discovery algorithms for
  agents to locate computational resources across multi-region edge nodes.

### API Contract Requirements

These modules must utilize JSON-RPC 2.0 for agent-to-agent and agent-to-core
communication. JSON-RPC is preferred over REST to support the high-speed,
stateful WebSocket streams required for the "Multi-Modal Fusion" features,
ensuring the core remains UI-agnostic while maintaining the performance
required for <100ms response times.

## 4. Platform Builder SDK: Custom Dashboard Framework

The Platform Builder SDK is the developer-facing toolkit for building custom
dashboards and consumer interfaces on the AITBC network.

### SDK Features

- **React/Vue Component Library:** Pre-built themeable hooks for querying the
  AITBC blockchain explorer and marketplace data directly from the
  decentralized ledger.
- **WebSocket Stream Handlers:** Standardized methods for multi-modal agent
  communication, supporting text, image, audio, and video formats as defined in
  the Multi-Modal Fusion specification.
- **Resource Monitoring Hooks:** Integrated logic for real-time GPU priority
  queuing, preemption status, and global edge node health monitoring.

### Internal Package Hierarchy

1. `@aitbc/sdk-core`: Primary blockchain communication and cryptographic
   identity logic.
2. `@aitbc/sdk-ui-hooks`: Framework-specific state management for React and
   Vue.
3. `@aitbc/sdk-streaming`: WebSocket management for multi-modal (text/audio/video)
   agent interactions.
4. `@aitbc/sdk-verifiers`: Client-side ZK-proof verification and Optimistic
   Rollup challenge generation.

## 5. Plugin Architecture for Brand-Specific Agent Behaviors

A "Plugin Manifest" system is required to allow developers to inject
brand-specific logic into OpenClaw agents without altering the core AITBC
engine. This maintains the integrity of the base protocol while allowing
vertical specialization.

### Lifecycle Hooks and Verifiability

Plugins must hook into the following agent lifecycle events:

- `onResourceDiscovery`: Filters GPU providers based on region or compliance
  (e.g., HIPAA-certified nodes).
- `onNegotiationStart`: Brand-specific pricing adjustments or unique contract
  terms.
- `onProofGeneration`: Allows brand-specific agents to inject custom metadata
  into their Zero-Knowledge performance proofs, ensuring custom logic remains
  verifiable on-chain.
- `onVerificationSuccess`: Triggers post-computation logic, such as regulatory
  logging or settlement.

Custom behaviors for healthcare (HIPAA), finance (regulatory checks), or
manufacturing are to be loaded dynamically. These plugins operate within the
existing Optimistic Rollups framework, ensuring that even brand-specific logic
can be challenged during the dispute resolution window.

## 6. CLI Configuration and Developer Tooling

The expansion of the `aitbc-cli` (found in the `/cli` directory) must provide
a seamless scaffolding and deployment experience.

### Technical Specification for CLI Commands

```bash
# Initialize a new white-label platform instance using standardized boilerplate
aitbc init-platform --name "HealthAI" --template "compliance-heavy"

# Generate boilerplate for brand-specific logic plugins with ZK-hook support
aitbc plugin create --type "compliance" --name "hipaa-logger"

# Sync configuration and assets to decentralized storage (IPFS/Arweave)
# and register the brand instance with AITBC DAO Governance contracts
aitbc deploy-brand --config ./config/brand.yaml --network mainnet --storage ipfs
```

Engineering must ensure the local development environment utilizes the
existing `dev` and `scripts` directories to simulate the AITBC blockchain,
enabling developers to test ZK-proof generation for custom plugins locally.

## 7. Engineering Goals and Success Criteria (Phase 4 Transition)

Success for the Phase 4 transition is defined by the following "Readiness
Checklist":

- [ ] **Core Decoupling:** Complete migration of logic from `apps/website` to
      `packages/aitbc-core`.
- [ ] **SDK Documentation:** 100% API endpoint coverage with functional code
      examples for text, audio, and video streaming.
- [ ] **Onboarding Efficiency:** Target deployment time for a new white-label
      platform (scaffolding to IPFS sync) of < 4 hours.
- [ ] **Plugin Interoperability:** Support for multi-party contracts where
      custom plugins from different providers can interact within a single
      workflow.
- [ ] **ZK-Verification Integrity:** 100% success rate for `onProofGeneration`
      hooks in verifying custom plugin metadata.

The move toward a modular architecture is the catalyst for "Swarm
Intelligence" within our ecosystem. By enabling self-improving, specialized
marketplaces, the AITBC platform evolves from a single tool into a global,
decentralized infrastructure for the AI agent revolution.
