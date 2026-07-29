# Windows Spawn Argv-Size Gate Guide

**Shipped in**: ABS-251 (epic ABS-245, boilerplate v2.25.0)

On Windows, `CreateProcess` caps the entire command line at approximately 32 KB.
The orchestrator's spawn seam passes each agent def inline via `--agents`, so any
role whose definition exceeds the gate crashes instantly — before the Claude CLI
even starts. The consumer-reported reproduction: the `system-architect` def at
37.6 KB killed every spawn of that role on Windows.

ABS-251 adds a configurable byte-count gate (`ORCH_AGENTS_ARG_MAX`, default
24 000 bytes). Above the gate the seam drops the inline `--agents` and, since
PILOT-23, **materializes the same composed + rewritten def** (ABS-535 skill-path
rewrite + ABS-174 commons prepend) as a markdown def under a throwaway
`--plugin-dir`, selected by a unique `--agent <role>__seat`. The big def content
travels in a *file*, so the command line stays tiny (Windows-safe) while the seat
material is byte-for-byte the same rewritten def the inline path would emit. macOS
and Linux are unaffected: today's defs stay under the default gate so the
command-line sequence is byte-identical to before.

> **Pre-PILOT-23 behavior (superseded):** the fallback used to pass a bare
> `--agent <role>`, letting the CLI load the role's *un-rewritten* on-disk def
> from `.claude/agents/`. That skipped both the ABS-535 skill-path rewrite and the
> ABS-174 commons prepend, so any role def large enough to trip the gate
> (`be-developer`, `po-agent`, `tech-writer`) stayed SESSION-POISONED on
> skill-file permission denials even after the ABS-535 fix landed.

---

## When This Applies

- You run the orchestrator on **Windows** and at least one role's def is large
  (composite defs with embedded patterns, or the `system-architect` / `be-developer`
  roles in a heavily customized project).
- You want to **force the fallback** for testing or benchmarking (lower the gate).
- You want to **disable the gate** to always use inline `--agents` (raise the gate).

---

## How It Works

At spawn time, after the seam assembles the `--agents` JSON, it checks the byte
length against the gate:

```
if byte-length(AGENTS_JSON) > ORCH_AGENTS_ARG_MAX (default 24000):
    omit --agents
    materialize composed+rewritten def -> $TMP/agents/<role>.md   # same rewrite as inline
    pass  --plugin-dir <tmp>        # CLI loads the def from the file (not argv)
    pass  --agent <role>__seat      # unique name so a same-named project agent cannot shadow it
    apply tool-narrowing if needed  # see below
else:
    pass  --agents <JSON>           # unchanged path (byte-identical on macOS/Linux)
    pass  --agent <role>
```

The fallback is announced on `stderr` so the orchestrator can observe it:

```
spawn-claude: NOTICE --agents JSON is 38521B > ORCH_AGENTS_ARG_MAX (24000B)
              -> falling back to a plugin-materialized def for --agent system-architect
```

### Tool-Narrowing Parity (AC2)

When a runner-supplied `ORCH_TOOLS` override is write-free (e.g. a reviewer seat
restricted to `Read, Bash`), the seam appends
`--disallowedTools Write,Edit,NotebookEdit` to the fallback invocation. The
materialized def already carries the resolved (override-or-frontmatter) `tools:`
list, so this is belt-and-suspenders; it also stays a hard backstop against a
seat the runner deliberately locked down being silently re-granted write access.

| `ORCH_TOOLS` value | Fallback behavior |
|--------------------|-------------------|
| *(unset)* | No `--disallowedTools` — the on-disk `tools:` frontmatter equals what the inline JSON would have carried. |
| Contains `Write` or `Edit` | No `--disallowedTools` — the override grants writes; nothing to narrow. |
| Set but write-free (e.g. `"Read, Bash"`) | `--disallowedTools Write,Edit,NotebookEdit` added — seat stays read-only. |

---

## Configuration

Set `ORCH_AGENTS_ARG_MAX` in the environment before running the orchestrator.

```bash
# Default — 24 000 bytes (well under Windows' ~32 KB limit, conservative headroom).
# No action needed if you are happy with the default.
export ORCH_AGENTS_ARG_MAX=24000

# Disable the gate entirely (always pass inline --agents, Windows users on their own).
export ORCH_AGENTS_ARG_MAX=999999

# Force the fallback for every role (useful for testing the on-disk path on any OS).
export ORCH_AGENTS_ARG_MAX=10
```

The variable is documented in the spawn-seam header (`scripts/orchestrator-spawn-claude.sh`,
`ORCH_AGENTS_ARG_MAX` block).

---

## Known Limitations

1. **ABS-174 commons prepending and the ABS-535 skill-path rewrite now DO apply
   on the fallback path (PILOT-23).** The original ABS-251 fallback loaded the
   raw on-disk def and so skipped both — the accepted-but-poisoning trade-off
   documented here before. PILOT-23 replaced that with a plugin-materialized def
   built by the same composer as the inline path, so the fallback seat is no
   longer degraded: it gets the commons, the rewritten skill paths, and the
   Read-allowlist for the live skills dir, exactly like the inline path.

2. **`Bash` is not narrowed.**
   The `--disallowedTools` narrowing covers `Write`, `Edit`, and `NotebookEdit`
   — the file-mutation tools. `Bash` remains as defined in the on-disk def.
   This matches realistic reviewer toolsets (a read-only reviewer still needs
   `Bash` for read commands) and the consumer fix scope.

---

## Troubleshooting

### Spawn dies immediately on Windows with a large def

**Symptom**: The orchestrator reports a spawn failure; no Claude output. The role
def is over 24 KB (check with `wc -c .claude/agents/<role>.md`).

**Fix**: The gate is active by default in v2.25.0+. If you are on an older
version, upgrade or patch `scripts/orchestrator-spawn-claude.sh` from ABS-251
(`feat(orchestrator): argv-size-gated --agent fallback for large defs [ABS-251]`).

### A read-only seat gained write access after a Windows fallback

**Symptom**: A reviewer or QAS seat wrote files it should not have been able to.

**Diagnosis**: Check whether `ORCH_TOOLS` was set to a write-free value at spawn
time. The tool-narrowing only fires when `ORCH_TOOLS` is present and write-free.
If `ORCH_TOOLS` was unset, the on-disk def's `tools:` frontmatter governs — and
if that frontmatter grants writes, the seam leaves it alone (it equals what the
inline JSON would have carried for an unoverridden spawn).

### Fallback notice appears on macOS/Linux

**Symptom**: You see the `ORCH_AGENTS_ARG_MAX` NOTICE on macOS or Linux.

**Explanation**: A def has grown past the gate value. Either the def was recently
expanded or `ORCH_AGENTS_ARG_MAX` was set lower than usual. Since PILOT-23 the
fallback is functionally equivalent to the inline path (same rewritten def, same
commons, same Read-allowlist), so the notice is informational — no action needed.
Raise the gate (`export ORCH_AGENTS_ARG_MAX=999999`) if you nonetheless prefer the
inline path.
