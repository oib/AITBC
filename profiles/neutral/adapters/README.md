# Neutral adapters

Provider-agnostic capability interfaces. A [profile](../../README.md) binds each to a concrete
provider; agents target the capability, never a specific tool.

| Capability | Interface | `saw-stack` provider |
|------------|-----------|----------------------|
| Task tracking | [`task-tracking.md`](task-tracking.md) | Linear |
| Docs | [`docs.md`](docs.md) | Confluence |
| Git | [`git.md`](git.md) | GitHub |
| Database | [`database.md`](database.md) | Supabase/Postgres + RLS |
| Deploy | [`deploy.md`](deploy.md) | Docker + GitHub Actions |
| Notifications | [`notifications.md`](notifications.md) | Linear (via tracker) |
| Design system | [`design-system.md`](design-system.md) | none |
| Knowledge | [`knowledge.md`](knowledge.md) | okf-repo (in-repo bundle) |
| Secrets | [`secrets.md`](secrets.md) | env |
| Evolution | [`evolution.md`](evolution.md) | none |

> Some interface files originated in the clean-room blueprint and reference the earlier
> `.agentic/…` layout. They remain valid as capability contracts; the live execution layer is
> SAW, mapped in [`INTEGRATION.md`](../../../INTEGRATION.md). Path-reference cleanup is tracked
> follow-on work.
