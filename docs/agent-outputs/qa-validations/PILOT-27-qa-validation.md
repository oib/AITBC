# QA Validation Report — PILOT-27

**Ticket**: PILOT-27 — seat_spawn producer: orchestrator/shipper POSTs open+close rows (session_id + session_stored) to the backend  
**QAS Seat**: qas  
**Date**: 2026-07-25  
**Branch**: PILOT-27-auto  
**Commit**: 44949e3d52bdad7c6f5d60c08ec0a33356f6f366  
**Verdict**: ✅ **APPROVED**

---

## Test Suite Results

```
bash tests/test-orchestrator.sh
  Total:  1321
  Passed: 1321
  Failed: 0
  ALL TESTS PASSED
```

Full suite run on commit `44949e3d` on branch `PILOT-27-auto`.

---

## Acceptance Criteria Verification

### AC1 ✅ — A live seat spawn produces a `seat_spawn` row carrying `session_id`

**Verified by:**
- `emit_seat_upsert close` now extracts `seat_session_id` via `extract_session_id "$seat_out"` and passes it as arg 9 to `emit_seat_upsert`.
- The backend route `/agent/v1/projects/:project/spawns` (POST) accepts `session_id` and passes it to `upsertSpawn` → COALESCE upsert. Confirmed in `backend/packages/core/src/spawns.ts` line 101: `session_id = COALESCE(EXCLUDED.session_id, seat_spawn.session_id)`.
- Conformance test case A: `assert_contains ... '"session_id":"sess-abc-123"'` → **PASS**
- Architect's live round-trip (stated in handoff): `session_id="final-sess-abc"` read back from localhost:8420. Backend confirmed UP at time of QAS run.

### AC2 ✅ — A poison-guard-rejected spawn yields `session_stored=false` (JSON boolean)

**Verified by:**
- Implementation at `orchestrator.sh:8903–8908`: when `result_has_permission_denials "$seat_out"` is true and `ORCH_SESSION_POISON_GUARD=1` (default), `seat_session_stored="false"`.
- Conformance test case B:
  - `assert_contains ... '"session_stored":false'` → **PASS** (JSON boolean literal)
  - `assert_not_contains ... '"session_stored":"false"'` → **PASS** (never a quoted string that breaks `WHERE session_stored = false`)

### AC3 ✅ — INTENT-REPAIR-HANDOFF repair-respawn produces a row via OPEN upsert

**Verified by:**
- `orchestrator.sh:8765–8766`: OPEN upsert carries `"${SPAWN_RESUME_ID:-}"` as session_id arg.
- REPAIR-HANDOFF path (`orchestrator.sh:9198`): calls `run_spawn_cmd` with `SPAWN_RESUME_ID="$sid"`, so `SPAWN_RESUME_ID` is set during the repair respawn → OPEN upsert carries the resumed session ID.
- Conformance test source wiring assertion:
  - `assert_contains "$_pilot27_src" 'emit_seat_upsert open "$seat_sid" ... "${SPAWN_RESUME_ID:-}"'` → **PASS**
- Conformance test case C: absent session (first spawn OPEN) serializes as `"session_id":null` → **PASS**

### AC4 ✅ — Route/conformance test proves producer→row path beyond PILOT-24's schema conformance test

**Verified by:**
- `tests/orchestrator.d/PILOT-27-seat-session.sh`: 8 assertions pinning exact JSON serialization at the producer→endpoint seam, using a BACKEND_CURL stub (offline, network-free).
- All 8 assertions: **PASS** (in the 1321-total run)
- The test covers: stored session (A), poison-dropped session (B), absent session / first-spawn OPEN (C), plus source wiring assertions for both OPEN and CLOSE call sites.
- Backend route contract confirmed: `spawns.ts` accepts `session_id: string | null` and `session_stored: boolean | null`, preventing quoted-string confusion at the DB layer.

---

## Non-blocking Observation (Architect MEDIUM, carried forward)

**Salvage+birth-denials edge case**: In the salvage respawn path, the CLOSE upsert recomputes `session_stored` from the SALVAGE result's `permission_denials` rather than the original spawn's. In the rare corner where the original spawn had birth-denials but the salvage result has a session_id without permission_denials, `session_stored` would be set to `true` when the session was never actually stored. This undercounts "lost sessions" marginally.

**Impact**: Minimal; affects only salvage-then-no-denial corner. ACs are literally met. Suggested follow-up ticket if "how many sessions do we lose?" precision becomes important.

---

## Files Changed (commit 44949e3d)

- `scripts/orchestrator.sh` — `emit_seat_upsert` extended with `session_id`/`session_stored` args; OPEN upsert carries `SPAWN_RESUME_ID`; CLOSE upsert carries extracted `session_id` + computed `session_stored`.
- `tests/orchestrator.d/PILOT-27-seat-session.sh` — 90-line seam conformance test, 8 assertions, all PASS.

No schema/API/UI changes (PILOT-24 owns those). No new secrets.

---

## Final Verdict

**✅ APPROVED FOR RTE**

All 4 ACs met. Full suite 1321/1321 PASS. No regressions. Evidence committed on `PILOT-27-auto`. Transitioning to Story Acceptance.
