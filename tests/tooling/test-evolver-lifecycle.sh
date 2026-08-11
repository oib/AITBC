#!/usr/bin/env bash
# Test: evolver-lifecycle.sh skip paths and rate limit (ABS-25)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/hooks/evolver-lifecycle.sh"
EVOLVER_DIR="$(mktemp -d)"
# Isolated project dir so the hook's `mkdir .evolver` / rate-limit marker never
# lands in the real repo working tree (which would dirty it and rate-limit real runs).
PROJECT_DIR="$(mktemp -d)"
trap 'rm -rf "$EVOLVER_DIR" "$PROJECT_DIR"' EXIT

printf '#!/usr/bin/env bash\nexit 0\n' >"$EVOLVER_DIR/evolver"
chmod +x "$EVOLVER_DIR/evolver"

run_hook() {
  # shellcheck disable=SC2030
  env -i HOME="$HOME" PATH="${1:-/usr/bin:/bin}" \
    CLAUDE_PROJECT_DIR="$PROJECT_DIR" "${@:2}"
}

out="$(run_hook /usr/bin:/bin EVOLUTION_PROVIDER=none bash "$HOOK" 2>&1)" || true
printf '%s' "$out" | grep -qF "SKIP evolution provider none" \
  || { echo "FAIL: provider none skip"; exit 1; }

out="$(run_hook /usr/bin:/bin EVOLUTION_PROVIDER=evolver bash "$HOOK" 2>&1)" || true
printf '%s' "$out" | grep -qF "SKIP evolver not installed" \
  || { echo "FAIL: missing CLI skip"; exit 1; }

# Rate limit: first successful run, second skips within 300s
rm -rf "$PROJECT_DIR/.evolver"
out="$(run_hook "$EVOLVER_DIR:/usr/bin:/bin" EVOLUTION_PROVIDER=evolver bash "$HOOK" 2>&1)" || true
printf '%s' "$out" | grep -qF "RUN evolver --review" \
  || { echo "FAIL: expected successful run"; exit 1; }
[ -f "$PROJECT_DIR/.evolver/.last-hook-run" ] \
  || { echo "FAIL: rate-limit file not written after success"; exit 1; }

out="$(run_hook "$EVOLVER_DIR:/usr/bin:/bin" EVOLUTION_PROVIDER=evolver bash "$HOOK" 2>&1)" || true
printf '%s' "$out" | grep -qF "SKIP rate limit" \
  || { echo "FAIL: rate limit skip"; exit 1; }

echo "PASS: evolver-lifecycle behavioral"
exit 0
