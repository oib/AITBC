# Documentation Changelog

**Last Updated**: 2026-06-30
**Version**: 1.0

This changelog tracks all structural and content changes to the AITBC documentation.

## 2026-06-30 - Documentation Restructuring

### Release Notes Splitting

**v0.6.4 Release Notes**
- Split `docs/releases/v0.6.4/AGENTS.md` into topic-focused files:
  - `overview.md` - Release overview, status baseline, architecture
  - `agent-a.md` - Shared core implementation (PortAllocator, ChainConfigParser)
  - `agent-b.md` - Apps & infrastructure implementation
- Updated original `AGENTS.md` to serve as navigation index
- Added version metadata (1.0) and last-updated dates (2026-06-30) to all files
- Added standardized footer with documentation version, last updated date, release name, and agent assignment

**v0.6.3 Release Notes**
- Split `docs/releases/v0.6.3/AGENTS.md` into topic-focused files:
  - `overview.md` - Release overview, status baseline, architecture
  - `agent-a.md` - Shared core implementation (SyncSourceResolver, IslandRegistry, SubscriptionManager)
  - `agent-b.md` - Apps & infrastructure implementation
- Updated original `AGENTS.md` to serve as navigation index
- Added version metadata (1.0) and last-updated dates (2026-06-30) to all files
- Added standardized footer with documentation version, last updated date, release name, and agent assignment

**v0.5.10 Migration Runbook**
- Split `docs/releases/v0.5.10/migrate-hub.md` into topic-focused files:
  - `overview.md` - Migration overview
  - `pre-flight-checks.md` - Pre-migration verification (P1-P7)
  - `migration-steps.md` - Step-by-step hub migration procedure (Step 1-11)
  - `follower-instructions.md` - Follower node procedures
  - `troubleshooting.md` - Common issues and solutions
  - `rollback.md` - Rollback procedures
- Updated original `migrate-hub.md` to serve as navigation index
- Added version metadata (1.0) and last-updated dates (2026-06-30) to all files
- Added standardized footer with documentation version, last updated date, and release name

### Documentation Standardization

**Footer Format**
- Standardized footer format across all split release notes files
- Footer includes:
  - Documentation Version
  - Last Updated date
  - Release name
  - Agent assignment (for agent-specific files)

**Quick-Start Summaries**
- Added quick-start summaries to all app categories in `docs/apps/README.md`:
  - Blockchain - Deploy node, configure settings, monitor via RPC
  - Coordinator - Start API, submit jobs, monitor dashboard
  - Agent Coordinator - Launch, register agents, view swarm status
  - Agents - Initialize agent, configure identity, start
  - AI Engine - Start engine, load models, submit inference jobs
  - Agent Protocols - Import schemas, implement handlers, register
  - Agent Registry - Query registry, register agents, discover services
  - Exchange - Start exchange, configure pairs, access API
  - Trading Service - Launch, submit orders, monitor trades
  - Marketplace - Access UI, browse resources, submit requests
  - Marketplace Service - Start, list resources, submit bids
  - GPU Service - Launch, register resources, monitor jobs
  - Wallet - Initialize, import/generate keys, manage addresses
  - Infrastructure - Deploy, configure monitoring, access dashboard
  - Monitoring Service - Start, configure alerts, view metrics
  - Crypto - Initialize, configure circuits, generate proofs
  - Compliance - Start, configure rules, check status
  - Governance Service - Launch, submit proposals, vote
  - Mining - Start, configure parameters, monitor status
  - Global AI - Initialize, configure endpoints, discover agents
  - Global AI Agents - Start, register agents, coordinate tasks
  - Explorer - Start, access UI, search blocks/transactions
  - Clients - Install SDK, configure credentials, submit jobs

### Navigation Improvements

**Quick Navigation Sections**
- Added quick navigation sections to all split release notes files
- Navigation includes links to major headings within each document
- Enables rapid access to specific sections without scrolling

**Cross-References**
- Added "Related Topics" sections to all split files
- Links between overview, agent-specific, and procedure documents
- Maintains context across split documentation

## Previous Documentation Changes

### 2026-04-27 - Apps Documentation Hub
- Created comprehensive apps documentation index
- Consolidated 23 app documentation entries
- Added quick links and quality metrics
- Established template compliance standards

### 2026-04-XX - Documentation Template Standardization
- Established documentation template standards
- Added navigation breadcrumbs
- Implemented quality metrics tracking
- Created audit checklist for documentation compliance

## Future Planned Changes

### Pending Tasks
- Add code examples to agent-sdk API reference
- Add request/response examples for each endpoint
- Create Quick Reference section for common commands
- Audit and consolidate large release notes AGENTS.md files
- Create Release Notes Summary for users

---

**Documentation Standards Version**: 1.0
**Last Updated**: 2026-06-30
**Maintained By**: Documentation Team
