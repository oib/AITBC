---
id: ADR-A-0028
title: Rule ledger — every normative instruction-surface rule has a sensor or a declared risk
status: accepted
accepted_by: Raphael Sahann (POPM)
accepted_date: "2026-07-21"
scope: agentic
date: "2026-07-21"
---

## Context

The RULES-carrying markdown surface (AGENTS.md, CLAUDE.md, `docs/sop/`, `adrs/agentic/`,
agent defs, gate skills — ~17k lines) states rules that only an LLM interprets. Every
documented md-misread incident (gates run after dispatch, Done with an open PR, ADR
frontmatter drift, station skip ABS-492, respawn churn ABS-494) came from the subset of
that surface with no deterministic sensor. The survey "Code as Agent Harness"
(arXiv 2605.18747) names the underlying principle: natural-language guidance is a valid
contract layer, but control must not rest on NL alone — reliability comes from
executable, inspectable enforcement. The repo already practices governed harness
mutation (incident → improvement proposal → gate script + `tests/test-*.sh`); what is
missing is systematics: nobody can say which rule has a sensor and which does not.

## Decision

We will maintain `docs/rule-ledger.yaml` as the machine-readable inventory of the
instruction surface, checked by `scripts/rule-ledger-check.sh` (auto-discovered via
`tests/test-rule-ledger.sh`), with these invariants:

1. Every H2/H3 section of every scoped RULES file has one ledger row per occurrence
   declaring `enforced`, `derived`, `unenforced`, or `informative`. A new section or a
   new file under a `scope_dirs:` directory without ledger rows is a CI failure.
2. `enforced` and `derived` rows name at least one existing deterministic sensor
   (test, guard/lint script, hook, CI workflow, or `scripts/<file>:<function>` gate).
   Honest semantics: the checker verifies sensor EXISTENCE; wiredness is pinned by the
   sensor's own test.
3. `unenforced` rows carry a non-empty risk note — the sensor-backfill worklist is the
   set of unenforced rows, reported as an absolute count.
4. Nothing is removed from RULES markdown unless its section has a sensor-covered
   (`enforced`/`derived`) ledger row (condensation precondition, ABS-524).
5. Anchoring is (file, heading) at section level — no IDs injected into markdown, no
   sentence-level rule DSL (ADR-A-0010). Ledger ids `R-NNNN` are append-only.

Deliberately unenforced rules remain legitimate — human-boundary rules (ADR-A-0004)
are declared with a risk note instead of getting an auto-sensor.

## Consequences

The enforced/unenforced balance of the instruction surface becomes a measurable,
CI-guarded property instead of folklore. Authors of new SOP rules must decide at
writing time whether the rule gets a sensor or a declared risk. Heading renames touch
the ledger (intended: an anchor change is a reviewable event). The ledger inventories
`work/.orchestrator*` marker classes (ABS-522) but their typed-state migration stays
owned by ADR-A-0026 / ABS-229.

## Related Decisions

- ADR-A-0004 — human-approval boundaries (deliberately unenforced rows)
- ADR-A-0010 — minimal-change default (section-level anchoring, no DSL)
- ADR-A-0026 — first-class orchestration state (typed-state substrate)
