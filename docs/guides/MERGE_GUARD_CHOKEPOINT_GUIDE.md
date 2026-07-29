# Merge Chokepoint Guard (PILOT-11 / ABS-513)

**Audience:** operators configuring the harness, implementers writing merge
logic, and anyone who needs to understand why `bb pr merge` / `glab mr merge`
can be blocked.

---

## Background

PILOT-10 shipped `scripts/merge-target-guard.sh`: a script that decides whether
a merge target is on the protected-branch list. PILOT-10 wired it in only as
prose in the RTE duty-step. On 2026-07-21 (v3-Pilot #2), an RTE seat ran
`glab mr merge 150` onto `main` without executing that step (MR !150). A rule
a seat can skip is not enforcement.

PILOT-11 closes the defect class by adding a PreToolUse Bash hook
(`harness/claude/hooks/pre-bash-merge-guard.sh`) that calls the guard on every
`bb pr merge` / `glab mr merge` before the command reaches the git host,
independent of whether the seat ran the duty-step.

---

## How it works

1. The Claude Code Bash PreToolUse hook reads every Bash command from the
   `stdin` JSON payload.
2. All commands that are not `bb pr merge` or `glab mr merge` pass through
   untouched.
3. For a merge command, the hook resolves the MR/PR **target branch** (see
   [Target resolution](#target-resolution) below).
4. It calls `bash scripts/merge-target-guard.sh check <target>`:
   - Exit 0 (ALLOW, e.g. `epic/*`): hook exits 0; the merge proceeds.
   - Exit 1 (REFUSE, target is `main` or any `ORCH_PROTECTED_BRANCHES` entry):
     hook exits 2 (tool blocked). The guard's `MERGE-GUARD-REFUSE …
     action=hitl-handoff` intent line surfaces on `stderr` and appends to the
     guard log. The merge never runs.
   - Unresolvable target: hook exits 2 (fails closed). Hand off to HITL.
5. The hook fires only inside orchestrator seats. A human's interactive shell
   carries none of the `ORCH_SEAT` / `ORCH_TICKET` / `ORCH_ROLE` markers and
   is never guarded.

---

## Target resolution

The MR/PR target branch is a server-side property. The hook resolves it in
this order:

| Priority | Source | Typical use |
| --- | --- | --- |
| 1 | `$ORCH_MERGE_GUARD_TARGET_CMD <id>` (prints target) | Test seam; operator override |
| 2 | `glab mr view <id> -F json` | GitLab |
| 2 | `bb pr view <id> --json` | Bitbucket |

If neither path yields a target, the hook fails closed (exit 2).

---

## Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `ORCH_MERGE_GUARD` | `1` | Set to `0` to disable the chokepoint (restores unguarded merges) |
| `ORCH_MERGE_GUARD_TARGET_CMD` | _(unset)_ | Override resolver; must print the target branch given an MR/PR id |
| `ORCH_MERGE_GUARD_LOG` | `$TMPDIR/orchestrator-merge-guard.log` | Audit log; each blocked merge appends one line |
| `ORCH_PROTECTED_BRANCHES` | `main master` | Protected branch set, read by `scripts/merge-target-guard.sh` |

`ORCH_MERGE_GUARD` follows the ABS-111 kill-switch pattern: it is declared in
`scripts/orchestrator.sh` and documented in the Environment Knobs table of
`docs/sop/ORCHESTRATOR_SOP.md`.

---

## What a seat sees when blocked

```
❌ BLOCKED (PILOT-11 merge-guard): glab mr merge refused before it reached the git host.
  MERGE-GUARD-REFUSE action=hitl-handoff
  Reason:   merge-target-guard REFUSED: target 'main' is protected.
  Command:  glab mr merge 150 --yes
  A seat may NEVER merge onto a protected branch (main / ORCH_PROTECTED_BRANCHES);
  auto-merge is legitimate ONLY onto an epic integration branch (ADR-A-0014), and
  the human-merge boundary (ADR-A-0004/0005) is not a seat's to cross. Hand off to
  HITL for this merge.
  Override (operator only): ORCH_MERGE_GUARD=0
  Logged to: /tmp/orchestrator-merge-guard.log
```

The seat posts the `MERGE-GUARD-REFUSE … action=hitl-handoff` line as a
`gate-results` comment and hands off to HITL. The seat must not set
`ORCH_MERGE_GUARD=0` — the override is for operator use only.

---

## RTE duty-step 4 (updated by PILOT-11)

`harness/claude/agents/rte.md` duty-step 4 was reworded from
`check "$EPIC_BRANCH"` to `check "<the ACTUAL MR target branch>"`. An empty
`$EPIC_BRANCH` (the epic-less lane) exits 64 (usage error), not the clean
`MERGE-GUARD-REFUSE` intent line. The step now explicitly instructs the RTE to
pass `main` in the epic-less lane.

The updated guidance in `docs/sop/rte-reference.md`:

> `scripts/merge-target-guard.sh check "<the ACTUAL MR target branch>"` —
> Pass the real branch the MR is opened against, never a hard-coded slug.
> This is also enforced mechanically by `.claude/hooks/pre-bash-merge-guard.sh`
> (PILOT-11), which blocks a protected-branch merge even if this step is skipped.

---

## Conformance test

```bash
# Run from the repo root — must be 16/16.
bash tests/test-merge-guard-chokepoint.sh
```

The suite injects `ORCH_MERGE_GUARD_TARGET_CMD` as a stub resolver; no live
forge connection is needed. Coverage: skip-path block to `main`; the MR !150
exact command form (`glab mr merge 150`); both forge variants; epic-branch
allow; knob invariance (`ORCH_AUTOMERGE` 1/0/unset all refuse `main`); scope
(non-merge commands pass); fail-closed on unresolvable target; kill-switch off.

The PILOT-10 regression suite also remains in CI:

```bash
bash tests/test-merge-target-guard.sh   # must be 15/15
```

---

## Troubleshooting

**Seat logs "hooks: jq not found; skipping merge-guard" and the merge runs.**
The hook fails open when `jq` is absent. Install `jq` on the seat's machine.
Without `jq` the hook cannot read the command from the payload and cannot guard.

**A legitimate `epic/*` merge is blocked.**
Verify the MR's target branch on the forge is an `epic/` branch, not a personal
branch. If `glab mr view <id>` or `bb pr view <id>` returns an unexpected value,
set `ORCH_MERGE_GUARD_TARGET_CMD` to a resolver that prints the correct target.

**Operator needs to bypass the guard in an emergency.**
Set `ORCH_MERGE_GUARD=0` in the seat's launch environment. Log the reason.
The operator's own interactive shell is never guarded; this knob only applies
to orchestrator seats.

---

## Related

- `scripts/merge-target-guard.sh` — the guard decision script (PILOT-10).
- `harness/claude/hooks/pre-bash-merge-guard.sh` — this chokepoint (PILOT-11).
- `tests/test-merge-guard-chokepoint.sh` — chokepoint conformance suite.
- `tests/test-merge-target-guard.sh` — guard decision regression suite.
- `docs/sop/rte-reference.md` — RTE duty-step 4 copy-paste templates.
- `docs/sop/ORCHESTRATOR_SOP.md` — `ORCH_MERGE_GUARD` knob row.
- ADR-A-0004, ADR-A-0005 (human-merge boundary); ADR-A-0014 (epic-branch
  auto-merge).
