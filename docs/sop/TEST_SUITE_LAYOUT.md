# Test Suite Layout — where new tests go (ABS-215)

**Audience:** implementer seats (BE/FE/data/QAS) adding tests or touching the
orchestrator SOP header.

**Why this exists.** GoalSync rebases at the epic-integration gate kept
colliding on the same two shared-file "conflict magnets", and because agent
hand-resolve is forbidden (#EXPORT_CRITICAL, `rte` no-hand-resolve) every
collision forced a human round (ABS-181: 5 conflicts; earlier PR
#128/#129/#130/#139). ABS-215 removes both magnets. Follow the two rules below
and your change will not re-create them.

---

## 1. Orchestrator tests → one file per story (never append to the monolith)

`tests/tooling/test-orchestrator.sh` is a ~3.9k-line monolith. New tests used to be
**appended at the end**, so any two stories in flight edited the same trailing
region and conflicted on rebase.

**Do this instead:** drop a self-contained file at

```
tests/orchestrator.d/<TICKET>-<slug>.sh      e.g. tests/orchestrator.d/ABS-231-defer-window.sh
```

The runner `source`s every `tests/orchestrator.d/*.sh` into its own shell just
before the results tally, so your file shares the whole harness — the `assert_*`
helpers, the `orch` / `new_env` / `cleanup_env` functions, the
`PASS`/`FAIL`/`TOTAL` counters, and every env var exported at the top of the
monolith.

Rules for a per-story file:

- **No shebang, no `set -e`, no re-sourcing the harness** — the parent already
  did all three. Just write `new_env` / `assert_* …` / `cleanup_env`.
- **Do not reset** `PASS`/`FAIL`/`TOTAL` — they roll up into the single tally.
- Copy `tests/orchestrator.d/ABS-215-per-story-include.sh` as the template.

Run the whole suite exactly as before — the includes run automatically:

```bash
bash tests/tooling/test-orchestrator.sh
```

Two concurrent stories now add two different files → **zero shared-file
conflict**. The monolith body stays frozen; only genuinely cross-cutting edits
to existing tests still touch it.

---

## 2. Orchestrator SOP version → append a change-log line (never edit the header)

`docs/sop/ORCHESTRATOR_SOP.md` used to carry a single growing `**Version**:`
parenthetical that every story edited — the second magnet.

**Do this instead:** append **one new line** to the bottom of
[`docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md`](./ORCHESTRATOR_SOP_CHANGELOG.md) —
one ticket per line — and leave the SOP `**Version**:` header and all prior
lines untouched.

That file is marked `merge=union` in `.gitattributes`, so git's built-in
`union` driver keeps **both** sides of concurrent appends automatically: two
branches each appending their own line auto-merge with **no conflict and no
hand-resolve**. Editing an existing line or reordering defeats `union` and
re-creates the magnet — don't.

---

---

## 3. Fast test paths (test-runtime-diet)

The suite is fast now, but the **full suite stays mandatory at the QAS gate**.
The tooling below is for the inner dev loop; it never replaces the pre-merge
full run.

**Sharded orchestrator suite.** `bash tests/tooling/test-orchestrator.sh` runs its
scenario blocks across `TEST_JOBS` parallel shards (default **4**). Each shard
is a child process running a contiguous range of the body (cut only at
`cleanup_env` block boundaries, which fully tear down per-block state), with its
own `mktemp` state — no fixed paths or ports. Tallies are aggregated and any
shard's failures are reprinted in full.

Two integrity guards keep the aggregate honest (ABS-370 / ABS-525): a shard
that dies before emitting its tally is counted as an aborted-shard failure, and
the **lost-fail guard** cross-checks every shard log's visible `FAIL` verdict
lines against its tallied count — a FAIL that prints but is not tallied (for
any reason) still forces a non-green summary and exit 1. Slices are pre-cut at
dispatch time, so editing or checking out `tests/tooling/test-orchestrator.sh` while a
sharded run is in flight can no longer tear the shard slices. Corollary for
test authors: a deliberately-induced-then-rolled-back FAIL must be
print-suppressed (see the ABS-310/ABS-370 self-tests), or the guard will count
it.

```bash
bash tests/tooling/test-orchestrator.sh            # 4 shards (default)
TEST_JOBS=8 bash tests/tooling/test-orchestrator.sh
TEST_JOBS=1 bash tests/tooling/test-orchestrator.sh # exact legacy serial behaviour
```

`TEST_JOBS=1` reproduces the original serial path verbatim. Per-story
`orchestrator.d/*.sh` includes (rule 1) work unchanged under sharding.

**Parallel full-suite runner.** `bash tests/run-all.sh` runs every
`tests/tooling/test-*.sh` concurrently (`TEST_JOBS`, default 4), aggregating exit codes.
Pass explicit files to run a subset: `bash tests/run-all.sh test-claim.sh …`.

**Changed-scope selection.** `bash tests/scoped-tests.sh` runs only the tests
affected by the current diff (`git diff origin/main...HEAD` + uncommitted) plus
a mandatory smoke, via the declarative map in
[`tests/test-scope-map.txt`](../../tests/test-scope-map.txt). It is **fail-open**:
any changed path that matches no glob forces the full suite. Use it for fast
local feedback — **not** as the QAS gate.

---

**Related:** ADR-A-0014 (Integration-Gate), `rte` no-hand-resolve;
origin self-improvement 2026-07-11 (ABS-215); test-runtime-diet (sharding,
scoped tests, fixture prewarming).
