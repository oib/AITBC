---
name: spec-creation
description: Spec creation with pattern references, acceptance criteria, and demo
  scripts. Use when creating implementation specs, defining acceptance criteria, or
  breaking down user stories.
triggers:
- user
- model
context: fork
allowed-tools:
- glob
- grep
- read
- write
---

# Spec Creation Skill

## Purpose

Guide spec creation with clear acceptance criteria, pattern references for execution agents, and testable success validation commands.

## When This Skill Applies

Invoke this skill when:

- Creating implementation specs
- Breaking down user stories
- Defining acceptance criteria
- Adding pattern references for execution
- Creating demo scripts for validation
- Translating business requirements to technical specs

## Stop-the-Line Conditions

### FORBIDDEN Patterns

```markdown
# FORBIDDEN: Missing acceptance criteria

## Implementation

Just do the thing.

<!-- No testable outcomes defined -->

# FORBIDDEN: No pattern reference

## Technical Approach

Build it however you want.

<!-- Execution agents need pattern pointers -->

# FORBIDDEN: No success validation

## Done Criteria

Looks good to reviewer.

<!-- No command to verify completion -->
```

### CORRECT Patterns

````markdown
# CORRECT: Clear acceptance criteria

## Acceptance Criteria

- [ ] User can click button → modal appears
- [ ] Modal shows validation errors for empty fields
- [ ] Successful submission shows success toast

# CORRECT: Pattern reference for execution

## Pattern Reference

- **UI Pattern**: `patterns_library/ui/form-with-validation.md`
- **API Pattern**: `patterns_library/api/user-context-api.md`
- **RLS Pattern**: `patterns_library/database/rls-migration.md`

# CORRECT: Success validation command

## Success Validation

```bash
# Run these commands to verify implementation
yarn test:unit --grep "ModalForm"
curl -X POST http://localhost:3000/api/endpoint -d '{"test": true}'
```
````

`````

## Spec Template (MANDATORY)

Every spec must include:

````markdown
# SPEC-AITBC-{number}: {Feature Name}

## Summary

{One paragraph describing the feature}

## User Story

As a [user type], I want [goal] so that [benefit].

## Acceptance Criteria

- [ ] {Testable criterion 1}
- [ ] {Testable criterion 2}
- [ ] {Testable criterion 3}

## Environment Prerequisites (MANDATORY — write "none" if empty)

- **Secrets/API keys**: [name each key, which library/service needs it, and who provisions it — provisioning credentials is HUMAN-ONLY]
- **Env vars**: [name, example value, where consumed]
- **External accounts/services**: [service, plan/tier needed, owner]

## Pattern References

- **UI**: `patterns_library/ui/{pattern}.md`
- **API**: `patterns_library/api/{pattern}.md`
- **Database**: `patterns_library/database/{pattern}.md`
- **Security**: Follow RLS patterns in `docs/database/RLS_IMPLEMENTATION_GUIDE.md`

## Success Validation Command

```bash
# Run this to verify the feature works
{validation command}
`````

## Demo Script

1. Navigate to {page}
2. Click {button}
3. Observe {expected behavior}
4. Verify {success indicator}

## Logical Commits

1. `feat(scope): implement data model [AITBC-{number}]`
2. `feat(scope): add API endpoint [AITBC-{number}]`
3. `feat(scope): create UI component [AITBC-{number}]`
4. `test(scope): add unit tests [AITBC-{number}]`

````

## Acceptance Criteria Patterns

### User Action Criteria

```markdown
- [ ] User can {action} → {result}
- [ ] When user {triggers}, system {responds}
- [ ] User receives {feedback} after {action}
```

### Data Criteria

```markdown
- [ ] Data persists after {action}
- [ ] User can only see their own {data type}
- [ ] {field} validates {constraint}
```

### Error Criteria

```markdown
- [ ] Invalid input shows {error message}
- [ ] Network failure shows retry option
- [ ] Unauthorized access returns 401
```

## AC Coverage Rules (MANDATORY)

The gates verify exactly the acceptance criteria — anything verified only by
reading is not verified. Two rules govern what the AC list MUST cover:

### Rule 1: Executed AC for Procedural Deliverables

Every ticket that defines a **procedure an agent will follow** (a charter, an
SOP section, a workflow) MUST include at least one acceptance criterion that
**EXECUTES the procedure's command sequence** and asserts its postcondition.
Grep-only ACs are insufficient for procedural deliverables: a grep proves the
text exists, not that the procedure achieves its postcondition. A cheap
non-LLM simulation counts — bash the charter's adapter commands against the
mock tracker and assert the postcondition.

**Worked example (the ABS-60 gap)**: the decomposition charter's `create`
command could not persist the enriched child body — every child stayed
`_TBD_`. Every command in the charter was individually real, but the
procedure could not achieve its postcondition. All three gates passed it
because every AC was a grep or suite run. The executed AC that catches it:

```bash
# Execute the charter's persistence step against the mock tracker
BODY_FILE="$(mktemp)"
printf '# Simulated child\n\nEnriched goal/scope/AC body.\n' > "$BODY_FILE"
CHILD=$(scripts/mock-tracker.sh create --type ticket \
  --title "Executed-AC simulation" --body-file "$BODY_FILE")
# Postcondition: the enriched body persisted, not the _TBD_ template
scripts/mock-tracker.sh get "$CHILD" | grep -q '_TBD_' \
  && echo "FAIL: enrichment output dropped" || echo "PASS: body persisted"
```

`create` then `get` the child and assert the body is not `_TBD_` — this AC
fails in seconds against the pre-fix adapter.

### Rule 2: Every Claimed File Gets an AC

Each file the ticket claims to change MUST appear in at least one acceptance
criterion (a grep or diff assertion against that file). If no AC names a
file, no gate checks it — ABS-61 shipped without its claimed `po-agent.md`
section because no AC named the file.

## Pattern Discovery for Specs

Before writing any spec, invoke the `pattern-discovery` skill (isolated Explore
fork) — it returns only the matching pattern file path(s) plus a one-line
rationale. Read just the 1–2 returned files; never `cat`/`ls` `patterns_library/`
directly in the main context.

```bash
# Search for similar implementations
grep -r "similar feature" app/ lib/

# Check existing specs for format
ls specs/
cat specs/SPEC-AITBC-XXX-example.md
```

## Spec Quality Checklist

Before submitting spec:

- [ ] All acceptance criteria are testable (can verify pass/fail)
- [ ] Procedural deliverable (charter/SOP/workflow)? → at least one AC EXECUTES the procedure's command sequence (grep-only is insufficient — see AC Coverage Rules)
- [ ] Every file the ticket claims to change appears in at least one AC (grep or diff assertion)
- [ ] Environment Prerequisites section present (or explicit 'none' if empty) — missing prerequisites will be treated as a spec defect
- [ ] Pattern references point to existing patterns
- [ ] Success validation command is runnable
- [ ] Demo script is step-by-step reproducible
- [ ] Logical commits follow SAFe format
- [ ] Linear ticket referenced

## Output Locations

| Output Type  | Location                                              |
| ------------ | ----------------------------------------------------- |
| Impl specs   | `specs/SPEC-AITBC-{number}-{description}.md`            |
| Requirements | `docs/agent-outputs/requirements/AITBC-{number}-*.md`   |
| ADRs         | `docs/adr/ADR-{number}-{description}.md`              |

## Evidence for Linear

After spec approval:

```markdown
**BSA Spec Evidence**

**Spec**: specs/SPEC-AITBC-{number}-{description}.md
**Status**: Approved by [reviewer]

**Deliverables**:

- [x] Acceptance criteria defined
- [x] Pattern references added
- [x] Demo script created
- [x] Ready for implementation
```

## Authoritative References

- **Spec Template**: `specs_templates/spec_template.md`
- **Pattern Library**: `patterns_library/README.md`
- **Planning Guide**: `docs/team/PLANNING-AGENT-META-PROMPT.md`
- **SAFe Workflow**: `CONTRIBUTING.md`
````
