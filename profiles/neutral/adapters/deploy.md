# Deploy Adapter — Interface

Build and deployment pipelines. **Agents prepare deployments; humans release to production.**
This mirrors SAW's RTE boundary and the neutral core's `production-deployment` approval gate.

## Operations

| Operation | Semantics |
|-----------|-----------|
| `build(ref)` | Produce a deployable artifact; surface build-gate results. |
| `deploy(env, artifact)` | Deploy to a non-production environment (dev/staging). |
| `prepare_production(artifact)` | Assemble everything a human needs to release: checklist, artifact, rollback plan. **Does not deploy to prod.** |
| `rollback(env)` | Roll back a non-production deployment. |
| `status(env)` / `logs(env)` | Observe a deployment. |

## Providers

- **`docker-github-actions`** (saw-stack) — backed by SAW's `deployment-sop` /
  `release-patterns` skills, the `deploy-dev` / `remote-deploy` / `remote-rollback` / `release`
  commands, and the [CI/CD Pipeline Guide](../../../docs/ci-cd/CI-CD-Pipeline-Guide.md).
- **`vercel`, `fly`, `none`** — pluggable / disabled.

## Invariant

No provider exposes an autonomous production release to agents. `prepare_production` is the
furthest an agent goes; a human executes the release (see
[`blueprint/governance/approval-boundaries.md`](../../../blueprint/governance/approval-boundaries.md)).
