# ABS-319 Test-Prep fixtures — `lane` as a first-class tracker field

Provisioned by the Data-Provisioning Engineer (Test Prep seat) so QAS can exercise
**AC1–AC5** with **zero setup gaps**. The story touches only the shell tracker
adapters (`scripts/mock-tracker.sh` + the Jira parity path) — there is **no DB,
no Prisma, no RLS surface** — so the "fixtures" are seeded tracker records in an
isolated, throwaway state directory rather than DB rows.

## Load the fixtures (one command)

```bash
eval "$(tests/fixtures/abs319-lane/seed.sh)"
# exports: FIX_DIR, MOCK_TRACKER_TICKETS_DIR (=FIX_DIR), FL_ID (fastlane), NL_ID (normal)
```

`seed.sh` is idempotent and wipes/re-seeds `$FIX_DIR` on every run. It NEVER writes
to `work/tickets` — `MOCK_TRACKER_TICKETS_DIR` is pointed at a temp dir.

## Seeded data (per AC)

| Ticket | How created | Lane | Exercises |
|--------|-------------|------|-----------|
| `$FL_ID` | `create --lane fastlane` | `fastlane` | AC1 (explicit), AC3 (included), AC4 (field not label) |
| `$NL_ID` | `create` (no `--lane`)   | `normal` (default) | AC1 (default), AC2 (flip target), AC3 (excluded) |

## Run the ACs against the fixtures

```bash
A=scripts/mock-tracker.sh
# AC1 — explicit fastlane + default normal
"$A" get "$FL_ID" | grep '^lane:'      # -> lane: fastlane
"$A" get "$NL_ID" | grep '^lane:'      # -> lane: normal
# AC2 — flip both ways on the normal ticket
"$A" update "$NL_ID" lane fastlane && "$A" get "$NL_ID" | grep '^lane:'   # fastlane
"$A" update "$NL_ID" lane normal   && "$A" get "$NL_ID" | grep '^lane:'   # normal
# AC3 — filter (with NL_ID back to normal)
"$A" search --lane fastlane            # -> only $FL_ID
"$A" search --lane normal              # -> only $NL_ID
# AC4 — lane is a frontmatter field, never a label token
"$A" get "$FL_ID" | grep -E '^(lane:|labels:)'   # lane: present; no lane:<x> in labels
# AC5 — invalid values rejected non-zero
"$A" create --type ticket --prefix DEMO --title bad --lane bogus; echo "exit=$?"  # exit=1
"$A" update "$FL_ID" lane bogus;                                  echo "exit=$?"  # exit=1
```

## RLS test contexts

**N/A for this story.** The change lives entirely in the shell tracker adapters;
there is no `withUserContext` / `withAdminContext` / `withSystemContext` surface to
seed. The System-Architect In-Review gate confirmed RLS/auth/migrations/layering
are N/A here. No RLS seeds are required and none are provided — this is documented
so QAS does not bounce looking for setup that does not exist.

## Jira-adapter parity note (from the In-Review gate, non-blocking)

`search --lane normal` diverges for label-less **legacy** tickets: the mock treats a
missing `lane` as `normal` (matches), while the Jira JQL `labels = lane:normal`
excludes tickets with no lane label. New tickets always carry the field explicitly,
so no AC is affected. The authoritative routing query is `--lane fastlane` (identical
in both adapters). QAS should assert on `--lane fastlane`; `--lane normal` on legacy
tickets is out of scope.
