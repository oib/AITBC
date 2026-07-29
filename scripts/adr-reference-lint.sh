#!/bin/bash
# =============================================================================
# ADR Reference Linter [ABS-315]
# =============================================================================
#
# A renumber leaves DANGLING CITATIONS. When ADR-A-0016 was renumbered to
# ADR-A-0017 (2026-07-10, because A-0016 was taken by ABS-196) the references in
# the epic title, both children, and the spec kept pointing at the old id — and a
# human even accepted the stale "ADR-A-0016" label, forcing the PO to
# scope-interpret intent onto A-0017 (ABS-190 lineage). Nothing checked that an
# ADR id cited in a spec/ADR actually resolves to an existing ADR file.
#
# This linter closes that gap. It collects every ADR id that a real ADR file
# DEFINES (frontmatter `id:`) and asserts that every strict ADR-id CITATION in
# the durable, low-noise scopes — specs/ and adrs/ cross-references — resolves to
# one of those defined ids. A citation that resolves to no file is a dangling
# reference (a forgotten renumber, or a typo): it fails.
#
# SCOPE (deliberately narrow to stay false-positive-free): specs/**/*.md and
# adrs/**/*.md only. docs/ prose (authoring guides, historical qa-validations)
# carries ILLUSTRATIVE ids (e.g. `ADR-A-0099-probe`, `ADR-P-0001-example`) that
# are examples, not citations, so docs/ is out of scope by design.
#
# MATCH: the strict id shape `ADR-[ACP]-NNNN` (4 digits) only, so placeholder
# prose like `ADR-YYY` / `ADR-A-00NN` in templates never matches.
#
# Exit: 0 = every citation resolves; 1 = at least one dangling reference.
#
# bash 3.2 + BSD tools only. Run from repo root, or:
#   scripts/adr-reference-lint.sh [adrs_dir] [refs_scope_dir ...]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADRS_DIR="${1:-$ROOT/adrs}"
shift || true
if [ "$#" -gt 0 ]; then
    SCOPES=("$@")
else
    SCOPES=("$ROOT/specs" "$ADRS_DIR")
fi

ID_RE='ADR-[ACP]-[0-9]{4}'

# Concurrency-safety [PILOT-56]. Under the staged `pool` stage (~90 test files at
# -P4) the previous `find | xargs grep` / `grep -r` pipelines re-walked the LIVE
# tree, so a file a sibling test transiently created/removed, or a read starved by
# resource contention, could flip Case 6 to a spurious DANGLING. Two defences,
# both of which leave the dangling-detection semantics (ABS-315) byte-identical
# for a stable tree:
#   (a) snapshot-then-read — enumerate the files ONCE, then read each path with an
#       existence guard, so a `grep` on a path that vanished between enumeration
#       and read can neither error the scan nor emit a false citation (AC5); and
#   (b) confirm-before-fail — a candidate dangling is re-scanned and reported only
#       if it survives EVERY pass. A real dangling is stable and always survives;
#       a transient race does not reproduce, so it is dropped.

# One full pass: prints the sorted, unique set of "DANGLING: ..." lines (empty on
# a clean tree). Deterministic ordering so passes can be intersected with comm(1).
scan() {
    # --- 1. Defined ids: every `id:` a real ADR file declares in frontmatter. --
    local defined="" adr id_lines f id lineno hit
    while IFS= read -r adr; do
        [ -n "$adr" ] || continue
        [ -f "$adr" ] || continue   # vanished between enumeration and read -> skip
        id_lines="$(grep -h '^id:' "$adr" 2>/dev/null)" || continue
        [ -n "$id_lines" ] && defined="$defined$id_lines
"
    done < <(find "$ADRS_DIR" -type f -name 'ADR-*.md' 2>/dev/null)
    defined="$(printf '%s' "$defined" \
        | sed -E 's/^id:[[:space:]]*//; s/[[:space:]]*$//' \
        | grep -E "^${ID_RE}$" | sort -u || true)"

    # --- 2. Citations in scope. Snapshot the file list once (README index rows
    # legitimately enumerate ids and are excluded, so a range table never FPs). --
    local scope_files=()
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        scope_files+=("$f")
    done < <(find "${SCOPES[@]}" -type f 2>/dev/null | grep -vE '/README\.md$' | sort)

    [ "${#scope_files[@]}" -gt 0 ] || return 0
    for f in "${scope_files[@]}"; do
        [ -f "$f" ] || continue   # vanished between snapshot and read -> skip
        # grep -noE prints one id per line as "<line>:<id>" (ids never contain ':').
        while IFS= read -r hit; do
            [ -n "$hit" ] || continue
            lineno="${hit%%:*}"; id="${hit#*:}"
            printf '%s\n' "$defined" | grep -qx "$id" && continue
            echo "DANGLING: $id cited in ${f#$ROOT/}:$lineno resolves to no ADR file"
        done < <(grep -noE "$ID_RE" "$f" 2>/dev/null || true)
    done
}

result="$(scan | sort -u)"

# Confirm: only danglers reproduced by every pass are real (see note above). A
# clean tree short-circuits here with no re-scan, so the green path stays fast.
if [ -n "$result" ]; then
    for _ in 1 2 3 4 5; do
        [ -n "$result" ] || break
        sleep 0.05
        next="$(scan | sort -u)"
        result="$(comm -12 <(printf '%s\n' "$result") <(printf '%s\n' "$next"))"
    done
fi

if [ -n "$result" ]; then
    printf '%s\n' "$result"
    ids="$(printf '%s\n' "$result" | grep -oE "$ID_RE" | sort -u | tr '\n' ' ')"
    n="$(printf '%s\n' "$result" | grep -c '^DANGLING:')"
    echo "adr-reference-lint: ${n} dangling ADR citation(s) — ${ids}"
    echo "A renumber must update every reference (or leave a redirect note under the old id). See docs/sop/ADR_AUTHORING_GUIDE.md."
    exit 1
fi

exit 0
