# shellcheck shell=bash
# =============================================================================
# tests/sandbox-guard.sh — mechanical sandbox env isolation (PILOT-46 / ABS-546)
# =============================================================================
# WHY. Seat testsuites inherit BACKEND_URL / BACKEND_TOKEN / TRACKER_CMD /
# ORCH_INSTANCE_ID from the runner env (the seat's tracker_cmd legitimately
# needs them). Their orchestrator/backend FIXTURES then inherit them too and
# register REAL instances + seat_spawn rows in the PROD backend — the Mission
# Control board was flooded with ~1750 junk rows (24.07.) then ~1000 more
# (25.07.), from hundreds of throwaway instances. Prose guardrails on every
# ticket did NOT stop it. This is the mechanical stop.
#
# HOW. Every tests/ entrypoint that touches the backend or a tracker adapter
# SOURCES this file near the top:
#
#     . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"
#
# It unsets the four leak-carrying vars so a fixture cannot reach the prod
# backend by inheritance. A test that boots its OWN local backend/tracker sets
# its own values AFTER sourcing (the unset only strips an INHERITED value, never
# a locally-assigned one — the source line sits above all local setup).
#
# ESCAPE HATCH. A deliberate live-conformance test exports
# ORCH_TEST_ALLOW_BACKEND=1 BEFORE sourcing; the guard then leaves the env
# untouched (and says so once on stderr).
#
# ENFORCEMENT. scripts/sandbox-guard-check.sh fails CI if a tests/ entrypoint
# that touches backend/tracker does not source this file. Regression coverage:
# tests/tooling/test-sandbox-guard.sh.
# =============================================================================

if [ "${ORCH_TEST_ALLOW_BACKEND:-}" = "1" ]; then
    printf 'sandbox-guard: ORCH_TEST_ALLOW_BACKEND=1 — backend/tracker env left intact (live-conformance mode)\n' >&2
else
    unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID
fi

# PILOT-81: the harness-release preflight (check_harness_release) fail-closes a
# LIVE start unless $ORCH_HARNESS_HOME is exactly on a release tag with a clean
# tree. In a test sandbox the harness IS a dev checkout (feature branch, dirty), so
# that guard is meaningless here and would break every --live orchestrator test.
# Default it OFF for the sandbox; the guard's own behavior is covered by
# tests/orchestrator.d/PILOT-81-harness-release-guard.sh, which re-enables it
# against a purpose-built temp repo. A test that specifically needs it on sets
# ORCH_HARNESS_RELEASE_GUARD=1 AFTER sourcing (the source line sits above local setup).
export ORCH_HARNESS_RELEASE_GUARD=0
