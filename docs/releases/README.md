# Release Notes

**Level**: All Levels
**Prerequisites**: None
**Estimated Time**: 5-15 minutes
**Last Updated**: August 27, 2026
**Version**: 2.5

## 🧭 **Navigation Path:**

**🏠 [Documentation Home](../README.md)** → **📋 Releases** → *You are here*

**breadcrumb**: Home → Releases → Overview

---

## 🎯 **See Also:**

- **🏠 [Documentation Home](../README.md)** - Main docs entry point
- **📚 [Master Index](../MASTER_INDEX.md)** - Full documentation catalog
- **📖 About Documentation** - Standards and compliance context
- **✅ [Completed Projects](2026/README.md)** - Completion tracking and summaries

---

## 🧾 **One version number, one source of truth**

The package version and the release train are the same number — currently
`0.25.9`. `aitbc/_version.py` is the single source of truth (`pip`, `make
version-check`, and `aitbc --version` all report it), and
`scripts/ci/check-version-consistency.py` enforces that every other reference
matches it:

- `pyproject.toml` — `version = "…"` (every occurrence must equal the canonical value)
- `cli/aitbc_cli/__init__.py` — the CLI package's literal `__version__`
- `cli/setup.py` — imports `__version__` from `aitbc_cli` (a matching literal is also accepted)
- `README.md` — the `version-…` badge (a `v` prefix is tolerated)

Bumping a release means setting the new value in `aitbc/_version.py` and
updating the checked references above; the checker fails on any it finds
stale, and `cli/tests/test_version.py` holds the same rules. Release
directories under `docs/releases/` follow the same number — `v0.25/` holds
the `v0.25.x` logs.

## 📦 **Release History**

Read the release notes newest-first:

### Current Releases (v0.5.x+)

- **[v0.29.0](2026/README.md#v0290)** - Post-v0.28 window (staging draft): consensus domain separation (#1298), state transitions v21–v24 (#1314), mempool reservations (#1300), agent-spend policy, contract + app audit-bug waves (#1380–#1512)
- **[v0.28.0](2026/README.md#v0280)** - Post-reset tasks: island gauges, CLI error/exit sweeps, failover + backup runbooks, PG-capable services, fork guards (staged, tag pending)
- **[v0.27.0](2026/README.md#v0270)** - RAM optimization wave: systemd memory caps, coordinator startup footprint, journal-errors streaming, watchdog/OOM visibility (staged, tag pending)
- **[v0.26.0](2026/README.md#v0260)** - Post-reset window: RPC `chain_id` 400s, governance sealed-proposal reader, reset-window gate tooling (staged, tag pending)
- **[v0.25.13](2026/README.md#v02513)** - MCP routing/groups hardening, post-tag follow-ups (staged, tag pending)
- **[v0.25.12](2026/README.md#v02512)** - Post-v0.25.11 consolidation: chain-stall alert, MCP groups, CLI exit codes, failover/backup drills, escrow relays ✅ tagged 2026-10-21
- **[v0.25.11](2026/README.md#v02511)** - On-chain messaging, bridge ledger/ops hardening, KR-2…KR-6 key rotations, v13/v14 shared activation ✅
- **[v0.25.10](2026/README.md#v02510)** - Escrow settlement passes, energy-rate guard, v11/v12 consensus pins, governance parameter tooling ✅
- **[v0.25.9](2026/README.md#v0259)** - Bridge payout monitor, governance service-local reclassification, v9 shadow window ✅
- **[v0.25.8](2026/README.md#v0258)** - Post-v0.25.2-tag consolidation: coordinator hardening, faucet budgets, consensus freshness & fork choice, fleet ops ✅
- **[v0.25.7](2026/README.md#v0257)** - First-class IPFS marketplace support ✅
- **[v0.25.6](2026/README.md#v0256)** - Multi-validator consensus hardening, auth & admin client fixes, CLI genesis tooling, and escrow v3 state path ✅
- **[v0.25.5](2026/README.md#v0255)** - Audit reconciliation: register fully closed, fleet hardening, dead-code removal ✅
- **[v0.25.4](2026/README.md#v0254)** - Bridge, escrow/consensus hardening, GPU electricity-cost floor ✅
- **[v0.25.3](2026/README.md#v0253)** - Escrow and settlement hardening ✅
- **[v0.25.2](2026/README.md#v0252)** - CLI, docs, and test surface cleanup ✅
- **[v0.25.1](2026/README.md#v0251)** - Open follow-ups and design notes after v0.25.0 ✅
- **[v0.25.0](2026/README.md#v0250)** - On-chain liquidity, sync consolidation and MCP expansion ✅
- **[v0.24.0](2026/versions/v0.24/v0.24.0_change.log)** - Hub node development special (split into v0.24.1–v0.24.18 by topic)
- **[v0.23.0](2026/versions/v0.23/v0.23.0_change.log)** - Design & Correctness Audit (split into v0.23.1–v0.23.34 by topic)
- **[v0.10.18](2026/README.md#v01018)** - Update Deployment Stabilization (market_metrics migration conflict, wallet keystore restore, update.sh/health_check.sh fixes, poetry switch, schema-drift reconciliation) ✅ complete
- **[v0.10.17](2026/README.md#v01017)** - Security & Auth Hardening (auth bypass, hardcoded defaults, feature flag defaults, pool-hub reward signing, wiring bug) ✅ complete
- **[v0.10.16](2026/README.md#v01016)** - Security & Correctness Hardening (bridge trust boundaries, wallet authentication, financial exactness, migrations, CI/deployment) ✅ complete
- **[v0.10.15](2026/README.md#v01015)** - Monolithic Router/Module Decomposition & Settlement Config Wiring ✅ complete
- **[v0.10.14](2026/README.md#v01014)** - Legacy Code & Stub Elimination (shadow packages, legacy routers, fake implementations, duplicate stacks) ✅ complete
- **[v0.10.13](2026/README.md#v01013)** - Security & Correctness Hardening (credential hygiene, auth boundaries, signature verification, fake payments, file permissions, migration integrity, test coverage) ✅
- **[v0.10.12](2026/README.md#v01012)** - Quality Hardening (mypy completeness, test suite repair, production assert removal, dependency/version cleanup) ✅
- **[v0.10.11](2026/README.md#v01011)** - Bug Fixes & Code Quality Continuation (stub completion, Pydantic v2, SQLAlchemy standardization, concurrency safety) ✅
- **[v0.10.10](2026/README.md#v01010)** - Code Quality & Testing Roadmap (mypy coverage, coverage gate, property-based tests, perf regression, dep pinning, dev script, integration fixtures) ✅
- **[v0.10.9](2026/README.md#v0109)** - Dead Code Elimination & Status Drift Cleanup
- **[v0.9.0](2026/README.md#v090)** - Atomic Cross-Chain Settlement
- **[v0.8.2](2026/README.md#v082)** - Advanced Offer Sync (subscription, real-time, search index)
- **[v0.8.1](2026/README.md#v081)** - Cross-Chain Offer Sync (polling-based)
- **[v0.8.0](2026/README.md#v080)** - Inter-Chain Trading Basics
- **[v0.7.5](2026/README.md#v075)** - Consensus Activation (MultiValidatorPoA + PBFT)
- **[v0.7.4](2026/README.md#v074)** - Deferred v0.7.x Items (External Oracle, Cross-Chain Governance, Parameter Automation, Emergency Proposals, Coordinator-API Bridge)
- **[v0.7.3](2026/README.md#v073)** - Governance
- **[v0.7.2](2026/README.md#v072)** - Bridge Verification (In-Process Crypto)
- **[v0.7.1](2026/README.md#v071)** - Bridge Security
- **[v0.7.0](2026/README.md#v070)** - Bridge Basics
- **[v0.6.7](2026/README.md#v067)** - Pool Hub & Mining
- **[v0.6.6](2026/README.md#v066)** - Compute Marketplace
- **[v0.6.5](2026/README.md#v065)** - Agent Coordination Service ✅
- **[v0.6.4](2026/README.md#v064)** - Multi-Chain Per Island
- **[v0.6.3](2026/README.md#v063)** - Multi-Island Node Support
- **[v0.6.2](2026/README.md#v062)** - Sync & Gossip Optimization
- **[v0.6.1](2026/README.md#v061)** - Parallel Processing ✅
- **[v0.6.0](2026/README.md#v060)** - Database & Network Optimization ✅
- **[v0.5.19](2026/README.md#v0519)** - Tech Debt Cleanup ✅
- **[v0.5.18](2026/README.md#v0518)** - Test Suite Repair ✅
- **[v0.5.17](2026/README.md#v0517)** - Test Infrastructure ✅
- **[v0.5.16](2026/README.md#v0516)** - Security Hardening & Multi-Chain Preparation ✅
- **[v0.5.15](2026/README.md#v0515)** - Flat-to-Context Migration + Test Suite Repair
- **[v0.5.14](2026/README.md#v0514)** - Cross-Context Dependency Elimination
- **[v0.5.13](2026/README.md#v0513)** - Coordinator-API Bounded Context
- **[v0.5.12](2026/README.md#v0512)** - Duplication Elimination & Large-File Decomposition
- **[v0.5.11](2026/README.md#v0511)** - (See change.log for details)
- **[v0.5.10](2026/README.md#v0510)** - (See change.log for details)
- **[v0.5.9](2026/README.md#v059)** - (See change.log for details)
- **[v0.5.8](2026/README.md#v058)** - (See change.log for details)
- **[v0.5.7](2026/README.md#v057)** - (See change.log for details)
- **[v0.5.6](2026/README.md#v056)** - (See change.log for details)
- **[v0.5.5](2026/README.md#v055)** - (See change.log for details)
- **[v0.5.4](2026/README.md#v054)** - (See change.log for details)
- **[v0.5.3](2026/README.md#v053)** - (See change.log for details)
- **[v0.5.2](2026/README.md#v052)** - (See change.log for details)
- **[v0.5.1](2026/README.md#v051)** - (See change.log for details)
- **[v0.5.0](2026/README.md#v050)** - Production Infrastructure
- **[v1.0.0](2026/README.md#v100)** - Production Readiness

### Legacy Releases (v0.4.x and earlier)
>
> **Note**: Legacy release files (v0.0.x through v0.4.x) now live under `2026/versions/`. These releases use the old single-file format and are preserved for historical reference.

- **[View Archived Releases](2026/versions/)** - All v0.0.x through v0.4.x releases (archived 2026-06-30)
- **[v0.4.27](2026/README.md#v0427)** - (See change.log for details)
- **[v0.4.26](2026/README.md#v0426)** - (See change.log for details)
- **[v0.4.25](2026/README.md#v0425)** - (See change.log for details)
- **[v0.4.16](2026/versions/v0.4/v0.4.16_changelog.md)** - (See changelog for details)
- **[v0.4.7](2026/versions/v0.4/v0.4.7_changelog.md)** - May 14, 2026 - **Multi-Model Ollama, Hardware+Software Bundles, GPU Marketplace Deprecated** ✅
- **[v0.4.6](2026/versions/v0.4/v0.4.6_changelog.md)** - April 17, 2026
- **[v0.4.4](2026/versions/v0.4/v0.4.4_changelog.md)** - March 14, 2026

---

## 📊 **Topic Summary**

For a comprehensive topic-based analysis of releases from v0.4.5 through v0.8.0, see the Release Notes Topic Summary. This document organizes releases by major themes:

- **Marketplace & Trading Evolution** - Software marketplace, reputation systems, multi-model Ollama, hardware+software bundles, external blockchain exchange, governance integration
- **Agent Communication & Coordination** - Structured message protocols, cross-node messaging, WebSocket migration, backend implementation
- **Blockchain Infrastructure** - Node service fixes, input validation, adaptive sync, MyPy compliance
- **Security & Performance** - Enterprise-grade security, vulnerability fixes, resource optimization, security hardening
- **Code Quality & Type Safety** - Major refactoring, MyPy type safety graduation, test coverage improvements, linting fixes
- **Architecture & Observability** - Codebase cleanup, architecture refactoring, logging standardization, observability enhancement
- **Cross-Chain & Interoperability** - Bridge contracts, multi-chain wallet, inter-chain trading (planned)

---

## 🧱 **Purpose**

This directory records versioned release notes, migration context, and milestone summaries.

---

## 🚀 **Next Steps**

- Start with the newest release note when checking change history.
- Use release notes to understand migration and operational implications.
- Keep future release notes linked from the master index.

---

*Last updated: November 10, 2026*
*Version: 2.4*
*Status: Release index updated through the v0.29.0 staging draft (v0.25.2–v0.25.13, v0.26.0, v0.27.0, v0.28.0 entries added 2026-11-10)*
