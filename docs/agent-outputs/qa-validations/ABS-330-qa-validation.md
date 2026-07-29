# QA Validation Report — ABS-330

**Ticket**: ABS-330 — Adapter: fixVersion support on `create`/`update` (+ parent inheritance)
**Branch**: `ABS-330-auto`
**Commit reviewed**: `e889cf1 feat(tracker): fixVersion on create/update + parent inheritance [ABS-330]`
**QAS actor**: qas
**Date**: 2026-07-16
**Verdict**: ✅ APPROVED → Story Acceptance

---

## Validation Environment

- Worktree: `/tmp/ABS-330-work` (branch `ABS-330-auto`, based on main `dcc6a60`)
- Test harness: `tests/test-jira-tracker.sh` (offline-contract tier, `JIRA_CURL=tests/fixtures/jira-curl-shim.sh`)
- Adapter-lint: `tests/test-tracker-adapter-lint.sh`
- No live token required; all ACs assert against constructed request payloads (AC spec: no network)
- Live smoke tier skipped (JIRA_LIVE_TOKEN not set; intentional per ticket spec)

---

## Suite Results (Independent Run)

| Suite | Result |
|---|---|
| `bash -n scripts/jira-tracker.sh` | **SYNTAX_OK** |
| `tests/test-jira-tracker.sh` | **171/171 PASS** (1 skip: live smoke) |
| `tests/test-tracker-adapter-lint.sh` | **8/8 PASS** |

---

## Acceptance Criteria — Independent Verification

### AC1 ✅ — `create --fix-version <v>` builds `fields.fixVersions=[{"name":<v>}]`

**Spot-check command:**
```
create --type ticket --title "AC1 test" --fix-version v3.0.0
```
**Captured payload `fields.fixVersions`:** `[{"name": "v3.0.0"}]`
**PASS** — payload confirmed via `JIRA_SHIM_CAPTURE_BODY` capture without network.

---

### AC2 ✅ — `create --parent <epic>` inherits parent's fixVersion; parent with none adds none

**Spot-check (parent has v3.0.0 — fixture `ABS-201`):**
```
create --type ticket --title "Inherited child" --parent ABS-201
```
**Captured `fixVersions`:** `[{"name": "v3.0.0"}]`
**PASS** — inheritance confirmed.

**Spot-check (parent has no fixVersion — fixture `ABS-101`):**
```
create --type ticket --title "No-ver child" --parent ABS-101
```
**Captured `fixVersions`:** `null` (key absent)
**PASS** — no error, no fixVersions added.

---

### AC3 ✅ — Explicit `--fix-version` overrides inheritance

**Spot-check:**
```
create --type ticket --title "Explicit wins" --parent ABS-201 --fix-version v9.9.9
```
**Captured `fixVersions`:** `[{"name": "v9.9.9"}]`; `v3.0.0` **absent** from payload.
**PASS** — explicit value short-circuits the parent lookup.

---

### AC4 ✅ — `update <id> fix_version <v>` sets fixVersion; empty value rejected with clear die

**Spot-check (set):**
```
update ABS-104 fix_version v3.0.0
```
**Output:** `ABS-104: fix_version updated`
**Captured PUT `fields.fixVersions`:** `[{"name": "v3.0.0"}]`
**PASS** — success line + PUT payload confirmed.

**Spot-check (empty value):**
```
update ABS-104 fix_version ""
```
**Exit code:** 1 (non-zero ✅)
**Error:** `ERROR: update: fix_version requires a non-empty value`
**PASS** — clear die message consistent with sibling field checks (`lane`, `priority`, `ac_blocking`).

---

### AC5 ✅ — Existing create/update invocations unchanged; full test suite passes

**Spot-check (plain create, no `--fix-version`, no `--parent`):**
```
create --type ticket --title "Plain create"
```
**Captured `fixVersions`:** `null`; `fixVersions` key **absent** from payload.
**PASS** — payload byte-identical to pre-change behavior.

**Test suite regression (Test 8: update success line parity):** `171/171` all green.
`test-tracker-adapter-lint.sh` argv/`--data-binary` guards: `8/8` PASS.

---

### AC6 ✅ — Help/usage block documents `--fix-version` on `create` and `fix_version` as an `update` field

**Verified in help output:**
- `create` usage line: `[--fix-version <v>]` present ✅
- `create` docs: describes inheritance default and explicit-wins semantics ✅
- `update` field list: `ac_blocking|fix_version` present ✅
- `update` docs: describes `fix_version` as remediation path; empty value rejected ✅

---

## Diff Scope

3 files, +133/-7, additive only:

| File | Change |
|---|---|
| `scripts/jira-tracker.sh` | `--fix-version` arg on `create`; inheritance lookup via `GET parent?fields=fixVersions`; `fix_version` field in `update`; help-block updates |
| `tests/fixtures/jira-curl-shim.sh` | Added `ABS-201` fixture (versioned epic for AC2 inheritance) |
| `tests/test-jira-tracker.sh` | 13 new assertions in Test 8d covering AC1–AC6 |

No product-code changes outside the bash adapter and its test/fixture files. No RLS/DB/auth surface. No merge-token issuance, epic-integration gate, or human-merge-to-main changes.

---

## Flags

Ticket carries **no `design` flag** → exit target is **Story Acceptance**.

---

## Verdict

**✅ APPROVED** — All 6 ACs met. Independent spot checks confirm. Suites green (171/171 + 8/8). Additive, regression-safe, parity-clean. Transitioning to **Story Acceptance**.
