# Commit-Tag Guard SOP (PILOT-79)

**Audience:** seat implementers, operators, RTE.

---

## What the guard does

`scripts/hooks/commit-msg-ticket-tag-guard.sh` (installed via
`provision_ticket_tag_guard` in `scripts/orchestrator.sh`) aborts a seat commit
on a story branch when the commit message is missing its `[PREFIX-XXX]` ticket
tag.

**Why this matters.** The RTE Epic-Integration seat git-bisects the epic branch
on a smoke failure and maps the culprit commit to its story via the
`[PREFIX-XXX]` tag (rte.md step 6). An untagged commit that reaches the epic
branch routes the whole epic to `Needs PO Decision` — a status with no edge back
to the merge path. CONTRIBUTING.md declared the tag required, but nothing
enforced it until PILOT-79. Real occurrence: `epic/PILOT-58` commit `4d70ec09`
carried its ticket only in prose, not as `[PILOT-66]`.

The tag format is prefix-agnostic (`[A-Z][A-Z0-9]*-<digits>`): it matches
PILOT-*, ABS-*, and any consumer key — no `AITBC` baked in.

---

## Two commit classes

Not every commit has a ticket. The guard enforces the tag **only on story
commits**; operator/release commits are exempt by design:

| Class | Tag | Recognised by |
| ----- | --- | ------------- |
| (a) Seat / story commit | **required** | on a `<ticket>-auto` branch with seat env vars set |
| (b) Operator / release commit | not required | subject `chore(release):` / `chore(governor):`, or `[no-ticket]` |

Protected branches (`main`, `master`) and `epic/*` integration branches are
operator/RTE territory and are never guarded. Human commits outside a seat
context (no `ORCH_*` env marker) are never blocked.

---

## Opting out with `[no-ticket]`

When an operator needs to commit something genuinely ticketless on a story
branch (a `HARNESS_CHANGELOG` entry, a docs afterthought), add `[no-ticket]`
anywhere in the message body:

```
chore(docs): add harness changelog entry [no-ticket]
```

This makes the exemption explicit and greppable rather than silently untagged.

---

## Kill switch

`ORCH_TICKET_TAG_GUARD=0` disables the guard for the current spawn. The
installer (`provision_ticket_tag_guard`) also skips installation and removes any
existing hook when the switch is off. Operator-only; do not set it in seat code.

---

## Bisect recovery (RTE, AC5)

When a smoke failure bisect lands on a culprit with no ticket tag, RTE step 6
runs `scripts/commit-tag-guard.sh recover <range> <culprit-sha>` before
resorting to `Needs PO Decision`:

1. Culprit is tagged → maps to that story directly.
2. Nearest tagged commit between culprit and branch tip → maps to that story.
3. Enclosing merge commit that brought the culprit in → maps via the merge.
4. None of the above → `unresolved` (exit 3) → RTE falls back to `Needs PO
   Decision` as last resort.

`Needs PO Decision` is therefore the last resort when recovery finds no path,
not the first response to a missing tag.

---

## Classifier subcommands

`scripts/commit-tag-guard.sh` provides a stable contract used by tests and RTE:

| Subcommand | Input | Output / exit |
| ---------- | ----- | ------------- |
| `verdict <sha>` | one commit SHA | `tagged <ID>` / `exempt <reason>` / `untagged`; 0 or 1 |
| `check-msg <file>` | commit-msg file path | same verdict/exit contract |
| `check-range <range>` | git range (`good..bad`) | offenders listed; exit 1 if any |
| `recover <range> <sha>` | range + culprit SHA | `child=<ID> via=...` or `unresolved`; 0, 3, or 64 |

Exit codes: 0 = tagged/exempt; 1 = at least one untagged story commit; 3 =
`recover` found no resolution; 64 = usage error.

---

## Running the test suite

```bash
bash tests/test-commit-tag-guard.sh
# 25 assertions: AC1-AC5 (tagged pass, untagged fail, release exempt,
# [no-ticket] exempt, recover subcommand, kill switch)
```

All 25 assertions must pass. Regression both ways is verified: a tagged story
commit exits 0, an untagged story commit exits 1, a `chore(release):` commit
exits 0.

---

## Related files

| File | Role |
| ---- | ---- |
| `scripts/commit-tag-guard.sh` | prefix-agnostic classifier + recover subcommand |
| `scripts/hooks/commit-msg-ticket-tag-guard.sh` | git commit-msg hook |
| `scripts/orchestrator.sh` (`provision_ticket_tag_guard`) | installs hook at startup |
| `tests/test-commit-tag-guard.sh` | 25-assertion regression suite |
| `CONTRIBUTING.md` §"Exempt commits" | human-readable two-class table |
| `harness/claude/agents/rte.md` step 6 | bisect recovery procedure |
