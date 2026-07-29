# ABS-193 — Root-Cause: `./` path-prefix Bash-allowlist denial on the tracker adapter

- **Type**: Follow-up hardening (origin: operator follow-up on ABS-163, live-run ABS-181)
- **Seat**: be-developer (headless)
- **Date**: 2026-07-10
- **Flag**: security (touches the Bash allowlist / permission surface)
- **Status**: Root-caused + durable committed fix shipped (this ticket)

---

## TL;DR

A **restrictive main-checkout** seat (one whose `.claude/settings.local.json`
pins the tracker adapter to a *literal-path* Bash rule rather than a bare `Bash`
grant) is **permission-denied** when it invokes the adapter with a **`./`
prefix** — `./scripts/jira-tracker.sh …`. The Claude Code permission matcher
keys on the **exact command prefix**: `Bash(scripts/jira-tracker.sh:*)` and
`Bash(/abs/path/scripts/jira-tracker.sh:*)` match the bare-relative and absolute
literals, but `./scripts/jira-tracker.sh` is a **different literal prefix** and
matches **neither** → denied under `--permission-mode dontAsk` (silent, no
prompt).

This is a **distinct, still-open denial class** from the two already fixed:

| Denial class | Trigger | Fixed by |
|---|---|---|
| redirection-char | `<` / `>` in comment/reason text | ABS-163 `--body-file` / `--reason-file` |
| variable-call form | `"$TRACKER_CMD" …` (unexpanded) vs literal allowlist | ABS-180 (packet carries the resolved literal + duty-note) |
| **path-prefix (`./`)** | **`./scripts/…` vs bare/abs literal allowlist** | **ABS-193 (this ticket)** |

In live-run ABS-181 this class denied a WRITE op and drove the issue-enrichment
seat to RESPAWN-LIMIT even though ABS-163 had removed the redirection-char class.

---

## 1. Why the `./` form is denied (which patterns match, which do not)

The Claude Code Bash permission matcher (`Bash(<prefix>:*)`) does a **literal
command-prefix** match on the command string, **not** a filesystem-path
resolution. `./scripts/jira-tracker.sh` and `scripts/jira-tracker.sh` resolve to
the **same file** on disk, but they are **different command strings**, so they
need **different allow rules**.

| Command string the seat runs | Allowlist entry that would match | Restrictive checkout has it? | Result |
|---|---|---|---|
| `scripts/jira-tracker.sh transition …` | `Bash(scripts/jira-tracker.sh:*)` | yes | **allowed** |
| `/Users/…/scripts/jira-tracker.sh transition …` | `Bash(/Users/…/scripts/jira-tracker.sh:*)` | yes | **allowed** |
| `./scripts/jira-tracker.sh transition …` | `Bash(./scripts/jira-tracker.sh:*)` | **no** | **DENIED** |

Under `--permission-mode dontAsk` an unmatched Bash call is **silently denied**
(no prompt) — so the seat's WRITE (comment / transition) simply drops, and the
runner sees no gate comment / no exit transition → RESPAWN-LIMIT.

### Where the `./` comes from

The default and documented binding uses a **relative** adapter path
(`export TRACKER_CMD=scripts/jira-tracker.sh`, ORCHESTRATOR_SOP §"Jira Cloud
Binding"). `build_packet` writes that resolved literal into the packet header
(`tracker_cmd: scripts/jira-tracker.sh`, ABS-180). A seat, treating it as a
"local script", naturally prepends `./` to run it — the idiomatic shell spelling
for invoking a script in the current directory — and lands on the denied prefix.
(In production with an **absolute** `TRACKER_CMD` a verbatim copy already avoids
`./`; the exposure is the relative-path binding.)

---

## 2. The durable committed fix (not operator-local)

Two complementary, minimal changes — belt-and-suspenders, each tiny:

### Fix A (primary — stop seats emitting `./`): packet duty-note

`scripts/orchestrator.sh` `build_packet()` — the packet header duty-note now
pins the **path form**, not only the identity of the adapter:

> `use tracker_cmd above … invoked VERBATIM as printed — do NOT prepend ./ and do
> NOT wrap it in bash (the Bash allowlist matches the exact path, not a
> ./-prefixed form, so ./scripts/... is denied under --permission-mode dontAsk); …`

A seat that copies the packet's literal verbatim never emits the denied form.
This is the same lever ABS-180 used (the packet header is the single source seats
are told to trust), extended one clause. Durable: committed in the runner, rides
every spawn packet, no operator action.

### Fix B (defense-in-depth for relative `TRACKER_CMD`): SOP allowlist baseline

`docs/sop/ORCHESTRATOR_SOP.md` §"Live-Run Allowlist Baseline" now documents that a
restrictive main-checkout allowlist which pins the adapter to a literal path must
seed **both** spellings — the bare-relative literal **and** the `./`-prefixed
variant (for `jira-tracker.sh` and `mock-tracker.sh`) — or use a bare `Bash`
grant (the ABS-154 worktree default already sidesteps the whole path-form
question). Operators seed this from the committed SOP, not from a gitignored
`settings.local.json` stopgap.

### Why AC #6 (minimal, justified widening) holds

Fix A widens nothing — it is prompt wording. Fix B's documented widening grants
**only the same adapter script under an equivalent path spelling**; it adds **no
new command surface** and crosses **no** human-only boundary (ADR-A-0004). A bare
`Bash` grant needs none of it.

---

## 3. Regression coverage

`tests/test-orchestrator.sh`, ABS-180 packet-header block, two new assertions:

- `invoked VERBATIM as printed` — the duty-note pins verbatim invocation.
- `do NOT prepend ./` — the duty-note forbids the `./`-prefixed form.

Green in the full suite (see §5 of the handoff). These exercise the real
`build_packet` output captured via `STUB_PACKET_COPY`, the same harness ABS-180
uses — so the note that ships in every live packet is what is asserted.

---

## 4. Scope boundaries (from the ticket)

**Out of scope** (unchanged here): redirection-char denials (ABS-163), the
operator-local `settings.local.json` stopgap, permission-model redesign, and any
human-only boundary.

---

## References

- Origin: operator follow-up on ABS-163 (2026-07-09); live-run ABS-181
  (enrichment seat → RESPAWN-LIMIT).
- Related: ABS-180 (packet carries resolved `tracker_cmd` + duty-note),
  ABS-163 (`--body-file`/`--reason-file`), ABS-154 (worktree bare-`Bash`
  default), ABS-134 (`docs/agent-outputs/ABS-134-bash-denial-analysis.md`).
- Code: `scripts/orchestrator.sh` `build_packet()`;
  `docs/sop/ORCHESTRATOR_SOP.md` §"Live-Run Allowlist Baseline";
  `tests/test-orchestrator.sh` ABS-180 block.
