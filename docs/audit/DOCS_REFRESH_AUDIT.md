# AITBC Documentation Refresh Audit

**Last Updated:** 2026-08-13
**Version:** 1.0
**Baseline:** `main` at the current checkout

## Scope

This audit covers the high-traffic `docs/` entry points that new visitors and node operators hit first, plus a lightweight scan of the full tree. It is the first deliverable of the docs-refresh megaplan.

## Method

1. `bash scripts/validate_docs.sh` — 3,091 internal `.md` links checked, all valid.
2. Targeted `grep` for stale markers across `docs/`:
   - `designed` / `not implemented` / `placeholder`
   - references to deleted `feature_flags.json`
   - old app/service names (`marketplace-service`, `gpu-service`, `trading-service`, `plugin-service`)
   - non-existent CLI commands (`aitbc <service> start`)
   - missing example files (`examples/gpu_inference_*.py`)
   - suspect port numbers (8000, 8001, 8003, 8006, 8015, 9001, 8103)
   - `vscode-remote://` links
3. Compared `apps/*/` and `cli/aitbc_cli/commands/` against `docs/apps/`.

## Findings summary

| Area | Issue | Severity | Count (approx) |
|------|-------|----------|----------------|
| `docs/apps/README.md` | Catalog uses old app names (`marketplace-service`, `gpu-service`, `trading-service`), non-existent CLI commands, and wrong ports. Many current `apps/*` are missing. | High | 17 flagged lines |
| `docs/getting-started/overview/introduction.md` | Describes aspirational AI trading/surveillance/analytics as current capabilities and lists old port numbers (8015, 3000). | High | 5 sections |
| `docs/README.md` | Claims "100% complete" / "production ready" and lists outdated port numbers. No hub/shop/client path. | High | 3 sections |
| `docs/getting-started/README.md` | User journeys use old terminology and do not surface the hub/shop/client roles from the new README. | Medium | 5 paths |
| `docs/apps/clients/` | Duplicates or overlaps with `docs/getting-started/` and the new Client role. | Medium | 6 files |
| `docs/reference/SERVICE_PORTS.md` | Authoritative, but other docs frequently duplicate or contradict its numbers. | Low | many |
| `docs/agent-coordinator/CLI.md`, `docs/QUICK_REFERENCE.md`, etc. | Contain stale ports and commands. | Medium | 20+ files |

## Current `apps/*` vs. `docs/apps/`

Current `apps/` with `README.md` (22 entries):

`agent-coordinator`, `ai-engine`, `api-gateway`, `blockchain-event-bridge`, `blockchain-explorer`, `blockchain-node`, `bridge-monitor`, `coordinator-api`, `edge`, `exchange`, `ffmpeg`, `governance`, `gpu`, `marketplace`, `miner`, `pool-hub`, `shared-core`, `shared-domain`, `trading`, `wallet`, `whisper`, `zk-circuits`.

`docs/apps/` directories (17):

`agents`, `blockchain`, `clients`, `compliance`, `coordinator`, `crypto`, `exchange`, `explorer`, `global-ai`, `infrastructure`, `marketplace`, `openclaw`, `wallet`.

Gaps: no docs for `agent-coordinator`, `ai-engine`, `api-gateway`, `blockchain-event-bridge`, `blockchain-explorer`, `bridge-monitor`, `edge`, `ffmpeg`, `governance`, `gpu`, `miner`, `pool-hub`, `shared-core`, `shared-domain`, `trading`, `whisper`, `zk-circuits`.

Extras (may be concept/area docs, not 1:1 app docs): `agents`, `clients`, `compliance`, `crypto`, `global-ai`, `infrastructure`, `openclaw`.

## CLI command accuracy

`docs/apps/README.md` and `docs/getting-started/overview/introduction.md` contain CLI commands like:

- `aitbc blockchain-node start`
- `aitbc coordinator-api start`
- `aitbc agent-coordinator start`
- `aitbc exchange start`
- `aitbc marketplace-service start`
- `aitbc gpu-service start`
- `aitbc trading-service start`
- `aitbc ai-engine start`
- `aitbc global-ai init`

None of these top-level command groups exist in `cli/aitbc_cli/commands/`. The CLI has `system`, `node`, `market`, `marketplace`, `ai`, `agent`, `mining`, `wallet`, `exchange`, `gpu`, etc. Service startup is done via `systemctl`, not the `aitbc` CLI.

## Port drift

Authoritative ports are in `docs/reference/SERVICE_PORTS.md`. Docs frequently repeat ports that are legacy or wrong:

- `8000` (coordinator quick start in `docs/apps/README.md`)
- `8001` (old exchange API, now 8106)
- `8003` (old wallet, now 8108)
- `8015` (old wallet, now 8108)
- `9000` / `9001` (old agent-coordinator / infra)
- `3000` (explorer, now 8100)
- `8080` (explorer UI, not a service port)

## Recommended action list

1. **High-traffic landing pages** (this slice):
   - Rewrite `docs/README.md` to remove "100% complete" claims, add hub/shop/client paths, and link to `STATUS.md`.
   - Rewrite `docs/getting-started/README.md` around hub/shop/client roles.
   - Update `docs/getting-started/overview/introduction.md` to describe current AITBC, mark aspirational features, and use authoritative ports.
   - Rewrite `docs/apps/README.md` as a catalog of current `apps/*` using real service names, `systemctl` commands, and links to `docs/reference/SERVICE_PORTS.md`.

2. **Next slices**:
   - Enforce port single-source-of-truth by replacing inline port lists with links to `docs/reference/SERVICE_PORTS.md`.
   - Continue refreshing other stale current docs surfaced by the inventory (e.g., `docs/testing/MICROSERVICES_TESTING_GUIDE.md`, `docs/infrastructure/migration/microservices-migration-status.md`, `docs/agents/AGENT_COMMUNICATION.md`, `docs/cli/CLI_ARCHITECTURE.md`).
   - Remove remaining root boilerplate artifacts from `.gitignore` / CI references if needed.

3. **Continuous validation**:
   - Re-run `bash scripts/validate_docs.sh` after every slice.
   - Run `npx markdownlint-cli docs/` on touched directories.
   - Keep this audit updated as remediation completes.

## Current baseline (post-boilerplate removal, 2026-08-13)

- Internal `.md` links: 2,839 valid.
- Markdown lint errors in `docs/`: 15,096.
- Stale markers in current `docs/` (excluding `docs/releases/`, `docs/archive/`, `docs/audit/`): 133 files, 513 hits.
- Top directories by stale markers: `docs/development` (59), `docs/agent-coordinator` (50), `docs/testing` (46), `docs/security` (42), `docs/reference` (32), `docs/agents` (30), `docs/infrastructure` (30), `docs/infrastructure/migration` (24), `docs/cli` (21).
- Top files by stale markers:
  - `docs/development/mock-data-system.md` (67 designed/placeholder terms)
  - `docs/testing/MICROSERVICES_TESTING_GUIDE.md` (28 old app names)
  - `docs/infrastructure/migration/microservices-migration-status.md` (24)
  - `docs/cli/CLI_ARCHITECTURE.md` (15)
  - `docs/agents/AGENT_COMMUNICATION.md` (12)

## Remediation status

| File | Action | Status |
|------|--------|--------|
| `docs/README.md` | rewrite landing | done |
| `docs/getting-started/README.md` | rewrite role-based paths | done |
| `docs/getting-started/overview/introduction.md` | update to current code | done |
| `docs/apps/README.md` | rewrite app catalog | done |
| `docs/MASTER_INDEX.md` | update counts | done |
| `docs/apps/clients/` | archived to `docs/archive/apps-clients/` | done |
| `docs/QUICK_REFERENCE.md` | rewrite to current CLI and ports | done |
| `docs/agent-coordinator/CLI.md` | rewrite to current `aitbc` CLI and port 8107 | done |
| `docs/development/1_overview.md` | rewrite to current stack and mark designed features | done |
| `docs/apps/<missing>/README.md` | created 19 app landing pages | done |
| `docs/apps/README.md` | regenerated catalog to use new app docs | done |
| Boilerplate docs and root files | deleted from repo | done |
| `docs/README.md` / `MASTER_INDEX.md` | rewritten post-cleanup | done |
| `CONTRIBUTING.md` | created project-specific root guide | done |
| Dead CONTRIBUTING.md / SDK links | fixed across README and docs | done |
| Port single-source-of-truth cleanup | replace inline old ports with links | pending |
| Remaining stale current docs | e.g. agents, cli, testing, infrastructure | pending |
