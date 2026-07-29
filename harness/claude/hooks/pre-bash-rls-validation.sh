#!/bin/bash
# Pre-Bash Hook: RLS Validation (ABS-149)
#
# Reminds about RLS context before Prisma/SQL database operations.
#
# Claude Code PreToolUse protocol (ABS-32): the hook receives a JSON payload on
# STDIN (.tool_input.command), NOT a positional $1 argument. The old version
# read "$1" and therefore never saw the command — it was a dead, never-firing
# gate. This version re-derives the command from stdin via jq, like every other
# hook in settings.template.json.
#
# Advisory only: this hook NEVER blocks (always exits 0). It emits a reminder
# when a Bash command touches the database without an explicit RLS context.
# Fails open (exit 0) if jq is missing or no command is present.

payload=$(cat)

command -v jq >/dev/null 2>&1 || { echo 'hooks: jq not found; skipping RLS validation' >&2; exit 0; }

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

# Only react to Prisma / SQL database operations.
printf '%s' "$cmd" | grep -qE '(npx prisma|psql|DATABASE_URL)' || exit 0

# RLS context present -> allow.
if printf '%s' "$cmd" | grep -qE '(withUserContext|withAdminContext|withSystemContext)'; then
  echo '✅ RLS context detected in command'
  exit 0
fi

# Schema / migration operations are allowed without an RLS context.
if printf '%s' "$cmd" | grep -qE '(prisma migrate|prisma generate|prisma studio)'; then
  echo '✅ Prisma schema operation - allowed'
  exit 0
fi

# Database operation without explicit RLS context -> warn (advisory, non-blocking).
echo '⚠️  WARNING: Database operation without explicit RLS context'
echo '   Consider using withUserContext / withAdminContext / withSystemContext'
exit 0
