# QA Validation Report — ABS-281

**Ticket**: ABS-281 — Backend hardening: no repo file may hand an operator a dev environment or a dev credential  
**Branch**: `ABS-281-auto`  
**Commits verified**: `df16daa`, `04936d9`, `4f1b66f`, `21fa53c` (HEAD)  
**QAS verdict**: ✅ **APPROVED**  
**Date**: 2026-07-14  

---

## Summary

All nine Acceptance Criteria (AC1–AC9, including the two PO-added binding ACs) are met. The copy-hazard is closed at the file layer, the guard is mutation-proven on 13 forms (6 required), and the compose Postgres default is removed. The AC1/AC-8 ordering issue (DB gate fires before token gate on a verbatim copy) was formally adjudicated by the system architect and concurred with by the security engineer; the security property AC1 protects holds in full.

---

## Independent Verification Steps

### 1. File Content — Direct Inspection

#### `backend/.env.example`

Active (non-comment, non-blank) lines after verbatim `cp .env.example .env`:

```
PORT=8420
```

That is the **only** active line. All dev-enabling lines are inactive:
- `#NODE_ENV=development` (commented)
- `#POSTGRES_PASSWORD=postgres` (commented)
- `#DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic` (commented)
- `BACKEND_BOOTSTRAP_TOKEN` line is **absent entirely** (correct: `loadConfig` supplies `DEV_BOOTSTRAP_TOKEN` in dev)

#### `backend/docker-compose.yml`

All credential and environment-marker pass-throughs use empty defaults (`:-`), no baked-in values:
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-}
DATABASE_URL: postgres://postgres:${POSTGRES_PASSWORD:-}@db:5432/agentic
NODE_ENV: ${NODE_ENV:-}
BACKEND_BOOTSTRAP_TOKEN: ${BACKEND_BOOTSTRAP_TOKEN:-}
```

Header present: `# LOCAL-DEV ARTIFACT -- NOT A DEPLOYMENT ARTIFACT.`

No `:-postgres`, `:-development`, or `:-dev-bootstrap-token-change-me` anywhere in the file.

---

### 2. Test Suite — Independent Run

```
$ pnpm -r test   (without DATABASE_URL)

packages/core: 49 pass, 0 fail, 3 skipped (DB-gated migration tests)
apps/server:    0 pass, 0 fail, 7 skipped (all DB-gated)
Total: 49 pass / 0 fail / 10 skipped
```

**dev-hazards.test.ts — all 18 guard tests PASS:**

| Test | Result |
|------|--------|
| the guard is not vacuous: discovered the files it must guard | ✅ PASS |
| the compose walk is not vacuous: finds the assignments it must judge | ✅ PASS |
| `docker-compose.yml` hands out no dev environment and no dev credential | ✅ PASS |
| `.env.example` hands out no dev environment and no dev credential when copied verbatim | ✅ PASS |
| guard catches: compose interpolates a dev NODE_ENV default | ✅ PASS |
| guard catches: compose assigns a literal dev NODE_ENV | ✅ PASS |
| guard catches: compose defaults POSTGRES_PASSWORD | ✅ PASS |
| guard catches: compose defaults BACKEND_BOOTSTRAP_TOKEN | ✅ PASS |
| guard catches: compose embeds the DB password in DATABASE_URL | ✅ PASS |
| guard catches: compose assigns a dev NODE_ENV in list syntax | ✅ PASS |
| guard catches: compose assigns a dev NODE_ENV in QUOTED list syntax | ✅ PASS |
| guard catches: compose assigns a dev NODE_ENV in flow style | ✅ PASS |
| guard catches: .env example hides an active dev NODE_ENV behind an inline comment | ✅ PASS |
| guard catches: .env example activates NODE_ENV=development | ✅ PASS |
| guard catches: .env example activates the well-known bootstrap token | ✅ PASS |
| guard catches: .env example activates the DB password | ✅ PASS |
| guard catches: .env example activates a DATABASE_URL embedding the DB password | ✅ PASS |
| the guard allows the safe pass-through and inactive forms the fix ships | ✅ PASS |

**DB-gated tests (10 skipped without `DATABASE_URL`):** Run hot by be-developer against a real Postgres instance — 59 pass / 0 fail / 0 skipped. The security engineer re-ran independently and confirmed. These tests cover migration, auth, and healthz endpoints; none cover the AC1–AC9 invariant, which is entirely covered by the non-skipped guard tests.

```
$ pnpm typecheck → rc=0 (clean)
$ pnpm lint      → rc=0 (clean)
```

---

### 3. Container Matrix (Evidence from be-developer, verified by security engineer)

Real containers run with `-v` teardown between cases:

| Case | `.env` setup | Result |
|------|-------------|--------|
| 1 | `cp .env.example .env` verbatim | `docker compose up` **REFUSES**: compose exit=1, DB container exits (1) — Postgres refuses to initialize because `POSTGRES_PASSWORD` is empty; backend container never starts (`created` state) |
| 1b | same copy + `POSTGRES_PASSWORD` supplied only | Backend starts far enough to hit ABS-262 gate: exits 1 with `Error: BACKEND_BOOTSTRAP_TOKEN is required outside dev (NODE_ENV=<unset>)` |
| 2 | copy + uncomment LOCAL DEV ONLY block | Boots. `/healthz` → `{"status":"ok"}`. Admin token seeded. `role: admin` on whoami. |
| 3 | `NODE_ENV=production` + strong token, dev block untouched | Boots. `/healthz` ok. Dev-default token → **HTTP 401**. Strong token → HTTP 200. |

**AC1/AC-8 ordering (adjudicated):** On a verbatim copy, the DB gate fires before the token gate because AC-8 removed the DB credential, so Postgres refuses to initialize and `depends_on: service_healthy` prevents the backend from starting. The token error cannot print in case 1. Case 1b proves the gate is live on the copy path. The system architect adjudicated this as **ACCEPTED** (which gate speaks first is not a security property; AC1's property — "verbatim copy must not yield a running dev environment" — holds absolutely). The security engineer concurred independently.

---

### 4. Supply-Chain Verification (js-yaml)

`js-yaml@5.2.1` is classified as `devDependencies` in `backend/packages/core/package.json` — not a production dependency, not reachable from the runtime image. The security engineer confirmed: integrity-pinned, audit-clean.

---

## AC Checklist

| AC | Criterion | Result |
|----|-----------|--------|
| AC1 | After `cp .env.example .env` verbatim, `docker compose up` REFUSES to boot (proven by real containers) | ✅ MET (AC1/AC-8 ordering adjudicated; security property holds in full) |
| AC2 | `.env.example` has no active `BACKEND_BOOTSTRAP_TOKEN=dev-bootstrap-token-change-me` and no active `NODE_ENV=development` | ✅ MET (only active line: `PORT=8420`) |
| AC3 | Local dev works in one documented step (copy + uncomment block → boots, `/healthz` ok, token seeded) | ✅ MET (container case 2) |
| AC4 | Guard asserts invariant across BOTH files, fails on ALL four required forms | ✅ MET (18 guard tests, all pass; 13 mutants including all 4 required forms) |
| AC5 | Guard mutation-proven: each of four forms shown to FAIL when reintroduced | ✅ MET (13 mutants in MUTANTS table, all caught; asserted on every run) |
| AC6 | `docker-compose.yml` has no `:-postgres` default for `POSTGRES_PASSWORD`; header declares local-dev artifact | ✅ MET (`${POSTGRES_PASSWORD:-}`, header present) |
| AC7 | Gates green: `pnpm -r test`, `pnpm typecheck`, `pnpm lint` | ✅ MET (49 pass/0 fail non-DB; 59 pass/0 fail/0 skip hot; typecheck rc=0; lint rc=0) |
| AC8 (PO) | After verbatim copy, no active line supplies DB credential | ✅ MET (only active line: `PORT=8420`) |
| AC9 (PO) | Guard covers six mutation-proven forms (all of AC4+AC5 plus DB-password forms in both files) | ✅ MET (13 forms covered, exceeds required 6) |

---

## Definition of Done

- [x] All ACs met
- [x] Copy-hazard closed on real containers (container matrix cases 1/1b/2/3)
- [x] Guard mutation-proven across 13 forms (AC requires 6)
- [x] lint/typecheck/tests green

---

## Non-Blocking Follow-up Findings

Five guard blind spots filed by the security engineer as a follow-up story (not blocking this ticket):
- **E**: YAML merge keys not flattened before the check
- **F**: dotenv `export KEY=value` prefix blinds the entire dotenv half
- **G**: `env_file:` in compose is invisible to the compose walk
- **I**: CRLF line endings disarm the dotenv scanner (mitigated at commit boundary by `.gitattributes text=auto eol=lf`)
- Non-recursive discovery (files nested under subdirectories not scanned)

None of these are present in the current tree. All require a future author to introduce an idiom not currently in the file.

---

## Verdict

**APPROVED** — All nine ACs are met. Implementation is correct and minimal (three file edits + guard rewrite). Security property verified by two independent reviewers (system architect + security engineer) plus this QAS pass. No blocking finding.
