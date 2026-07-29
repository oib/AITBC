# QA Validation — PILOT-74

**Ticket**: Status-Kollektor: Marker-Existenz statt Marker-Inhalt — falsches Human-Gate 'run paused'
**Branch**: `PILOT-74-auto`
**Commit under test**: `3aca1e4a`
**QAS run date**: 2026-07-27

---

## Verdict: APPROVED

---

## Evidence

### Test suite

```
bash tests/test-run-status-collector.sh
```

Run against commit `3aca1e4a` on `PILOT-74-auto`.

**Result: 41/41 PASS**

Full Case 4 output (the new regression tests):

```
Case 4: run-health markers read by content, not existence (PILOT-74)
  PASS  fastfail marker content '0' -> health ok
  PASS  fastfail marker content '0' -> no human gate
  PASS  fastfail empty marker -> health ok
  PASS  fastfail marker with real value -> paused
  PASS  fastfail real value -> human gate names marker+value
  PASS  halt marker content '0' -> health ok
  PASS  halt marker content '0' -> no human gate
  PASS  halt empty marker -> health ok
  PASS  halt marker with real value -> paused
  PASS  halt real value -> human gate names marker+value
  PASS  outage marker content '0' -> health ok
  PASS  outage marker content '0' -> no human gate
  PASS  outage empty marker -> health ok
  PASS  outage marker with real value -> paused
  PASS  outage real value -> human gate names marker+value
  PASS  no state dir -> health unavailable (honesty, not silent/invented)
  PASS  no state dir -> no invented pause alarm
```

### Shellcheck

- `scripts/run-status-collector.sh`: exit 0 (clean)
- `tests/test-run-status-collector.sh`: exit 0 at `-S warning`; one pre-existing SC1091 info note on line 21 (`.`-source of sandbox-guard.sh, not introduced by this commit — confirmed by checking the pre-fix file)

---

## AC Assessment

**AC1** — Marker content check, not existence, across all collector-read markers:

The implementation loops `for m in fastfail halt outage` (the three markers the collector reads — `probe-inflight` and `stop-file` are not read, per architect review). For each marker file it reads the value with `tr -d '[:space:]'` and skips on empty or `'0'`. Only a real non-zero non-empty value raises the gate (and names the value in the gate line). ✅

**AC2** — Regression test per marker type:

17 new assertions in Case 4 covering all three marker types × three sub-cases (content `'0'`, empty, real value), plus the AC3 honesty check pair. Each sub-case confirms: `'0'`/empty → `run.health: ok`, no gate; real value → `run.health: paused`, gate line includes `marker=<value>`. ✅

**AC3** — Honesty invariant preserved:

Case 3 ("no state dir → health unavailable, not silent") still passes. Case 4d explicitly tests no-state-dir outputs `run.health: unavailable` and no invented pause alarm. The `else` branch (`echo "run.health: unavailable"`) is unchanged. ✅

**AC4** — ABS-579 bridge note:

Informational AC. The commit message and in-code comment both name PILOT-74 and the fastfail reset-to-`'0'` behaviour as the source of the false alarm, making the interim nature of the file-based heuristic visible. ✅

---

## Commit reachability

```
git cat-file -e 3aca1e4a^{commit}  → exists
git for-each-ref --contains 3aca1e4a refs/heads refs/remotes → refs/heads/PILOT-74-auto, refs/remotes/origin/PILOT-74-auto
```

Commit is on the story branch and pushed to origin.

---

## No `design` flag → exit to `Story Acceptance`
