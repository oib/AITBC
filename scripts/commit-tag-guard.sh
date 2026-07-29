#!/usr/bin/env bash
# =============================================================================
# commit-tag-guard.sh — the ticket-tag convention, made mechanical (PILOT-79)
# =============================================================================
# PILOT-79-commit-tag-guard  <- marker: docs/tests grep for this token.
#
# WHY. CONTRIBUTING.md declares `type(scope): description [PREFIX-XXX]` a REQUIRED
# commit format and even claims "the CI/CD pipeline will automatically reject"
# untagged commits — but nothing in the repo checked it (no commit-msg hook, no
# commitlint). The tag is load-bearing: the RTE Epic-Integration seat, on a smoke
# failure, git-bisects the epic branch and maps the culprit commit to its story
# VIA THE [PREFIX-XXX] TAG (rte.md step 6). A culprit with no tag routes the whole
# epic to `Needs PO Decision`, a status with NO edge back to the merge path — a
# dead end reached because one commit message was incomplete. Real occurrence:
# epic/PILOT-58 4d70ec09 carried its ticket only in prose, not as [PILOT-66].
#
# TWO CLASSES (the ticket's core distinction — "every commit needs a tag" is WRONG):
#   (a) Seat/story commits on a story branch — tag MANDATORY. These are exactly the
#       commits the bisect maps.
#   (b) Operator/release commits — legitimately ticketless, but RECOGNISABLE, never
#       waved through unnoticed. Recognised by:
#         - a subject beginning `chore(release)` / `chore(governor)` (release
#           automation, e.g. "chore(release): promote governor to v2.32.0"), or
#         - an explicit `[no-ticket]` marker anywhere in the message (the operator's
#           self-documenting opt-out for a genuinely ticketless commit — a
#           HARNESS_CHANGELOG entry, a docs afterthought).
#   The exempt class is DOCUMENTED (CONTRIBUTING.md "Exempt commits"), not hidden.
#
# SUBCOMMANDS (this is the contract — tests and callers branch on these):
#
#   verdict <sha>
#       Classify one commit. Prints one of:  tagged <ID> | exempt <reason> | untagged
#       exit 0 = tagged or exempt; exit 1 = untagged (a story commit missing its tag).
#
#   check-msg <msg-file>
#       Classify a commit MESSAGE read from a file (the commit-msg hook path).
#       Same verdict/exit contract as `verdict`.
#
#   check-range <git-range>
#       Validate every NON-MERGE commit in the range (e.g. good..bad). Prints each
#       offender. exit 0 = all tagged/exempt; exit 1 = at least one untagged.
#
#   recover <git-range> <culprit-sha>
#       RTE bisect recovery (PILOT-79 AC5). Given an untagged culprit and the
#       bisect range good..bad, resolve it to a story WITHOUT crashing the epic into
#       `Needs PO Decision`:
#         1. culprit itself tagged            -> print "child=<ID> via=self"
#         2. nearest TAGGED commit in
#            culprit..bad (earliest first)    -> print "child=<ID> via=next-tagged sha=<sha>"
#         3. enclosing MERGE commit whose
#            side brought the culprit in       -> print "child=<ID> via=merge sha=<merge>"
#         4. none of the above                 -> print "unresolved" (exit 3)
#       exit 0 = resolved (RTE reopens that story, forward-fix); exit 3 = truly
#       unresolvable (RTE falls back to Needs PO Decision — the last resort, not the
#       first). exit 64 = usage/bad range.
#
# The tag is prefix-AGNOSTIC on purpose (like merge-target-guard.sh): it matches
# any [A-Z][A-Z0-9]*-<digits> token, so the guard needs no AITBC baked
# in and works for PILOT-*, ABS-*, and any consumer's key.
#
# Pure + side-effect-free (only reads git + prints). bash 3.2 + BSD tools only.
# Invoked directly by tests/test-commit-tag-guard.sh and the commit-msg hook.
# =============================================================================
set -uo pipefail

die() { echo "commit-tag-guard: $*" >&2; exit 64; }

# A ticket tag: [KEY-NNN] with an uppercase-alnum key. Anchored to the [..] form
# so a bare "PILOT-66" in prose does NOT count (that is exactly the 4d70ec09 bug).
TAG_RE='\[[A-Z][A-Z0-9]*-[0-9]+\]'

# _tag_of <text> — echo the FIRST ticket id (KEY-NNN, brackets stripped) in <text>,
# or nothing. Reads stdin if no arg.
_tag_of() {
    local text="${1-}"
    [ $# -gt 0 ] || text="$(cat)"
    printf '%s' "$text" | grep -oE "$TAG_RE" | head -1 | tr -d '[]'
}

# _is_exempt <full-message> — 0 if the message belongs to the operator/release
# exempt class (b); prints the reason. 1 otherwise.
_is_exempt() {
    local msg="$1" subject
    subject="$(printf '%s' "$msg" | head -1)"
    case "$subject" in
        chore\(release*|chore\(governor*)
            echo "release-automation"; return 0 ;;
    esac
    if printf '%s' "$msg" | grep -q '\[no-ticket\]'; then
        echo "no-ticket-marker"; return 0
    fi
    return 1
}

# _verdict_of <full-message> — the shared classifier. Prints the verdict line and
# returns 0 (tagged/exempt) or 1 (untagged).
_verdict_of() {
    local msg="$1" id reason
    id="$(_tag_of "$msg")"
    if [ -n "$id" ]; then
        echo "tagged $id"; return 0
    fi
    if reason="$(_is_exempt "$msg")"; then
        echo "exempt $reason"; return 0
    fi
    echo "untagged"; return 1
}

cmd_verdict() {
    [ $# -eq 1 ] || die "usage: verdict <sha>"
    command -v git >/dev/null 2>&1 || die "git not found"
    local msg
    msg="$(git log -1 --format='%B' "$1" 2>/dev/null)" || die "no such commit: $1"
    _verdict_of "$msg"
}

cmd_check_msg() {
    [ $# -eq 1 ] || die "usage: check-msg <msg-file>"
    [ -f "$1" ] || die "no such message file: $1"
    # Strip git comment lines (the editor template) before classifying.
    local msg
    msg="$(grep -v '^#' "$1")"
    _verdict_of "$msg"
}

cmd_check_range() {
    [ $# -eq 1 ] || die "usage: check-range <git-range>"
    command -v git >/dev/null 2>&1 || die "git not found"
    local shas sha msg rc=0
    # --no-merges: merge commits carry no story work, never bisect culprits.
    shas="$(git rev-list --no-merges "$1" 2>/dev/null)" || die "bad range: $1"
    [ -n "$shas" ] && for sha in $shas; do
        msg="$(git log -1 --format='%B' "$sha" 2>/dev/null)"
        if ! _verdict_of "$msg" >/dev/null; then
            echo "untagged $sha $(git log -1 --format='%s' "$sha" 2>/dev/null)"
            rc=1
        fi
    done
    return $rc
}

cmd_recover() {
    [ $# -eq 2 ] || die "usage: recover <git-range> <culprit-sha>"
    command -v git >/dev/null 2>&1 || die "git not found"
    local range="$1" culprit="$2" bad id sha merge
    bad="${range##*..}"; [ -n "$bad" ] || bad="HEAD"
    git rev-parse --verify -q "$culprit^{commit}" >/dev/null 2>&1 || die "no such commit: $culprit"

    # 1. culprit itself tagged.
    id="$(git log -1 --format='%B' "$culprit" | _tag_of)"
    if [ -n "$id" ]; then echo "child=$id via=self"; return 0; fi

    # 2. nearest TAGGED commit among culprit..bad, earliest first (the rest of the
    #    same story's work carries the tag).
    for sha in $(git rev-list --reverse --ancestry-path "$culprit..$bad" 2>/dev/null); do
        id="$(git log -1 --format='%B' "$sha" | _tag_of)"
        if [ -n "$id" ]; then echo "child=$id via=next-tagged sha=$sha"; return 0; fi
    done

    # 3. enclosing MERGE commit: the first merge on the ancestry path that carries a
    #    tag (story MRs merge with a "[ID]" subject) — the surrounding merge commit.
    for merge in $(git rev-list --reverse --merges --ancestry-path "$culprit..$bad" 2>/dev/null); do
        id="$(git log -1 --format='%B' "$merge" | _tag_of)"
        if [ -n "$id" ]; then echo "child=$id via=merge sha=$merge"; return 0; fi
    done

    echo "unresolved"; return 3
}

[ $# -ge 1 ] || die "usage: commit-tag-guard.sh {verdict|check-msg|check-range|recover} ..."
sub="$1"; shift
case "$sub" in
    verdict)     cmd_verdict "$@" ;;
    check-msg)   cmd_check_msg "$@" ;;
    check-range) cmd_check_range "$@" ;;
    recover)     cmd_recover "$@" ;;
    *)           die "unknown subcommand: $sub" ;;
esac
