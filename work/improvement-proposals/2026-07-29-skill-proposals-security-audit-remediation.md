# Skill proposals: bandit triage + dependency-CVE remediation

- **Date**: 2026-07-29
- **Source**: AITBC-60 epic retro (dependency/security audit remediation, children AITBC-51..59)
- **Ownership**: PROJECT-level (`.claude/skills/`), not boilerplate — route as creation tickets
  via BSA → Issue Enrichment Agent. This agent does not file tickets or create the skills.
- **Prior-art check**: `.claude/skills/security-audit/` exists but is TS/Prisma/RLS-only
  (0 mentions of bandit/pip-audit/FastAPI across 207 lines) and does not cover either
  procedure — see `2026-07-29-security-audit-skill-stack-mismatch.md`. These are therefore
  new skills, not extensions.

## Recurrence evidence

Both procedures cleared the threshold (same task on 3+ tickets) within a single epic:

| Procedure | Tickets | Volume |
| --------- | ------- | ------ |
| Bandit rule-category triage | AITBC-55 (B608), 56 (B108), 57 (B104), 58 (B310), 59 (B113) — **5** | 107 findings |
| Dependency CVE remediation | AITBC-51 (ecdsa), 52 (msgpack), 53 (pydantic-settings), 54 (starlette) — **4** | 4 advisories |

The five triage tickets ran the same procedure with the rule ID swapped. The drafts below are reverse-engineered from what the
epic actually did (verified against the working-tree diff), not invented.

---

## Skill Proposal 1: `bandit-triage`

- **Recurring task**: per bandit rule category — enumerate findings, classify each as
  genuine-fix vs. accepted-risk, fix or annotate `# nosec` with a written justification,
  re-scan to zero.
- **Occurrences**: 5 tickets (AITBC-55..59), 107 findings, one actor.
- **Belongs at**: `.claude/skills/bandit-triage/SKILL.md`
- **Draft SKILL.md**:

````markdown
---
name: bandit-triage
description: Triage a bandit rule category (B608, B108, B104, B310, B113, ...) to zero
  unreviewed findings. Use when acting on a bandit scan, resolving a security-audit
  finding category, or adding a # nosec annotation.
context: fork
agent: Explore
allowed-tools: Read, Bash, Grep, Glob
---

# Bandit Triage

## Purpose

Take one bandit rule category from "N raw findings" to "zero unreviewed findings", where
every remaining suppression carries a justification a reviewer can check.

## When This Skill Applies

- A bandit scan reports findings in a rule category
- A security-audit ticket is scoped to one rule ID
- You are about to write a `# nosec` comment

## Procedure

1. **Enumerate the category** — scan only the rule under triage, so the count is the
   ticket's scope:

   ```bash
   ./venv/bin/python -m bandit -r aitbc/ apps/ cli/ -ll -t B608 -f screen
   ```

2. **Classify every finding** into exactly one bucket. Default to FIX and argue for
   every `# nosec` rather than using it to clear the scan:

   | Bucket | Meaning | Action |
   | ------ | ------- | ------ |
   | FIX | Reachable with attacker-influenced input | Change the code |
   | ACCEPT | Structurally unreachable or non-production | `# nosec` + justification |
   | DEFER | Needs design change beyond this ticket | Follow-up ticket, do not annotate |

3. **Fix what is genuinely reachable.** Trace the input to its source before deciding —
   "it's internal" is a claim, not a finding. Real fixes from this repo's own triage:

   ```python
   # B608: interpolated SQL -> parameterised, value bound not formatted
   cursor.execute(
       'SELECT DATE(created_at) as day, type, COUNT(*) as count FROM "transaction" '
       "WHERE created_at >= datetime('now', ?) GROUP BY DATE(created_at), type",
       (f"-{int(days)} days",),
   )

   # B310: third-party URL -> validate the scheme before urlopen()
   # The offer arrives from a provider over the gossip network, so an unvalidated
   # endpoint could point at file:// or an internal address.
   if not endpoint.startswith(("http://", "https://")):
       error(f"Rejecting offer with unsafe endpoint scheme: {endpoint}")
       raise click.Abort()
   ```

4. **Annotate accepted risk in the house format.** One line, rule ID, then a justification
   that names *why it cannot be exploited* — the specific validation, allowlist, or context:

   ```
   # nosec <RULE> - <why this specific site is safe>
   ```

   Good (from this repo — each names a checkable fact):

   ```python
   # nosec B608 - chain_id validated against ChainManager's known-chain allowlist
   #   (validate_chain_id) before use; only the table name is interpolated, all values use ? params
   # nosec B310 - endpoint scheme validated above (must be http:// or https://) before this call
   # nosec B104 - intentional service bind-all; systemd-only (Docker-free) services bind
   #   broadly by design, real boundary is the firewall/reverse-proxy layer
   ```

   Rejected — a bare suppression clears the scan without recording a reason:

   ```python
   insert_sql = f'INSERT INTO "{table}" ...'  # nosec B608
   ```

5. **Re-scan to zero** and record the before/after counts as ticket evidence:

   ```bash
   ./venv/bin/python -m bandit -r aitbc/ apps/ cli/ -ll -t B608 -f screen | tail -5
   ```

6. **Run the affected tests** — a parameterised query or a new scheme check is a behaviour
   change, not a comment.

## Expected Output

- Category re-scan at 0 findings
- Every suppression carries a rule ID and a checkable justification
- Before/after counts + bucket tally (FIX / ACCEPT / DEFER) on the ticket
- Any DEFER raised as its own follow-up ticket

## Stop-the-Line

Escalate instead of annotating when: the finding is reachable from user input and the fix
needs an architectural change; or suppressing would be the *only* way to clear it and you
cannot name why it is unexploitable.
````

---

## Skill Proposal 2: `dependency-cve-remediation`

- **Recurring task**: per pip-audit advisory — locate the dependency's declaration, upgrade
  and re-lock, or (when no fixed version exists) record an explicit mitigation decision;
  re-scan and regression-test.
- **Occurrences**: 4 tickets (AITBC-51..54). AITBC-51 (ecdsa) is the no-fix-available branch,
  which is exactly the case teams handle inconsistently — hence worth encoding.
- **Belongs at**: `.claude/skills/dependency-cve-remediation/SKILL.md`
- **Draft SKILL.md**:

````markdown
---
name: dependency-cve-remediation
description: Resolve a pip-audit/CVE advisory against a Poetry monorepo dependency, including
  the no-fix-available case. Use when acting on a dependency audit finding or a CVE/GHSA/PYSEC advisory.
context: fork
agent: Explore
allowed-tools: Read, Bash, Grep, Glob
---

# Dependency CVE Remediation

## Purpose

Turn one advisory into either a locked upgrade or a recorded, justified mitigation — never
an open finding and never a silent skip.

## When This Skill Applies

- `pip-audit` reports a vulnerable package
- A GHSA/PYSEC/CVE advisory names a dependency in use
- A dependency-audit ticket is scoped to one package

## Procedure

1. **Confirm the advisory applies to the version actually resolved** — not the range declared:

   ```bash
   ./venv/bin/python -m pip_audit 2>&1 | grep -i "<package>"
   ./venv/bin/python -m pip show <package> | head -3
   ```

2. **Locate every declaration.** In a monorepo the package may be pinned in more than one
   place; missing one leaves the CVE live:

   ```bash
   git grep -n "<package>" -- pyproject.toml requirements.txt '**/pyproject.toml'
   ```

3. **Branch on fix availability.**

   **A fixed version exists** — bump the constraint, re-lock, verify the resolved version moved:

   ```bash
   # edit pyproject.toml / requirements.txt to the fixed floor, then:
   poetry lock
   ./venv/bin/python -m pip show <package> | head -3   # confirm the new version resolved
   ```

   Keep `poetry.lock` in the same commit as the constraint change — a bumped constraint with a
   stale lock fixes nothing.

   **No fixed version exists** (e.g. ecdsa / PYSEC-2026-1325 Minerva timing attack) — do NOT
   leave the ticket open-ended. Produce a written decision covering:

   - **Exposure**: is the vulnerable code path reachable in this system? Name the call sites
     (`git grep` them) and the attacker's position.
   - **Options**: upgrade impossible; migrate to another library; compensating control; accept.
   - **Decision + rationale**, recorded on the ticket. If it implies a library migration,
     raise an ADR (`adrs/`) rather than deciding it inside a dependency ticket.

4. **Re-scan and regression-test.** A transitive bump can move more than the target package:

   ```bash
   ./venv/bin/python -m pip_audit 2>&1 | grep -i "<package>"   # expect no rows
   ./venv/bin/python -m pytest tests/unit -q
   ./venv/bin/python -m ruff check .
   ```

5. **Attach evidence to the ticket**: before/after version, the pip-audit line clearing, and
   the test result — or, for a no-fix case, the mitigation decision.

## Expected Output

- Constraint + `poetry.lock` updated together, or a recorded mitigation decision
- `pip-audit` clean for the package
- Test suite green (no regression from the bump)

## Stop-the-Line

Escalate when the only fix is a major-version bump with breaking changes, or when a no-fix
advisory sits on a reachable cryptographic path — both are architecture decisions (ADR), not
dependency chores.
````

---

## Human actions

- Route both proposals as skill-creation tickets via BSA → Issue Enrichment Agent.
- Decide proposal 1 vs. the upstream `security-audit` mismatch report: if upstream splits that
  skill stack-wise, `bandit-triage` may become the Python companion rather than a standalone.
