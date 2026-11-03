#!/bin/bash
# ============================================================================
# systemd-env.sh — EnvironmentFile-compatible KEY=VALUE reader/writer
# ----------------------------------------------------------------------------
# systemd EnvironmentFile= semantics differ from shell `source` in ways that
# have bitten deploy scripts: `source` executes the file (command substitution,
# globbing, `export` side effects, syntax errors on unquoted spaces and `#`),
# while systemd only parses KEY=VALUE lines. Values with spaces or an inline
# ` # comment` either broke the read or silently produced a different value —
# and an unparseable file degraded to a default instead of failing loudly.
#
# This helper implements the subset of EnvironmentFile parsing the deploy
# scripts need, as a subprocess so nothing it reads enters the caller's shell:
#
#   systemd-env.sh get    <file> <key>   print the value
#                                        rc 0 = found, 1 = absent, 2 = malformed
#   systemd-env.sh parse  <file>         print every valid KEY=VALUE line
#                                        rc 0 = ok, 2 = a malformed assignment was seen
#   systemd-env.sh append <file> <line>  append a line, writing a newline first
#                                        when the file's last byte is not one
#
# Parse rules (mirroring systemd's EnvironmentFile):
#   - blank lines and lines whose first non-blank char is '#' are skipped
#   - an optional leading 'export ' is dropped
#   - KEY matches [A-Za-z_][A-Za-z0-9_]*; whitespace around '=' is ignored
#   - a value wrapped in matching single or double quotes is unquoted
#     (unbalanced quotes are malformed)
#   - an unquoted value runs to end of line; a '#' preceded by whitespace
#     starts an inline comment; surrounding whitespace is trimmed
#   - no variable expansion, no command execution, ever
# ============================================================================

set -euo pipefail

_SYSTEMD_ENV_KEY_RE='^[A-Za-z_][A-Za-z0-9_]*$'

# Read one logical line's KEY=VALUE. $1 = raw line.
# Prints "KEY=value" on stdout; rc 1 = not an assignment, rc 2 = malformed.
_systemd_env_parse_line() {
    local line="$1"

    # trim leading whitespace; skip blanks and comments
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && return 1

    # optional export prefix
    [[ "$line" == export[[:space:]]* ]] && line="${line#export}"

    # split at the first '='
    [[ "$line" == *=* ]] || return 1
    local key="${line%%=*}" value="${line#*=}"

    # trim whitespace around the key
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ $_SYSTEMD_ENV_KEY_RE ]] || return 2

    # trim leading whitespace of the value
    value="${value#"${value%%[![:space:]]*}"}"

    if [[ "$value" == \"* || "$value" == \'* ]]; then
        # quoted: the closing quote must match the opener
        local q="${value:0:1}"
        if [[ ${#value} -ge 2 && "${value: -1}" == "$q" ]]; then
            value="${value:1:${#value}-2}"
        else
            return 2
        fi
    else
        # unquoted: '#' after whitespace opens an inline comment
        value="${value%%[[:space:]]\#*}"
        # trim trailing whitespace
        value="${value%"${value##*[![:space:]]}"}"
    fi

    printf '%s=%s\n' "$key" "$value"
}

cmd_get() {
    local file="$1" want="$2" line parsed parsed_key
    [[ -f "$file" ]] || return 1
    local found=1 prc
    while IFS= read -r line || [[ -n "$line" ]]; do
        parsed=$(_systemd_env_parse_line "$line") && prc=0 || prc=$?
        [[ $prc -eq 2 ]] && return 2
        [[ $prc -ne 0 ]] && continue
        parsed_key="${parsed%%=*}"
        if [[ "$parsed_key" == "$want" ]]; then
            printf '%s\n' "${parsed#*=}"
            found=0
        fi
    done < "$file"
    return $found
}

cmd_parse() {
    local file="$1" line parsed rc=0 prc
    [[ -f "$file" ]] || return 1
    while IFS= read -r line || [[ -n "$line" ]]; do
        parsed=$(_systemd_env_parse_line "$line") && prc=0 || prc=$?
        if [[ $prc -eq 0 ]]; then
            printf '%s\n' "$parsed"
        elif [[ $prc -eq 2 ]]; then
            rc=2
        fi
    done < "$file"
    return $rc
}

cmd_append() {
    local file="$1" line="$2"
    # The file's last byte must be a newline, or the appended line glues itself
    # onto the existing last line and corrupts both (seen in env appenders).
    if [[ -f "$file" && -s "$file" ]]; then
        local last_byte
        last_byte=$(tail -c 1 "$file" | od -An -tx1 | tr -d '[:space:]')
        [[ "$last_byte" != "0a" ]] && printf '\n' >> "$file"
    fi
    printf '%s\n' "$line" >> "$file"
}

main() {
    local sub="${1:-}"
    case "$sub" in
        get)    cmd_get "$2" "$3" ;;
        parse)  cmd_parse "$2" ;;
        append) cmd_append "$2" "$3" ;;
        *)
            echo "usage: $0 {get <file> <key>|parse <file>|append <file> <line>}" >&2
            return 2
            ;;
    esac
}

main "$@"
