# packages/

Shared packages consumed by the apps and services in this monorepo. There are two
ecosystems here, managed separately:

## Python packages

| Path | Package | Purpose |
|---|---|---|
| `aitbc-shared/` | `aitbc-shared` | Shared ORM models and utilities (installed editable via root `requirements.txt`) |
| `aitbc-core/` | `aitbc-core` | Core domain helpers |
| `py/` | — | Namespace directory holding the smaller Python packages below |

`py/` contains:

- `aitbc-agent-core` — agent framework core
- `aitbc-agent-sdk` — agent SDK
- `aitbc-crypto` — crypto helpers
- `aitbc-errors` — shared error types
- `aitbc-sdk` — public SDK surface

## TypeScript packages (pnpm workspace)

`pnpm-workspace.yaml` declares the JS workspace; **pnpm only** — `web` depends on
`theme-provider` via `"workspace:*"`, which npm cannot resolve.

| Path | Package | Purpose |
|---|---|---|
| `theme-provider/` | `@aitbc/theme-provider` | Shared theming |
| `web/` | `@aitbc/web` | Web-facing shared code |

> Note: `contracts/` uses **npm**, not pnpm — the two package trees deliberately use
> different package managers, and CI matches each (`package-tests.yml` → pnpm,
> `smart-contract-tests.yml` → `npm ci`).
