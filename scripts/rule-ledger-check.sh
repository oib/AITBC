#!/bin/bash
# =============================================================================
# Rule Ledger Check (ABS-515, review-hardened per ABS-514 Stage-1)
# =============================================================================
# docs/rule-ledger.yaml is the machine-readable inventory of every normative
# rule in the RULES-carrying markdown surface (AGENTS.md, CLAUDE.md, docs/sop/,
# ...). Each H2/H3 section of a scoped file maps to exactly one ledger row per
# occurrence, and each row declares its enforcement status:
#
#   enforced     the rule has at least one deterministic sensor (a tests/*.sh,
#                a guard/lint script, a hook, a CI workflow, or a
#                scripts/<file>.sh:<function> gate) — listed in `sensors:`.
#                NOTE the honest semantics: enforced means a NAMED SENSOR
#                EXISTS, not that the sensor is proven live-wired to this
#                exact rule. Existence is what this checker can verify;
#                wiredness is what the sensor's own tests/test-*.sh pins.
#   derived      the section DESCRIBES code-enforced behavior (it retells what
#                scripts already do). Sensor reference mandatory, same C2
#                check as enforced. derived sections are the condensation
#                candidates for ABS-524 (S10).
#   unenforced   the rule relies on LLM interpretation alone; `risk:` MUST
#                say what can go wrong (this is the backfill worklist)
#   informative  the section is descriptive/reference, not a normative rule
#                and not a retelling of code behavior
#
# Motivation (epic ABS-514): every documented md-misread incident (gates after
# dispatch, Done with open PR, ADR frontmatter drift, station skip ABS-492)
# came from the unsensored subset of the instruction surface. This checker
# makes "new SOP section without a declared enforcement status" a CI failure.
#
# Checks:
#   C1  ledger row shape: id (R-NNNN, unique), file, heading, valid kind
#   C2  enforced/derived rows name >=1 sensor; every sensor path exists; a
#       `path:function` sensor's function must be defined in that file
#   C3  unenforced rows carry a non-empty risk note
#   C4  every scoped file's H2/H3 headings match the ledger rows for that file
#       as a MULTISET (duplicate headings need one row per occurrence; a
#       ledger row whose heading left the file is a dangling anchor)
#   C5  the ledger scope covers at least the required RULES files
#   C6  every *.md under each `scope_dirs:` directory appears in `scope:` —
#       a NEW rules file cannot be silently invisible to the ledger (the
#       hand-listed scope alone would be cosmetic; review finding 1.1)
#
# Headings are anchored by (file, heading text) — never by injected IDs or
# line numbers (invasive / churn-heavy). Fenced code blocks are ignored when
# extracting headings.
#
# Usage:
#   scripts/rule-ledger-check.sh            # check, exit 0/1
#   scripts/rule-ledger-check.sh --report   # per-file kind counts + quote
#                                           # + absolute unenforced backlog
#
# Fixture overrides (regression tests): RULE_LEDGER_FILE (ledger path),
# RULE_LEDGER_ROOT (root for scope files + sensors),
# RULE_LEDGER_REQUIRED_SCOPE (colon-separated required scope list).
# Exit 0 = ledger complete and consistent. Exit 1 = violation (details on
# stderr). Exit 2 = missing ledger/file (setup error).
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LEDGER="${RULE_LEDGER_FILE:-$REPO_ROOT/docs/rule-ledger.yaml}"
ROOT="${RULE_LEDGER_ROOT:-$REPO_ROOT}"
REQUIRED_SCOPE="${RULE_LEDGER_REQUIRED_SCOPE:-AGENTS.md:CLAUDE.md:docs/sop/ORCHESTRATOR_SOP.md}"
MODE="${1:-check}"

fail=0
note() { printf '  %s\n' "$1" >&2; }
err()  { printf 'RULE-LEDGER: %s\n' "$1" >&2; fail=1; }

[ -f "$LEDGER" ] || { printf 'rule-ledger-check: missing ledger: %s\n' "$LEDGER" >&2; exit 2; }

# --- parsers -----------------------------------------------------------------
# Field separator for parsed records: unit separator, NOT tab — tab is IFS
# whitespace in bash, so `read` would collapse an empty sensors field and
# shift risk into the wrong column.
US="$(printf '\037')"

# Scope file list / scope dir list (paths relative to ROOT).
scope_files() {
    awk '/^scope:/{s=1;next} s&&/^[a-z]/{s=0} s&&/^  - /{sub(/^  - /,"");print}' "$LEDGER"
}
scope_dirs() {
    awk '/^scope_dirs:/{s=1;next} s&&/^[a-z]/{s=0} s&&/^  - /{sub(/^  - /,"");print}' "$LEDGER"
}
# Rule rows as US-separated: id, file, heading, kind, sensors(csv), risk.
parse_rules() {
    awk -v OFS="$US" '
        function flush(){ if (id != "") print id, file, heading, kind, sensors, risk }
        /^rules:/ { inr=1; next }
        !inr { next }
        /^  - id: /      { flush(); id=$0; sub(/^  - id: /,"",id); file=heading=kind=sensors=risk=""; next }
        /^    file: /    { file=$0;    sub(/^    file: /,"",file); next }
        /^    heading: / { heading=$0; sub(/^    heading: "/,"",heading); sub(/"$/,"",heading); next }
        /^    kind: /    { kind=$0;    sub(/^    kind: /,"",kind); next }
        /^    sensors: / { sensors=$0; sub(/^    sensors: \[/,"",sensors); sub(/\]$/,"",sensors); next }
        /^    risk: /    { risk=$0;    sub(/^    risk: "/,"",risk); sub(/"$/,"",risk); next }
        END { flush() }
    ' "$LEDGER"
}
# H2/H3 heading texts of a markdown file, fence-aware, trailing-space-trimmed.
md_headings() {
    awk '/^```/{f=!f;next} !f && /^##[#]? /{sub(/^#+ /,""); sub(/[ \t]+$/,""); print}' "$ROOT/$1"
}
ledger_headings_for() {
    parse_rules | awk -F"$US" -v f="$1" '$2==f{print $3}'
}
kind_count() { # kind_count <kind> [file]
    if [ "$#" -ge 2 ]; then
        parse_rules | awk -F"$US" -v k="$1" -v f="$2" '$2==f&&$4==k' | wc -l | tr -d ' '
    else
        parse_rules | awk -F"$US" -v k="$1" '$4==k' | wc -l | tr -d ' '
    fi
}

# --- C1: row shape, id format/uniqueness, kind vocabulary --------------------
while IFS=$'\037' read -r id file heading kind sensors risk; do
    [ -n "$id" ] || continue
    # Two legal id forms (ABS-600):
    #   R-NNNN                legacy, frozen — never mint new ones (collides in parallel)
    #   R-<TICKET>-<n>        ticket-scoped — the collision-free scheme for NEW rows.
    #                         <TICKET> is the globally-unique introducing ticket
    #                         (e.g. R-ABS-600-1); <n> counts this ticket's own rows.
    printf '%s' "$id" | grep -qE '^R-[0-9]{4}$|^R-[A-Z][A-Z0-9]*-[0-9]+-[0-9]+$' \
        || err "C1: bad rule id '$id' (want legacy R-NNNN or ticket-scoped R-<TICKET>-<n>)"
    [ -n "$file" ]    || err "C1: $id has no file"
    [ -n "$heading" ] || err "C1: $id has no heading"
    case "$kind" in
        enforced|derived|unenforced|informative) : ;;
        *) err "C1: $id has invalid kind '$kind' (enforced|derived|unenforced|informative)" ;;
    esac
    [ -z "$file" ] || [ -f "$ROOT/$file" ] || err "C1: $id file does not exist: $file"

    # --- C2: enforced/derived rows need existing sensors ---------------------
    if [ "$kind" = "enforced" ] || [ "$kind" = "derived" ]; then
        if [ -z "$sensors" ]; then
            err "C2: $id is $kind but names no sensors"
        else
            old_ifs="$IFS"; IFS=','
            for s in $sensors; do
                s="$(printf '%s' "$s" | sed 's/^ *//; s/ *$//')"
                [ -n "$s" ] || continue
                spath="${s%%:*}"
                sfunc=""
                case "$s" in *:*) sfunc="${s#*:}";; esac
                if [ ! -e "$ROOT/$spath" ]; then
                    err "C2: $id sensor path does not exist: $spath"
                elif [ -n "$sfunc" ] && ! grep -qE "^${sfunc}\(\)" "$ROOT/$spath"; then
                    err "C2: $id sensor function '${sfunc}()' not found in $spath"
                fi
            done
            IFS="$old_ifs"
        fi
    fi

    # --- C3: unenforced rows need a risk note --------------------------------
    if [ "$kind" = "unenforced" ] && [ -z "$risk" ]; then
        err "C3: $id is unenforced but has no risk note"
    fi
done < <(parse_rules)

dup_ids="$(parse_rules | cut -d"$US" -f1 | sort | uniq -d)"
if [ -n "$dup_ids" ]; then
    err "C1: duplicate rule ids: $(printf '%s' "$dup_ids" | tr '\n' ' ')"
    # AC5 (ABS-600): name WHICH file+heading each colliding id came from, so the
    # operator no longer has to grep the ledger to locate the collisions. This is
    # the backstop-of-last-resort; the ticket-scoped scheme above is what keeps
    # parallel branches from reaching here in the first place.
    parse_rules | awk -F"$US" -v ids="$dup_ids" '
        BEGIN { n = split(ids, a, "\n"); for (i = 1; i <= n; i++) if (a[i] != "") want[a[i]] = 1 }
        want[$1] { printf "    %s  <-  %s  \342\200\272  \"%s\"\n", $1, $2, $3 > "/dev/stderr" }
    '
fi

# --- C5: required scope subset ------------------------------------------------
old_ifs="$IFS"; IFS=':'
for req in $REQUIRED_SCOPE; do
    [ -n "$req" ] || continue
    scope_files | grep -qxF "$req" || err "C5: required RULES file missing from ledger scope: $req"
done
IFS="$old_ifs"

# --- C6: every *.md under a scope_dir must be in scope (no invisible files) ---
while IFS= read -r sd; do
    [ -n "$sd" ] || continue
    if [ ! -d "$ROOT/$sd" ]; then
        err "C6: scope_dir does not exist: $sd"
        continue
    fi
    for f in "$ROOT/$sd"/*.md; do
        [ -e "$f" ] || continue
        rel="${f#"$ROOT"/}"
        scope_files | grep -qxF "$rel" \
            || err "C6: $rel exists under scope_dir $sd but is not in the ledger scope (new rules file must get ledger rows)"
    done
done < <(scope_dirs)

# --- C4: per-scope-file heading coverage (multiset) ---------------------------
while IFS= read -r sf; do
    [ -n "$sf" ] || continue
    if [ ! -f "$ROOT/$sf" ]; then
        err "C4: scope file does not exist: $sf"
        continue
    fi
    missing="$(comm -23 <(md_headings "$sf" | sort) <(ledger_headings_for "$sf" | sort))"
    dangling="$(comm -13 <(md_headings "$sf" | sort) <(ledger_headings_for "$sf" | sort))"
    if [ -n "$missing" ]; then
        err "C4: $sf has headings with no ledger row (declare enforced/derived/unenforced/informative):"
        printf '%s\n' "$missing" | sed 's/^/    + /' >&2
    fi
    if [ -n "$dangling" ]; then
        err "C4: ledger rows for $sf anchor headings that are not in the file (dangling anchor):"
        printf '%s\n' "$dangling" | sed 's/^/    - /' >&2
    fi
done < <(scope_files)

# --- report -------------------------------------------------------------------
if [ "$MODE" = "--report" ]; then
    printf 'Rule ledger report (%s)\n' "$LEDGER"
    printf 'enforced/derived = a named sensor EXISTS (not: proven live-wired).\n\n'
    printf '%-40s %9s %8s %11s %12s %6s\n' "file" "enforced" "derived" "unenforced" "informative" "quote"
    while IFS= read -r sf; do
        [ -n "$sf" ] || continue
        e="$(kind_count enforced "$sf")"; d="$(kind_count derived "$sf")"
        u="$(kind_count unenforced "$sf")"; i="$(kind_count informative "$sf")"
        n=$((e + d + u)); q="-"
        [ "$n" -gt 0 ] && q="$(((e + d) * 100 / n))%"
        printf '%-40s %9s %8s %11s %12s %6s\n' "$sf" "$e" "$d" "$u" "$i" "$q"
    done < <(scope_files)
    te="$(kind_count enforced)"; td="$(kind_count derived)"
    tu="$(kind_count unenforced)"; ti="$(kind_count informative)"
    tn=$((te + td + tu)); tq="-"
    [ "$tn" -gt 0 ] && tq="$(((te + td) * 100 / tn))%"
    printf '%-40s %9s %8s %11s %12s %6s\n' "TOTAL (normative: $tn)" "$te" "$td" "$tu" "$ti" "$tq"
    printf '\nUnenforced backlog (the actual worklist): %s rows\n' "$tu"
fi

if [ "$fail" -ne 0 ]; then
    printf '\nrule-ledger-check: FAIL — the rule ledger is incomplete or inconsistent (see above).\n' >&2
    exit 1
fi
[ "$MODE" = "--report" ] || printf 'rule-ledger-check: OK — every scoped rule section has a declared enforcement status.\n'
exit 0
