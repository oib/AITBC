#!/usr/bin/env bash
# TEST FIXTURE (ABS-382 / ABS-231 S5) — a `policies`-capable tracker adapter.
# Delegates every op to the mock tracker, but implements the `policies` agent op
# (S4/ABS-381) so the orchestrator's build_packet policy-injection path can be
# driven in the suite without a live agentic backend. It reproduces S4's server
# body exactly: the rendered effective-policy text followed by a trailing
# `policy_rev: <sha256>` line (`${rendered}policy_rev: ${rev}\n`). The rendered
# text is read from $POLICY_SRC so a test can mutate it and prove the packet
# cache re-derives on a policy change (revision-pinned caching).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MOCK="${POLICIES_FIXTURE_MOCK:-$HERE/../../scripts/mock-tracker.sh}"
case "${1:-}" in
    policies)
        body="$(cat "${POLICY_SRC:-/dev/null}" 2>/dev/null || true)"
        [ -n "$body" ] || body="Test policy: human-only merges; never push to main."
        # ABS-425 trust-boundary guard: the `policy_rev:` header line and the
        # `=== … ===` section-marker syntax are RESERVED by the packet framing.
        # Rendered policy body text must never contain a leading `policy_rev:`
        # line or a `=== … ===` marker line — either could forge a revision hash
        # or a packet section boundary when injected. Refuse to render (non-zero
        # exit, nothing on stdout) rather than emit a body that corrupts a packet.
        # See the S4 `policies` op contract (docs/guides/AGENTIC-BACKEND-API.md).
        if printf '%s\n' "$body" | grep -qE '^policy_rev:|^=== .* ===[[:space:]]*$'; then
            echo "policies: ABS-425 guard — rendered policy body contains a reserved marker line (leading 'policy_rev:' or '=== … ===' section marker); refusing to render" >&2
            exit 3
        fi
        rev="$(printf '%s' "$body" | shasum -a 256 | cut -d' ' -f1)"
        printf '%s\n' "$body"
        printf 'policy_rev: %s\n' "$rev"
        ;;
    *)
        exec bash "$MOCK" "$@"
        ;;
esac
