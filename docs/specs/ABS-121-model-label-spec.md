# ABS-121 Design Spec — Per-Ticket Model Label + Runner Precedence Chain

**Ticket**: ABS-121 (epic ABS-114) · **Status**: accepted (all decisions operator-fixed in the
refinement — precedence, ownership, haiku criteria; implementation is mechanical, no open
`#PATH_DECISION`, no separate architect round) · **Date**: 2026-07-07

## 1. Label + precedence

`model:<sonnet|opus|haiku>` ticket label (sibling of the `role:` convention, ABS-36 §2.2; a Jira
label — colons are valid there, and the mock adapter's label charset was extended to match so it
can represent the convention). Runner resolution in `run_spawn_cmd` (`resolve_model_label`):

```
ORCH_MODEL_<ROLE> / ORCH_MODEL env  >  ticket label  >  role frontmatter  >  CLI default
```

Operator-decided (revised from the draft): the ENV is the emergency lever ("alles auf sonnet,
Quota knapp") and always wins; the label is the informed per-ticket normal case; the frontmatter
(incl. the ABS-120 sonnet defaults) is the role fallback, resolved inside the spawn seam as
before. Label use logs `MODEL-LABEL`; an invalid value (e.g. `model:gpt5`) logs
`WARN-MODEL-LABEL` and falls through to the next level — never a crash. The seam's Sonnet-4.6 pin
applies after resolution regardless of source.

## 2. Ownership + sizing rule

BSA primary, enrichment fallback: the BSA decomposition assigns the label where complexity is
known (guidance in `bsa.md`); the issue-enrichment gate adds it for unlabelled tickets
(Path-A/parentless, manual) per the sizing rule documented in `issue-enrichment.md` (both
namespaces): opus = architecture-heavy, sonnet = mechanical implementation default, haiku =
trivial-only (one-line docs/label fixes; never a default; when in doubt, sonnet).

## 3. Tests (tests/test-orchestrator.sh, ABS-121 section)

label reaches the seat without env; `ORCH_MODEL_<ROLE>` beats the label; no label + no env →
frontmatter fallback (runner passes nothing); invalid label → WARN + ignored + spawn proceeds.
The ABS-120 cost report shows post-hoc whether the sizing was right.
