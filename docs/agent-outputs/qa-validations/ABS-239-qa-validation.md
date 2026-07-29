# QA Validation Report — ABS-239

**Ticket**: ABS-239 — Backend S7: Docker-Packaging + Daten-Lifecycle  
**Branch**: `ABS-239-auto`  
**Reviewed commit**: `139a6f1` (feat(api): Docker packaging + data lifecycle for the agentic backend [ABS-239])  
**QAS actor**: qas  
**Date**: 2026-07-16  
**Verdict**: ✅ **APPROVED**

---

## Validation Suite Results

| Check | Result | Notes |
|-------|--------|-------|
| `pnpm typecheck` | ✅ PASS | core + server, exit 0 |
| `pnpm lint` | ✅ PASS | eslint exit 0, no violations |
| `pnpm -r test` (83 core / 28 server) | ✅ **111/111 PASS** | Run with Postgres; 0 fail, 0 skip |
| `compose-lifecycle.sh` (DoD integration) | ✅ **9/9 assertions PASS** | Real compose up → import → export → restart → restore → pg_dump |

### Unit Test Detail (with DATABASE_URL set to Postgres 16-alpine)

```
packages/core: 83 pass / 0 fail / 0 skip
apps/server:   28 pass / 0 fail / 0 skip
Total:         111 pass / 0 fail / 0 skip
```

Key tests covering ABS-239 ACs:
- `AC#2 import DEMO-1.md → get renders byte-identical to the source` ✅
- `AC#3 export tarball is canonical; restore reproduces the ticket byte-for-byte` ✅
- `import ignores AppleDouble ._*.md members` ✅
- `AC#4 register orchestrator → project-scoped token; list shows live then stale` ✅
- `AC#5 import/export/register/projects require admin; agent → 403, anon → 401` ✅
- `packTar → unpackTar round-trips members of varied (non-512-aligned) sizes` ✅
- `unpackTar stops at the trailing zero blocks and yields only regular files` ✅
- `unpackTar rejects an entry whose declared size exceeds the cap` ✅

### Compose Lifecycle Test Detail

```
[1/9] compose up --build --wait on fresh volume       → PASS: compose up --wait succeeded (backend reached healthy)
[2/9] container health == healthy                      → PASS: State.Health.Status == healthy
[3/9] create project + import DEMO-1.md (tar)         → PASS: project created + DEMO-1 imported
[4/9] get renders byte-identical (AC#2)               → PASS: import→get is byte-identical
[5/9] export tarball carries canonical .md (AC#3)     → PASS: export DEMO-1.md is byte-identical
[6/9] volume persistence across container restart      → PASS: data survived container restart (named volume)
[7/9] restore = import of export, after wipe (AC#3)  → PASS: export→restore reproduces ticket byte-for-byte
[8/9] pg_dump -Fc backup → schema drop → pg_restore   → PASS: pg_dump/pg_restore round-trip byte-identical
[9/9] image hardening + registration (AC#4/#5)        → PASS: non-root, no baked secret, token not in history, registration live
ALL PASS (9 assertions)
```

---

## Acceptance Criteria Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC#1 | `docker compose up` → Server healthy, Migrations applied, Board erreichbar | ✅ PASS (with scope note) | compose-lifecycle.sh steps 1/9, 2/9; healthz confirmed healthy |
| AC#2 | Import DEMO-1.md → byte-identical get-rendering | ✅ PASS | compose-lifecycle.sh step 4/9; unit test `AC#2 import DEMO-1.md → get renders byte-identical` |
| AC#3 | Export-Tarball canonical .md; Restore documented + tested | ✅ PASS | compose-lifecycle.sh steps 5/9, 7/9, 8/9; README.md §4/§5 + pg_dump section |
| AC#4 | Registration → project-scoped Token; live/stale per Orchestrator | ✅ PASS (with scope note) | compose-lifecycle.sh step 9/9; unit test `AC#4 register orchestrator → project-scoped token` |
| AC#5 | Image non-root, no Secrets in Image, Token via Env/Secret-Mount only | ✅ PASS | compose-lifecycle.sh step 9/9; Security Engineer independently verified (commit 139a6f1) |

### DoD: Integration test compose-up→import→export→restore

✅ PASS — compose-lifecycle.sh 9/9 assertions pass end-to-end on a fresh Docker volume.

### Scope Notes (Accepted by SA + Security Engineer)

- **AC#1 "Board erreichbar"**: The dashboard SPA is ABS-241 (not built). The HTTP surface is reachable and healthy (`/healthz` → 200), which is the install-path portion of AC#1 deliverable here. The remaining UI is explicitly ABS-241 scope.
- **AC#4 "Dashboard zeigt live/stale"**: Delivered as `GET /api/v1/projects/:p/orchestrators` API; the dashboard view rendering is ABS-241 scope. The API the board will consume is tested and live.
- **Image size 322 MB vs spec §9 "target < 200 MB"**: Soft target, not an AC. Not blocking.

---

## Security Gate Evidence

The Security Engineer ran an independent gate on commit `139a6f1` (`ABS-239-auto`) and issued **PASS — no blocking finding**:
- Authz: all 5 new routes gated by `requireAdmin` + global bearer hook
- Tenant isolation: `resolveScope` enforces org boundary; project-scoped token pinned to its bound project
- Injection: SQL parameterized; tar unpack filesystem-free, 8 MiB bounded, basename-only, AppleDouble filtered
- Secrets (AC#5): `.dockerignore` tracked; compose fails closed (`:?`); non-root `USER app`; tokens sha256-hashed, `timingSafeEqual`, `randomBytes(24)`, plaintext once only

---

## Additional Findings (Non-Blocking)

1. **DB-skip trap** (pre-existing from ABS-235/236 harness): DB-backed tests SKIP with exit 0 when no Postgres is reachable. QAS independently verified by running without and then with a Postgres container — the behavior is real. Worth a separate ticket. Not introduced by ABS-239.
2. **Security Engineer follow-up (non-blocking)**: project-key charset validation + `Content-Disposition` uses raw `?project=` (admin-only; CRLF blocked by Node). Filed as non-blocking note for BSA.

---

## Final Verdict

**✅ APPROVED for Story Acceptance**

All 5 ACs met, DoD integration test green (9/9), 111/111 unit tests pass, typecheck + lint clean, Security Engineer gate PASSED. Scope notes for AC#1 (board UI) and AC#4 (dashboard view) are acknowledged scope boundaries — those belong to ABS-241.

