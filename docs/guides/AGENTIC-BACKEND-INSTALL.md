# Agentic Backend — Install Guide

> **Spec:** ABS-229 §9/§10 · **ADR:** [ADR-A-0021](../../adrs/agentic/ADR-A-0021-agentic-delivery-backend.md)
> **Profile:** [`profiles/agentic-backend/profile.yaml`](../../profiles/agentic-backend/profile.yaml)

This guide takes a new consumer from zero to a running board, registered orchestrator, and
working `TRACKER_CMD`. One `docker compose up` command starts everything; the board is the
only UI needed for setup.

---

## Prerequisites

- Docker (Engine 24+ or Docker Desktop) with Compose v2 (`docker compose`)
- `bash` and `curl` (for the registration step below)
- This boilerplate repo checked out locally

---

## Step 1 — Configure secrets

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and set **two required values**:

| Variable | Requirement |
| --- | --- |
| `POSTGRES_PASSWORD` | Any strong password (letters + digits, no `$`/`@` — Postgres URL-safe). |
| `BACKEND_BOOTSTRAP_TOKEN` | A random 32+ char string; this is the one-time admin credential. Store it somewhere safe — it seeds the org-wide admin token and is used in the registration step below. |

> Compose **fails fast** if either variable is unset — there is no public default and no secret
> is baked into the image.

---

## Step 2 — Start the stack

```bash
cd backend
docker compose up --build --wait
```

`--wait` blocks until the backend container reports **healthy**. Migrations run automatically on
first boot (idempotent — restarting a running stack is safe).

Verify:

```bash
curl -sf http://localhost:8420/healthz
# -> {"ok":true}
```

The **board** is served at `http://localhost:8420` — open it in a browser. It shows an empty
kanban at this point; the next steps populate it.

---

## Step 3 — Create a project

All admin calls use `BACKEND_BOOTSTRAP_TOKEN` as the Bearer token.

```bash
TOKEN=<your BACKEND_BOOTSTRAP_TOKEN>
BASE=http://localhost:8420

curl -sf -X POST "$BASE/api/admin/projects" \
  -H "authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"key":"ABS","name":"My project"}'
# -> {"id":"...","key":"ABS","name":"My project"}
```

Replace `ABS` with your project key and `My project` with your project name.

---

## Step 4 — Register the orchestrator

```bash
curl -sf -X POST "$BASE/agent/v1/orchestrators" \
  -H "authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"project":"ABS","instance":"orch-01"}'
# -> {"token":"<project-scoped-token>","project":"ABS","instance":"orch-01"}
```

**Save the returned `token` — it is printed exactly once.** This is the project-scoped
orchestrator token that goes into `BACKEND_TOKEN`.

---

## Step 5 — Wire up the orchestrator

Export the token and point the orchestrator at the backend adapter:

```bash
export BACKEND_URL=http://localhost:8420
export BACKEND_TOKEN=<token from step 4>
export TRACKER_PROJECT=ABS
export TRACKER_CMD=scripts/backend-tracker.sh
```

Smoke-test the adapter:

```bash
"$TRACKER_CMD" capabilities
# -> packet
#    brief
#    assign
```

Dry-run the orchestrator to confirm the wiring:

```bash
scripts/orchestrator.sh --dry-run --once
# -> provenance: harness=... target=...
#    INTENT SKIP-UNLABELLED (or INTENT NOOP — expected in an empty project)
```

Go live when ready (spawns real subagents, incurs LLM cost):

```bash
scripts/orchestrator.sh --live
```

---

## Step 6 — Board URL and live monitoring

The board at `http://localhost:8420` shows:

- **Kanban** — tickets by status column, derived from your `profiles/neutral/adapters/statuses.yaml`.
- **Escalation inbox** — Blocked, Needs PO Decision, Ready for Epic/Human Acceptance tickets.
- **Orchestrators** — registered instances with live/stale status (stale after 90 s of inactivity).
- **Event feed** — live SSE tail of every transition and comment.

Log in with the bootstrap token or any admin token. The board polls SSE and updates in real time.

---

## Import existing tickets (optional)

If you have existing mock-tracker tickets in `work/tickets/`, import them:

```bash
tar -cf - -C work/tickets . | \
  curl -sf -X POST "$BASE/api/admin/import?project=ABS" \
    -H "authorization: Bearer $TOKEN" \
    -H "content-type: application/x-tar" \
    --data-binary @-
```

Each `.md` file in the tarball becomes a work item. Imported tickets round-trip
byte-identically through `get` (ABS-239 AC#2).

---

## Backup

Two independent backup paths:

### Canonical export tarball (vendor-lock escape hatch)

```bash
curl -sf "$BASE/api/export?project=ABS" \
  -H "authorization: Bearer $TOKEN" \
  -o backup-$(date +%F).tar

# Restore into a fresh project:
curl -sf -X POST "$BASE/api/admin/import?project=ABS" \
  -H "authorization: Bearer $TOKEN" \
  -H "content-type: application/x-tar" \
  --data-binary @backup-YYYY-MM-DD.tar
```

### pg_dump physical backup (full database, including events and revisions)

```bash
# Dump (custom format):
docker compose exec -T db pg_dump -Fc -U postgres agentic > agentic-$(date +%F).dump

# Restore into a clean database:
docker compose exec -T db psql -U postgres \
  -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' agentic
docker compose exec -T db pg_restore --clean --if-exists \
  -U postgres -d agentic < agentic-YYYY-MM-DD.dump
```

The named volume `backend-data` persists pgdata across container restarts. Mount it to a host
path or use your container runtime's volume backup tooling for automated snapshots.

---

## Reference

| Resource | Path |
| --- | --- |
| Profile | `profiles/agentic-backend/profile.yaml` |
| Adapter source | `scripts/backend-tracker.sh` |
| Conformance suite | `tests/test-backend-tracker.sh` |
| API reference | `docs/guides/AGENTIC-BACKEND-API.md` |
| Decision record | `adrs/agentic/ADR-A-0021-agentic-delivery-backend.md` |
| Phase-1 spec | `specs/ABS-229-agentic-backend-phase1-spec.md` |
| Orchestrator SOP | `docs/sop/ORCHESTRATOR_SOP.md` → § "Agentic Backend Binding" |
| Backend source README | `backend/README.md` |
