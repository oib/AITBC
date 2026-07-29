# Tracker Migration Runbook — Jira → Agentic Backend (Koexistenz)

> **Epic ABS-326, Story ABS-329.** Operational guide for the coexistence phase in which the
> v3 agentic backend (ADR-A-0021, epic ABS-229) runs alongside Jira until it is provably
> error-free. Three phases: **Shadow** (Jira leads, backend mirrors) → **Pilot** (backend
> leads one low-risk lane, Jira as write-behind safety net) → **Cutover** (Jira read-only,
> then decommissioned).
>
> **Human-only boundary:** every phase transition (Shadow→Pilot, Pilot→Cutover) and the final
> Jira decommissioning is an **Operator decision**. Agents prepare evidence (conformance runs,
> divergence reports, sandbox runs); they never flip a phase. Steps marked **[OPERATOR]** must
> not be executed by an autonomous seat.

The generic `TRACKER_CMD` switching recipe (import, env swap, dry-run, go-live) lives in
[ORCHESTRATOR_SOP.md → "TRACKER_CMD switching recipe"](ORCHESTRATOR_SOP.md) (ABS-242) — this
runbook references it instead of duplicating it.

## Tooling map

| Tool | Role in the migration |
| --- | --- |
| `scripts/jira-tracker.sh` | Primary adapter while Jira is source of truth (ABS-64) |
| `scripts/backend-tracker.sh` | Backend adapter, conformance-proven drop-in (ABS-237) |
| `scripts/shadow-tracker.sh` | Dual-write shim: Jira primary + backend mirror, mirror failures only logged (ABS-327) |
| `scripts/tracker-divergence.sh` | Read-only Jira↔backend diff; Markdown+JSON report + gate exit code (ABS-328) |
| `tests/test-backend-tracker.sh` | Conformance suite — the Shadow→Pilot gate's functional leg (ABS-237) |
| `work/.shadow-mirror.log` | Replay-able log of mirror ops the backend missed |
| `work/divergence/` | `report.md` / `report.json` / `history.log` (gate evidence stream) |

---

## Sandbox-Pflicht für Backend-Tests (ABS-374)

**Incident 2026-07-16:** a seat test re-initialized the operator's LIVE demo backend —
compose derives the project name from the `backend/` directory, so every checkout (worktree,
`tmp/ABS-XXX-work`) lands in the same compose project and replaces its containers/volumes.

Binding rules for every backend deploy/smoke test (agent or human):

- **Taboo:** the default compose project and host port **8420** (and 5432) belong to the
  operator's live instance. Never `docker compose up`/`down` there from a test.
- **Own project + ports:** always `docker compose -p <unique-name>` plus own
  `BACKEND_PORT` / `POSTGRES_HOST_PORT` (see `backend/docker-compose.yml` header).
- **Guard first:** run `backend/scripts/sandbox-guard.sh "$BACKEND_URL"` **before**
  provisioning; after provisioning your own stack, write the `$SANDBOX_MARKER` file so
  subsequent guard calls recognize the instance as yours.
- **Clean up:** `docker compose -p <unique-name> down -v` when the test is done.

## Phase 1 — Shadow (Jira leads, backend mirrors)

**Goal:** the backend receives every mutating tracker op the lane performs, with **zero**
blast radius on the running lane. Jira remains the only source of truth.

### Preconditions

- [ ] ABS-237 conformance suite green on the target backend build: `bash tests/test-backend-tracker.sh`
- [ ] Backend reachable and provisioned (`BACKEND_URL`, registered `BACKEND_TOKEN`, project
      with **key parity** — the backend carries the ABS keys 1:1, no mapping)
- [ ] Existing fenced tickets imported into the backend (SOP switching recipe, step 1) so
      mirrored comments/transitions do not 404
- [ ] Jira env present as for any live run (`JIRA_SITE`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
      `JIRA_PROJECT_KEY`, fence via `JIRA_JQL_FILTER`)

### Launcher env

```bash
export TRACKER_CMD=scripts/shadow-tracker.sh   # Jira primary + backend mirror
# shim internals (defaults shown; usually nothing to set):
# export SHADOW_PRIMARY_CMD=scripts/jira-tracker.sh
# export SHADOW_MIRROR_CMD=scripts/backend-tracker.sh
# export SHADOW_MIRROR_LOG=work/.shadow-mirror.log
```

### Verification (after enabling)

1. One manual op through the shim, output byte-identical to the direct Jira call:
   `TRACKER_CMD` `get`/`comment` on a test ticket; compare with `scripts/jira-tracker.sh` direct.
2. Backend shows the mirrored op (board or `scripts/backend-tracker.sh get <id>`).
3. Kill the backend container, repeat an op: Jira result unchanged, missed op appears in
   `work/.shadow-mirror.log` in replay format.
4. Start the divergence reporter on a schedule (cron/watcher; it is read-only):
   `scripts/tracker-divergence.sh` — exit 0 = clean, 1 = unexplained divergence, 2 = error.

### Daily operation

- Review `work/divergence/report.md` when the reporter exits non-zero.
- Real backend gaps → fix ticket; **known/accepted** gaps → whitelist entry in
  `work/tracker-divergence-whitelist.txt` (`<key-glob>|<field-glob>|<reason>`), so the
  clean-days counter is not wedged by explained noise. The fixVersion field gap is
  whitelisted built-in.
- Replay missed mirror ops after backend downtime:
  ```bash
  # every non-comment line: <ts> rc=<n> -- <argv>; replay the argv part
  grep -v '^#' work/.shadow-mirror.log | while IFS= read -r line; do
    eval "scripts/backend-tracker.sh ${line#* -- }"
  done
  # then truncate the log (operator judgement): : > work/.shadow-mirror.log
  ```
- `key-mismatch` lines mean the backend's key sequence diverged from Jira's — stop, reconcile
  (re-import), do not continue counting clean days until resolved.

### Gate: Shadow → Pilot **[OPERATOR]**

All three, per the epic (normative):

- [ ] Conformance suite (ABS-237) green against the production backend build
- [ ] **≥ 5 operating days** of divergence history without an unexplained entry —
      evidence: `work/divergence/history.log` (`unexplained=0` on every line in the window)
- [ ] One full sandbox epic run against the backend (run-boilerplate lane,
      `TRACKER_CMD=scripts/backend-tracker.sh`) completed without tracker intervention

---

## Phase 2 — Pilot (backend leads one low-risk lane)

**Goal:** one real, low-risk lane runs with the backend as its tracker; Jira keeps being
updated (write-behind) so an instant rollback loses nothing.

### Preconditions

- [ ] Shadow→Pilot gate checklist above signed off **[OPERATOR]**
- [ ] Pilot lane chosen: low-risk, fenced disjoint from all Jira-led lanes
      (two-orchestrator partition rules apply: own state dir, disjoint fence)

### Launcher env (pilot lane only)

```bash
export TRACKER_CMD=scripts/shadow-tracker.sh
export SHADOW_PRIMARY_CMD=scripts/backend-tracker.sh   # backend now leads…
export SHADOW_MIRROR_CMD=scripts/jira-tracker.sh       # …Jira is the write-behind net
export SHADOW_MIRROR_LOG=work/.shadow-mirror-pilot.log
```

The shim is direction-agnostic: primary/mirror are env, so the same zero-blast-radius
machinery covers the reversed direction. Non-pilot lanes stay on Phase-1 env.

### Verification

1. Orchestrator `--dry-run --once` on the pilot lane (SOP recipe step 2).
2. First ticket walk: JOIN, escalation, and one human intervention via the board (spec S8)
   all round-trip; Jira shows the write-behind copy.
3. Divergence reporter now runs with reversed roles:

   ```bash
   DIVERGENCE_PRIMARY_CMD=scripts/backend-tracker.sh \
   DIVERGENCE_MIRROR_CMD=scripts/jira-tracker.sh \
   scripts/tracker-divergence.sh
   ```

### Gate: Pilot → Cutover **[OPERATOR]**

- [ ] One **real epic cycle** completed entirely on the pilot lane — including JOIN,
      escalation, and a human intervention via the board — **without any manual tracker
      intervention** (evidence: epic merge log + divergence history over the cycle)

---

## Phase 3 — Cutover (Jira read-only → decommissioned)

**[OPERATOR]** — every step in this phase.

1. Announce cutover; stop all Jira-led lanes at a lane boundary.
2. Final import/sync of any Jira-only residue into the backend (SOP recipe step 1), then a
   final divergence run must be clean: `scripts/tracker-divergence.sh` → exit 0.
3. Switch every lane to the plain backend adapter (no shim):
   `export TRACKER_CMD=scripts/backend-tracker.sh` (SOP recipe steps 2–3).
4. Set Jira read-only (project permission scheme), keep it as archive for one release cycle.
5. Decommission: remove Jira env from launchers; `scripts/jira-tracker.sh` stays in the repo
   for Jira-profile consumers (ADR-A-0021 Consequences).

---

## Rollback

Jira is carried along in every pre-cutover phase, so rollback is an env flip — no data
migration.

**Immediate rollback (STOP-triggers):** data loss, status corruption, or key-sequence
divergence (`key-mismatch` without reconciliation path).

1. **[OPERATOR]** Stop the affected lane's orchestrator.
2. Flip the lane back to Jira-led env:
   - from Shadow: `export TRACKER_CMD=scripts/jira-tracker.sh` (drop the shim), or keep the
     shim with default direction — both are safe; the shim direction decides only who leads.
   - from Pilot: restore the Phase-1 env block (Jira primary).
3. Aftercare: replay the pilot lane's mirror log (`work/.shadow-mirror-pilot.log`, procedure
   above, target = `scripts/jira-tracker.sh`) so Jira holds every op the backend led on;
   then run the divergence reporter and resolve to exit 0.
4. File the incident ticket; the clean-days counter for the affected gate restarts at zero.

**Ticket-only triggers (lane stays on the backend):** purely functional bugs without data
loss — file a ticket, keep operating, whitelist an explained divergence only if the bug
produces one.

| Trigger | Category | Action |
| --- | --- | --- |
| Data loss (ticket/comment vanished) | STOP | Immediate rollback, incident ticket |
| Status corruption (state machine broken) | STOP | Immediate rollback, incident ticket |
| Unreconciled `key-mismatch` | STOP | Immediate rollback, re-import, incident ticket |
| Functional bug, no data loss | Ticket | Fix-forward on the backend lane |
| Backend downtime in Shadow | none | By design: Jira unaffected; replay mirror log after recovery |
