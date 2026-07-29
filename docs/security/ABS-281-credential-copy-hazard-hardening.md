# Backend Credential Copy-Hazard Hardening (ABS-281)

**Shipped**: 2026-07-14 · PR #210 · commits `df16daa`, `04936d9`

Closes the defect class where a single documented setup step (`cp .env.example .env`) was enough
to manufacture a full dev environment with a well-known org-wide admin token. ABS-262 removed the
compose-level default; ABS-281 removes it from the file operators are explicitly told to copy.

---

## What the invariant says

> No repo file hands an operator a dev environment or a dev credential.

A verbatim copy of `backend/.env.example` now enables nothing and carries no credential. The
`docker compose up` stack supplies no fallback default for any gated variable. A copied file with
the dev block still commented out refuses to boot rather than silently seeding the well-known admin
token.

---

## Local dev setup

**One step before, one edit now** — the friction is deliberate and small.

```bash
# 1. Copy the template (unchanged from before).
cp backend/.env.example backend/.env

# 2. NEW: uncomment the LOCAL DEV ONLY block in .env.
#    That single edit declares the dev environment.
#    Before ABS-281 this edit was not needed; the copy itself did it.
```

After uncommenting the block, `docker compose up` boots normally:

- `/healthz` returns `{"status":"ok"}`
- The org-wide admin token is seeded with the `DEV_BOOTSTRAP_TOKEN` convenience value
  (`dev-bootstrap-token-change-me`), supplied by `loadConfig` in dev

The block in `.env.example` looks like this:

```
# ---------------------------------------------------------------------------------------
# LOCAL DEV ONLY -- uncomment this whole block to enable local development.
#
#NODE_ENV=development
#POSTGRES_PASSWORD=postgres
#DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic
```

**Non-dev setup** (staging, production, shared host): leave the block commented, set
`BACKEND_BOOTSTRAP_TOKEN` to a strong random token (`openssl rand -hex 32`) and
`POSTGRES_PASSWORD` to a password you choose. `NODE_ENV` stays unset (fail closed).

---

## Why `docker-compose.yml` is a local-dev artifact

The file carries this header:

```
# LOCAL-DEV ARTIFACT -- NOT A DEPLOYMENT ARTIFACT.
```

It publishes Postgres on port 5432 and the server on 8420 directly onto the host. It is not a
deployment template. Every gated variable passes through empty when the operator sets nothing:

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-}
NODE_ENV:          ${NODE_ENV:-}
BACKEND_BOOTSTRAP_TOKEN: ${BACKEND_BOOTSTRAP_TOKEN:-}
```

An empty pass-through means the stack refuses to boot without input, not that it manufactures
a dev environment. This is the same principle ABS-262 applied to the bootstrap token; ABS-281
extends it to the DB credential.

---

## The dev-hazards guard

`backend/packages/core/test/dev-hazards.test.ts` enforces the invariant mechanically. It replaces
`compose-env.test.ts`, which was one regex on one file — blind to a literal `NODE_ENV: development`
in compose and unable to open `.env.example` at all.

### What the guard checks

The guard asserts that no repo file in `backend/` hands out any of these forms:

- **compose** `${NODE_ENV:-development}` or any `${VAR:-non-empty}` default for
  `NODE_ENV`, `BACKEND_BOOTSTRAP_TOKEN`, or `POSTGRES_PASSWORD`
- **compose** a literal `NODE_ENV: development` assignment (map or list syntax)
- **compose** a literal value for `BACKEND_BOOTSTRAP_TOKEN` or `POSTGRES_PASSWORD`
- **compose** a `DATABASE_URL` with a password baked in rather than interpolated
- **`.env*example`** any active (uncommented) `NODE_ENV=development`
- **`.env*example`** any active `BACKEND_BOOTSTRAP_TOKEN` or `POSTGRES_PASSWORD` assignment
- **`.env*example`** a `DATABASE_URL` with a password baked in

### How it avoids the three ways such guards die

1. **File discovery, not hardcoded names.** The guard calls `readdirSync` on `backend/` and
   collects every `docker-compose*.yml` and `.env*example` it finds. A new compose override or a
   second `.env` template is covered the day someone adds it. Adding a file and forgetting to
   update a list of names is not possible.

2. **Non-vacuity assertions.** If the discovery yields nothing (e.g., someone renames
   `docker-compose.yml`), the guard fails — it does not turn into a no-op green suite.

3. **Mutation proof in-suite.** `MUTANTS` in the test file lists every hazard form. Each one is
   reintroduced into the real file during the test run, the guard is confirmed to catch it, and
   the file is restored. A guard that quietly stops catching a form fails on every run, not only
   when the architect notices.

### Extending the guard

To add a new gated variable:

1. Add it to the `GATED` tuple near the top of `dev-hazards.test.ts`.
2. Add its active-assignment check to `dotenvHazards` (credential keys) or the form-B check in
   `composeHazards` (literal compose values) as appropriate.
3. Add a mutation entry to `MUTANTS` covering the `.env.example` active form and the compose
   default form.

The guard imports `isDevEnv` from `config.ts` rather than keeping its own copy of the dev-marker
list, so a change to what counts as a dev environment propagates automatically.

---

## AC1 / AC-8 ordering note (adjudicated, do not re-open)

AC1 requires a verbatim copy to refuse "with the ABS-262 error naming `BACKEND_BOOTSTRAP_TOKEN`".
AC-8 requires no active DB credential after a verbatim copy. Both hold — but the database gate
fires first: `POSTGRES_PASSWORD` is empty, Postgres refuses to initialise, and
`depends_on: service_healthy` means the backend process never starts to print the token error.

The system architect adjudicated this: the ordering is not a security property. The property
AC1 protects ("a verbatim copy must not yield a running dev environment with a seeded admin
token") holds in full — nothing boots, nothing migrates, nothing seeds. The token gate is live
and unmasked on the copy path: give the copied `.env` a DB password (what a non-dev operator
does next) and `loadConfig` refuses immediately with the ABS-262 error. Resolved at Stage 1
architecture review; the security engineer concurred. Do not bounce future reviews for this.

---

## Related

- `backend/packages/core/src/config.ts` — `loadConfig`, `DEV_BOOTSTRAP_TOKEN`, `isDevEnv`
- `backend/.env.example` — the LOCAL DEV ONLY block
- `backend/docker-compose.yml` — the local-dev artifact header
- [ABS-262](../../specs/) — the preceding hardening that closed the compose-level default
- [docs/security/SECURITY_FIRST_ARCHITECTURE.md](SECURITY_FIRST_ARCHITECTURE.md) — broader
  security architecture
