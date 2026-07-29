---
name: spec-creation
description: Spec creation with pattern references, acceptance criteria, and demo scripts. Use when creating implementation specs, defining acceptance criteria, or breaking down user stories.
---

# Spec Creation Skill

## Purpose

Guide spec creation with clear acceptance criteria, pattern references, and testable success validation.

## When This Skill Applies

- Creating implementation specs
- Breaking down user stories
- Defining acceptance criteria
- Translating business requirements to technical specs

## Spec Template (MANDATORY)

```markdown
# SPEC-AITBC-{number}: {Feature Name}

## Summary
{One paragraph describing the feature}

## User Story
As a [user type], I want [goal] so that [benefit].

## Acceptance Criteria
- [ ] {Testable criterion 1}
- [ ] {Testable criterion 2}
- [ ] {Testable criterion 3}

## Pattern References
- **UI**: `patterns_library/ui/{pattern}.md`
- **API**: `patterns_library/api/{pattern}.md`
- **Database**: `patterns_library/database/{pattern}.md`

## Success Validation Command
```bash
{validation command}
```

## Demo Script
1. Navigate to {page}
2. Click {button}
3. Observe {expected behavior}

## Logical Commits
1. `feat(scope): implement data model [AITBC-{number}]`
2. `feat(scope): add API endpoint [AITBC-{number}]`
3. `feat(scope): create UI component [AITBC-{number}]`
```

## Acceptance Criteria Patterns

```markdown
# User Actions
- [ ] User can {action} → {result}

# Data
- [ ] Data persists after {action}
- [ ] User can only see their own {data type}

# Errors
- [ ] Invalid input shows {error message}
```

## AC Coverage Rules (MANDATORY)

The gates verify exactly the acceptance criteria — anything verified only by
reading is not verified.

**Rule 1 — Executed AC for procedural deliverables**: every ticket that
defines a procedure an agent will follow (charter, SOP section, workflow)
MUST include at least one AC that EXECUTES the procedure's command sequence
and asserts its postcondition — even a cheap non-LLM simulation (bash the
charter's adapter commands against the mock tracker). Grep-only ACs are
insufficient for procedural deliverables.

Worked example (the ABS-60 gap): the decomposition charter's `create` command
could not persist the enriched child body (children stayed `_TBD_`); every AC
was a grep or suite run, so all gates passed the broken procedure. The
executed AC that catches it in seconds:

```bash
BODY_FILE="$(mktemp)"
printf '# Simulated child\n\nEnriched body.\n' > "$BODY_FILE"
CHILD=$(scripts/mock-tracker.sh create --type ticket \
  --title "Executed-AC simulation" --body-file "$BODY_FILE")
scripts/mock-tracker.sh get "$CHILD" | grep -q '_TBD_' \
  && echo "FAIL: enrichment output dropped" || echo "PASS: body persisted"
```

`create` then `get` the child and assert the body is not `_TBD_` — fails
against the pre-fix adapter.

**Rule 2 — Every claimed file gets an AC**: each file the ticket claims to
change must appear in at least one AC (grep or diff assertion). If no AC
names a file, no gate checks it — the ABS-61 lesson (`po-agent.md` section
shipped missing because no AC named the file).

## Quality Checklist

- [ ] All acceptance criteria are testable
- [ ] Procedural deliverable? → at least one AC executes the procedure (grep-only insufficient)
- [ ] Every claimed file appears in at least one AC (grep or diff assertion)
- [ ] Pattern references point to existing patterns
- [ ] Success validation command is runnable
- [ ] Linear ticket referenced

## Reference

- **Spec Template**: `docs/archive/specs/spec_template.md`
- **Pattern Library**: `patterns_library/README.md`
