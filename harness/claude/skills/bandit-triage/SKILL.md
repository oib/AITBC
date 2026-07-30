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
   "it is internal" is a claim, not a finding. Real fixes from this repo's own triage:

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
# nosec B608 - chain_id validated against ChainManager's known-chain allowlist (validate_chain_id) before use; only the table name is interpolated, all values use ? params
# nosec B310 - endpoint scheme validated above (must be http:// or https://) before this call
# nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
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
