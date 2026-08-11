# SecEng bypassability review — the ABS-243 seat kill-guard

**Ticket:** ABS-244 · **Reviewed artifact:** `harness/claude/hooks/pre-bash-kill-guard.sh`
(live copy `.claude/hooks/pre-bash-kill-guard.sh`, generated mirror
`agent_providers/claude_code/hooks/`) · **Date:** 2026-07-14 · **Platform:** macOS/BSD, bash 3.2

## Verdict

> ### V0 — THE GUARD IS NOT WIRED IN THIS REPOSITORY. IT NEVER FIRES.
>
> No obfuscation is needed to bypass it, because nothing invokes it. Claude Code
> auto-loads **`.claude/settings.json`** — and that file **does not exist**: not in the
> repo, not in the worktree, not in the stable harness home (`$ORCH_HARNESS_HOME`). It is
> not gitignored and was never tracked. (`~/.claude/settings.json` does exist, but it
> carries no `hooks` key and never mentions the kill-guard.) What exists in the repo is
> `.claude/settings.template.json` — a *template*, which `harness/claude/SETUP.md:60-64`
> tells the operator to copy (`cp .claude/settings.template.json .claude/settings.json`).
> **That copy was never performed in this checkout**, so every hook command the template
> defines (15, across 6 events) is **inert** — the kill-guard, the ABS-272 stash-guard,
> the RLS guard, the push guards — along with the template's
> `permissions.deny: Bash(git stash:*)` rule, which no loaded settings file carries
> (`.claude/settings.local.json` has no `deny` key).
>
> **Proven live, not inferred.** As a seat (`ORCH_SEAT=be-developer`, `ORCH_KILL_GUARD=1`)
> I issued `pkill -f abs244-verify-decoy-nomatch-xyz` through the real Bash tool. It
> **executed** (exit 1 = `pkill` ran and matched nothing) instead of being refused
> (exit 2). A pattern that matched a real process would have killed it.
>
> The repository where the ABS-243 incident happened — where a seat reaped the
> operator's live watch-orchestrator twice — is the one where the guard built to prevent
> it does not run. Every vector below concerns the guard's *matcher*; **V0 concerns
> whether the matcher is ever consulted**, and it dominates all of them.
>
> **Remediation (one line, operator's call — deliberately NOT taken by this seat):**
> `cp .claude/settings.template.json .claude/settings.json`. It is not taken here because
> it would activate 16 hook commands mid-flight for every concurrently running seat of a
> live orchestrator run, and because whether the boilerplate itself should ship a
> committed `settings.json` (rather than a template) is an install-semantics decision
> under the ABS-94 governor-pin model — an operator/architect call, not a seat's.
> **Follow-up recommended:** an orchestrator preflight self-check that refuses to start,
> or loudly warns, when a guard hook on disk is not wired by any loaded settings file.
> A guard nobody notices is inert is worse than no guard: it is false assurance with a
> paper trail.

**Everything below assumes the guard is wired.** With that assumption, the matcher is a
**guardrail against the careless actor, not a barrier against a determined one — and it
cannot become one at the PreToolUse layer.** It does what ABS-243 built it to do (the
incident form and its near neighbours are refused, and that is the actor who caused the
incident), but a seat that *wants* to evade it can, trivially and in several independent
ways. This review says so plainly, because the main risk this artifact retires is
**false assurance**: a guard that reads like security while being a lint rule.

Two structural facts decide every vector below, and both were verified against the
tree rather than assumed:

1. **Seats run as the operator's own UID.** `git grep -nE '\b(setsid|sudo -u|runuser|unshare)\b' -- scripts/ harness/`
   returns nothing; `whoami` inside a seat is the operator (`sahan`). There is no
   privilege separation anywhere in the harness. The kernel will therefore deliver any
   signal a seat sends to any process the operator owns. **No hook can change that.**
2. **The guard is a plain file the seat may write.** `.claude/settings.local.json`
   grants seats a bare `Write` and `Edit` (and explicitly `Write(.claude/**)` /
   `Edit(.claude/**)`), and `.claude/hooks/pre-bash-kill-guard.sh` is a tracked,
   writable file. A seat can edit or delete the guard — **without ever putting a kill
   pattern on a command line.**

Given (1) and (2), hardening the string matcher against a deliberate evader is an
arms race that cannot be won at that layer. Where the technical control ends, the
**declarative rule** (`_common-rules.md` §8) is what binds — so §8 now states that
evading the guard by obfuscation is a governance violation, not a clever workaround.

## Method

Every candidate was fed to the guard through its real interface — the Claude Code
**PreToolUse stdin JSON contract** (`{"tool_input":{"command":…}}`) with the seat
markers set — and only its **exit code** was read. **No candidate command was ever
executed**, so nothing in this review could signal any process; no name-pattern kill
was run against `orchestrator.sh` (a live watch-orchestrator was running, and reaping
it is the exact incident this lineage exists to prevent). End-to-end proofs use a
**decoy** process whose command line carries the pattern, killed afterwards **by its
PID**.

Reproduce the table below on any checkout:

```bash
bash tests/probe-kill-guard-bypass.sh     # verdict per vector (evidence)
bash tests/tooling/test-kill-guard.sh             # the enforced gates (48 assertions)
```

## Vector matrix (AC1)

Verdicts are the guard's own, from the probe. "Exploitable" = a seat can reap a
process outside its spawn tree despite the guard.

| # | Vector | Verdict | Exploitable? | Disposition |
|---|--------|---------|--------------|-------------|
| **V0** | **Guard not wired** — no `.claude/settings.json` loads the hook | **NEVER FIRES** | **YES — dominant** | **Escalated to operator** (see Verdict) |
| CTL | Incident form `pkill -9 -f "scripts/orchestrator.sh --live"` (control) | BLOCKED | no | ABS-243, unchanged |
| V1 | **base64 / eval** — `eval "$(printf … \| base64 -d)"` | allowed | **YES** | **Accepted risk** (A1) |
| V2a | **Variable indirection** — `K=pki; "${K}ll" -f …` | allowed | **YES** | **Accepted risk** (A1) |
| V2b | **Quote splicing** — `p''kill -f …` | allowed | **YES** | **Accepted risk** (A1) |
| V3 | **Wrapper / indirect execution** — pattern lives in a script file, `bash cleanup.sh` | allowed | **YES** | **Accepted risk** (A2) |
| V4 | **`exec`** — `exec pkill -f …` | BLOCKED | no | Not a bypass: the kill word is still on the line |
| V5a | **Alternate kill utility** — `python3 -c "os.kill(pid, 9)"` | allowed | **YES** | **Accepted risk** (A1/A2) |
| V5b | **`ps … \| grep …` lookup feeding a kill** | **BLOCKED** | ~~yes~~ → **fixed** | **Mitigated** (M1) |
| V5c | **`ps … \| awk/sed/cut …` lookup feeding a kill** — `ps ax \| awk '{print $1}' \| xargs kill` | **BLOCKED** (since ABS-294) | ~~yes~~ → **fixed** | **Mitigated** (M1, rekeyed) — M1 as shipped keyed on the literal `grep` and covered only half its own vector class; ABS-294 rekeys it on *ps not being in `-p` PID mode*, so any filter between the lookup and the kill is covered |
| V6 | **Guard self-modification** — Edit/delete the hook or its `settings.json` wiring | n/a — never reaches the hook | **YES** | **Accepted risk** (A3) — *the strongest bypass* |
| V7 | **Kill-switch abuse** — inline `ORCH_KILL_GUARD=0 pkill -f …` | BLOCKED | no | Not a bypass — see below |
| V8 | **Broadcast kill** — `kill -9 -1` (every process of the UID) | **BLOCKED** | ~~yes~~ → **fixed** | **Mitigated** (M2) |

**V7 deserves a note, because the intuitive answer is wrong.** An inline
`ORCH_KILL_GUARD=0` prefix sets that variable for the *command being run*, not for the
*hook process* — Claude Code spawns the hook from its own environment, which the seat's
shell cannot reach. The kill switch is therefore **not** reachable from the command
line, and the guard still blocks. The switch *is* reachable by editing the settings/env
that the seat's process is launched with — but that is vector **V6**, not a separate one.

## Mitigations implemented (AC2)

Only two vectors were mitigated, and deliberately so: both sit **inside the guard's
actual threat model** (the careless seat), both are cheap and regression-free, and
neither pretends to stop a deliberate evader. The PO decision (2026-07-14T08:00:56Z)
caps any real enforcement layer out of this ticket.

**M1 — `ps … | grep …` name-lookup feeding a kill (closes V5b).** This is the same
"name lookup feeding a kill" form the guard already refuses as `pgrep … | kill`, and it
is precisely what a *well-intentioned* seat reaches for once `pkill` is refused — the
ABS-243 actor, one step later. ~~Blocked when a command carries **both** a `ps` and a
`grep` **and** a kill.~~ **Rekeyed by ABS-294 (V5c):** the `grep` literal covered only
half the vector class — `ps ax | awk '{print $1}' | xargs kill` (the classic idiom) and
the `sed`/`cut` variants sailed through. The rule is now: a `ps` invocation that is
**not** in `-p`/`--pid` mode, in a command that also carries a kill, is a name/list
lookup feeding a kill and is blocked, whatever filter sits in between.
`ps -p "$pid" >/dev/null && kill "$pid"` (a PID check, no name lookup) stays allowed.

**M2 — the broadcast kill `kill -9 -1` (closes V8).** A `-1` **target** signals *every
process the user may signal* — the operator's orchestrator included. It is strictly
worse than any name pattern, it carries no `pkill`/`pgrep`/`killall` token, and the
guard allowed it. Position decides meaning, so the rule is positional: a `-1` token
that is **not** the one directly after `kill` is a target, not a signal. `kill -1 1234`
(SIGHUP to one PID) and `kill -9 -12345` (own process group) remain allowed.

Both are covered by assertions in `tests/tooling/test-kill-guard.sh`, including an end-to-end
proof that a **decoy carrying the pattern survives** a blocked `ps|grep|kill`, plus
false-positive controls for the legitimate forms above.

**Known limits of M1/M2 (disclosed, not discovered later):**

- **M1 over-blocks one legitimate shape.** `ps aux | grep orchestrator; kill "$my_pid"`
  — an inspection followed by a *PID-scoped* kill in the same command — is refused,
  because the guard cannot tell that the `kill` argument did not come from the `grep`.
  This is a nuisance, not a hazard: the seat splits it into two commands and both pass.
  Accepted deliberately — the alternative (parsing data flow through a shell pipeline)
  is not something a PreToolUse string gate can do.
- **M2 is defeated by quoting.** `kill -9 "-1"` is allowed: the token carries literal
  quotes and does not equal `-1`. This is accepted risk class **A1**, not a defect in
  M2 — a *careless* seat does not quote `-1`, and a deliberate one has A1/A2/A3 anyway.
  Closing it would mean re-implementing the shell's quote removal, which is exactly the
  arms race this review declines to enter.
- **Neither mitigation does anything until V0 is fixed.** They are rules inside a hook
  that is currently never invoked.

## Accepted risks (AC2 — explicit, with reasoning)

> These are **not** oversights. Each is a vector the PreToolUse layer *structurally
> cannot* close, and mitigating them half-way would buy false assurance while adding
> false positives to a guard that currently does its job.

**A1 — Command-line obfuscation (V1, V2a, V2b, V5a).** The guard reads the command
string *before* the shell expands it. Any construction that assembles the kill word at
runtime (base64/eval, `${K}ll`, `p''kill`) or performs the kill in another language
(`python -c "os.kill(…)"`, `perl`, a compiled binary) presents a command line with no
pattern to match. Chasing these is unbounded: each new matcher is one shell feature away
from being defeated, while every added pattern raises the false-positive rate against
legitimate commands. **Accepted.** The binding control for these is §8 of
`_common-rules.md`, now explicit that obfuscated evasion is a governance violation.

**A2 — Indirect execution (V3, V5a).** A seat may write a script and run it; the guard
sees `bash cleanup.sh` and the pattern never appears on a command line. Closing this
would mean statically analysing the contents of every file any Bash command might
execute — i.e. re-implementing the shell. **Accepted.**

**A3 — Guard self-modification (V6) — the dominant risk.** A seat holds `Write`/`Edit`
on `.claude/hooks/pre-bash-kill-guard.sh` and its `settings.json` wiring **by explicit
grant**, and runs as the operator's UID. It can neuter the guard without ever invoking
Bash. This vector **strictly dominates every obfuscation vector above**: any effort
spent hardening the matcher is moot while the matcher itself is writable. It cannot be
fixed inside the hook — a hook cannot protect its own file from a process with write
access to it. Narrowing the seat's Write/Edit grant would be *partial* (a Bash
redirection re-opens it) and would therefore trade a known gap for a false sense of
closure. **Accepted here; escalated (see Residual).**

## #PATH_DECISION — OS-level process-group/session isolation (AC3)

**Chosen path: deferred, with the platform rationale recorded. Not built.**

- **`setsid` is unavailable.** `command -v setsid` finds nothing on this macOS/BSD
  host; it is Linux-only. Any use would be a Linux-only code path in a harness whose
  primary dev platform cannot execute or test it.
- **It would not stop an outward kill even where it exists.** `setsid` scopes a seat's
  *own* process group/session, which makes **own-group cleanup** (`pkill -g "$pgid"`)
  precise. It is not a barrier: a seat in its own session can still signal *any* process
  of the same UID. It answers "how do I kill only my children?", not "how am I prevented
  from killing yours?" — and the latter is this ticket's question.
- **Alternatives considered:**
  - *`setsid` behind a platform check* — rejected: Linux-only, untestable here, and per
    the point above it does not close the vector; it would be observability theatre.
  - *A `nohup`/`disown`-based approximation on BSD* — rejected: same non-property. It
    changes signal *delivery on hangup*, not *authority to signal*.
  - *Privilege separation (separate UID / container / sandboxed seat execution)* — the
    only mechanism that actually closes A1–A3, because it removes the UID equality that
    makes them possible. **Out of scope by PO decision and by guardrail (see Residual).**

## Residual risk and recommendation

**First, in priority order: wire the guard (V0).** Nothing else in this review changes
any outcome until `.claude/settings.json` exists and loads the hook. The remediation is
one line; the decisions attached to it (activate mid-run? ship a committed
`settings.json` with the boilerplate? add an orchestrator preflight self-check?) belong
to the operator and the System Architect, and are stated in the Verdict above.

**Second, the long-term control. The durable one is OS-level privilege separation — running seats under a
different UID or in a sandbox/container that cannot signal the operator's processes.**
It is the only layer at which A1, A2 and A3 all fail closed, because it removes the
shared-UID premise rather than pattern-matching its symptoms.

Per ADR-A-0004 and the PO decision on this ticket, that is **an architectural decision
and plausibly a new capability — it is NOT built here.** It is routed to the **System
Architect as an ADR authoring request** (Trigger b); if it constitutes a new capability
it is **human-only** and escalates to the POPM as a proposal. This review makes no
change to how seats are launched.

Until then the posture is, honestly stated:

- **Careless actor (the ABS-243 incident): mechanically blocked**, now including the two
  forms a blocked seat would naturally try next (M1, M2).
- **Deliberate evader: not blocked, and not blockable at this layer.** Governed by
  §8 of `_common-rules.md` and by review, not by the hook.

## Parity: kill switch and observability (AC4)

The mitigations are new *rules inside the existing guard*, not a new layer, so they
inherit its contract by construction — and this is asserted, not assumed:

- **Kill switch (ABS-111):** `ORCH_KILL_GUARD=0` restores legacy behavior for both new
  rules (the switch short-circuits before any matching), and a **human shell** (no
  `ORCH_SEAT` marker) is never guarded. Both tested.
- **Observability (ABS-66):** every block is appended to `ORCH_KILL_GUARD_LOG` with a UTC
  timestamp, seat identity, the matched form (`matched=ps|grep|kill`, `matched=kill -1`)
  and the offending command, and echoed to stderr for the seat. Both tested.

## Evidence

| Claim | Evidence |
|---|---|
| **V0: the guard never fires here** | Live seat Bash call `pkill -f abs244-verify-decoy-nomatch-xyz` → **exit 1 (executed)**, not exit 2 (refused) |
| **V0: no settings file loads the hook** | `.claude/settings.json` absent in repo, worktree, and `$ORCH_HARNESS_HOME`; `git check-ignore` → not ignored; `git log -- .claude/settings.json` → never tracked; `.claude/settings.local.json` → no `.hooks` key, no `deny` key; `~/.claude/settings.json` → `has("hooks")` = `false` |
| **V0: the copy step exists and was skipped** | `harness/claude/SETUP.md:60-64` — "Claude Code **auto-loads** `.claude/settings.json`" + `cp .claude/settings.template.json .claude/settings.json` |
| V0 reproducible | `bash tests/probe-kill-guard-bypass.sh` → prints `NOT WIRED` |
| Vector verdicts (V1–V8) | `bash tests/probe-kill-guard-bypass.sh` |
| Mitigations enforced, no regression | `bash tests/tooling/test-kill-guard.sh` → **48 passed, 0 failed** (was 31 before ABS-244) |
| ABS-243 behavior unchanged | Same suite: incident form, signal-flag variant, compound clause, `killall`, `xargs kill` all still BLOCKED; PID/`-P`/`-g`/`-s` kills still allowed |
| Adjacent guard unaffected | `bash tests/tooling/test-local-main-guard.sh` → ALL TESTS PASSED |
| No privilege separation exists | `git grep -nE '\b(setsid\|sudo -u\|runuser\|unshare)\b' -- scripts/ harness/` → no hits |
| `setsid` unavailable | `command -v setsid` → not found (macOS/BSD) |
| Guard file is seat-writable | `.claude/settings.local.json` allow-list contains `Write`, `Edit`, `Write(.claude/**)`, `Edit(.claude/**)` |
| Hook parity | `scripts/generate-governor.sh --providers --check` → OK |
| Lint | `bash -n` + `shellcheck -S warning` clean on guard, probe, and test |
