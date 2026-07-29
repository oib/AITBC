# ABS-269 — Stack-Applicability-Guard: unresolvable profile fails CLOSED

**Status**: implemented | **Parent**: ABS-278 | **Predecessor**: ABS-257 (Done)

## Problem

A `.active-profile` naming a profile with no `profiles/<name>/` directory degraded to `neutral`
(`scripts/lib/profile.sh:120`). `neutral` declares **no `stack:` key**, and "no key" means
"filtering off", so the misconfiguration silently served the **full library**: all 24 patterns,
of which only 10 are `generic` and 14 assume a specific stack (Next.js/Prisma/Clerk/Playwright).
Third instance of the same fail-open family, after `stack: []` and the worktree resolution (both
fixed in ABS-257).

> The ticket says "11 stack-fremde Patterns"; measured against HEAD the number is **14**
> (`pattern-applicability.sh --all` reports 14 `EXCLUDED`). The defect is unchanged; only the
> count is corrected.

Reproduced by the PO: an untracked `profiles/fastapi/` produced
`WARN profile 'fastapi' not found …; falling back to neutral` and then handed the FastAPI seat
every Next.js pattern.

## #PATH_DECISION — fail closed to `generic`, exit stays 0

**Chosen**: an unresolvable profile turns filtering **ON with an empty stack** (`generic`-only,
exactly like `stack: []`), plus a loud `FAIL-CLOSED` WARN on stderr. The guard still **exits 0**.

Rationale — a *declared* profile is an expressed intent. The consumer said "I have a stack"; the
name is merely not findable. That is the `stack: []` case (declaration present, intersection
empty), not the "no `stack:` key" case (no declaration, back-compat opt-out). The deliberate
asymmetry the guard already encodes therefore extends naturally: **absent key ≠ unresolvable name**.

**Rejected — additional exit ≠ 0.** The `pattern-discovery` skill consumes this script's stdout.
A hard failure would convert a *misconfiguration* into a *broken seat*: no patterns at all, and a
capability provider that dies rather than degrades (ABS-269 AC4 explicitly forbids that). A
non-zero exit also buys nothing the WARN does not already buy — the seat is told, loudly, that it
was filtered. Fail-closed = maximum *protection*, not maximum *breakage*.

## Blast radius: `get_active_profile()` is shared

`get_active_profile()` is consumed by both capability providers, so the fix could not simply
change its fallback:

| Consumer                            | Needs                                                          |
| ----------------------------------- | -------------------------------------------------------------- |
| `scripts/pattern-applicability.sh`  | must know the profile is unresolvable → fail closed             |
| `scripts/hooks/evolver-lifecycle.sh` | needs a name that **resolves**, or the hook hard-breaks         |

Resolution: `get_active_profile()` keeps its `neutral` degradation **unchanged** (providers stay
safe). ABS-269 adds `get_requested_profile()` — the requested name, precedence applied, *not*
validated — plus `profile_is_resolvable()`. The pattern guard asks for the **requested** name and
fails closed itself. No behavior change for any other caller.

## Acceptance evidence

`bash tests/test-pattern-applicability.sh` → **37/37 pass** (22 pre-existing ABS-257 assertions
still green = AC6). Also green: `test-profile-activation.sh` (17), `test-evolver-lifecycle.sh`,
`test-harness-parity.sh`.

| AC  | Covered by                                                                          |
| --- | ----------------------------------------------------------------------------------- |
| AC1 | unresolvable profile → `generic` subset, no `api/`/`ui/`/`database/` pattern; plus the real worktree + file-activation path (the PO's repro) |
| AC2 | absent `stack:` key → still unfiltered (24/24); `stack: []` → still `generic`-only  |
| AC3 | WARN names profile, searched path, and `FAIL-CLOSED`                                |
| AC4 | `get_capability_provider` on an unresolvable profile resolves as `neutral`; `evolver-lifecycle.sh` exits 0 |
| AC5 | this section                                                                        |
| AC6 | full ABS-257 suite green                                                            |

Real-repo check (`ACTIVE_PROFILE=fastapi scripts/pattern-applicability.sh`, the PO's repro): 10
patterns served, all `generic`; 14 stack-specific ones excluded; exit 0. `ACTIVE_PROFILE=neutral`:
still 24 (back-compat intact).
