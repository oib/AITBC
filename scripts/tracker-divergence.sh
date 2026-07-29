#!/usr/bin/env bash
set -uo pipefail

# =============================================================================
# Tracker Divergence Reporter (epic ABS-326, story ABS-328 / Koexistenz S2)
# =============================================================================
# READ-ONLY diff of the fenced ticket set between the primary tracker (Jira,
# scripts/jira-tracker.sh) and the shadow mirror (v3 backend,
# scripts/backend-tracker.sh). Produces a human-readable Markdown report and a
# machine-readable JSON report in the state dir, plus one append-only history
# line per run — the evidence stream for the Shadow->Pilot gate ("N days
# without an unexplained divergence entry", see the epic and
# docs/sop/TRACKER-MIGRATION-RUNBOOK.md).
#
# What is compared, per ticket in the fence:
#   presence (exists on both sides), type, title, status, parent, lane,
#   priority, role, flags, labels, ac_blocking, depends_on, links,
#   comment count, fixVersion (Jira-side sweep; see below).
#
# Fence: the ticket set is enumerated through the primary adapter's `search`,
# which is fenced by the adapter's own env (JIRA_PROJECT_KEY +
# JIRA_JQL_FILTER) — i.e. the run's JQL fence IS the reporter's input, no
# second fence definition to drift. Enumeration is PRIMARY-ONLY by design:
# during shadow, Jira is the source of truth and the question is "does the
# backend faithfully mirror the fence?". A fenced ticket the mirror cannot
# `get` is a `presence` divergence; backend tickets OUTSIDE the Jira fence
# are out of scope (a fence narrower than the backend's project would
# otherwise report permanent false positives and wedge the >=N-days-clean
# gate).
#
# fixVersion: the canonical adapter `get` does not carry fixVersion (adapter
# gap, ABS-330), so the Jira side is swept with ONE read-only query against
# POST /rest/api/3/search/jql (fields=fixVersions) — the same query endpoint
# the Jira adapter uses for every search; it reads, never writes. The v3
# backend has no fixVersion field at all, so any fenced ticket carrying one
# in Jira is a PERMANENT, EXPLAINED divergence covered by the built-in
# whitelist rule (see below). When the Jira env (JIRA_SITE/JIRA_EMAIL/
# JIRA_API_TOKEN) is absent — e.g. sandbox runs against stub adapters — the
# fixVersion sweep is skipped and the field is not compared.
#
# Whitelist (explained divergences): entries mark a divergence as explained —
# it is still listed in the report (flagged `explained`, with its reason) but
# does NOT drive the exit code. One entry per line:
#     <key-glob>|<field-glob>|<reason>
# e.g.   ABS-12*|labels|migration backfill pending (ABS-341)
# `#` lines and blank lines are ignored; globs are shell-style (fnmatch).
# Built-in rule (always active, listed in every report):
#     *|fixVersion|known field gap: v3 backend has no fixVersion field
#
# Exit codes (cron-/watcher-suitable gate semantics):
#     0  no divergence, or every divergence explained
#     1  at least one UNEXPLAINED divergence
#     2  usage / environment / adapter error
#
# Read-only guarantee (AC): this script invokes ONLY the read verbs `search`
# and `get` on either adapter, plus the one fixVersion query above. It never
# passes a mutating verb to any adapter and issues no writing HTTP call —
# auditable via tests/test-tracker-divergence.sh (endpoint/verb audit).
#
# Env:
#   DIVERGENCE_PRIMARY_CMD  primary adapter (default scripts/jira-tracker.sh)
#   DIVERGENCE_MIRROR_CMD   mirror adapter  (default scripts/backend-tracker.sh)
#   DIVERGENCE_STATE_DIR    report dir      (default work/divergence, gitignored)
#   DIVERGENCE_WHITELIST    extra whitelist file (default
#                           work/tracker-divergence-whitelist.txt; optional)
#   DIVERGENCE_CURL         curl binary/shim for the fixVersion sweep
#                           (default curl — offline-test seam, like JIRA_CURL)
# The adapters read their own env (JIRA_*, BACKEND_*) untouched.
#
# Usage: scripts/tracker-divergence.sh [--help]
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PRIMARY_CMD="${DIVERGENCE_PRIMARY_CMD:-$REPO_ROOT/scripts/jira-tracker.sh}"
MIRROR_CMD="${DIVERGENCE_MIRROR_CMD:-$REPO_ROOT/scripts/backend-tracker.sh}"
STATE_DIR="${DIVERGENCE_STATE_DIR:-$REPO_ROOT/work/divergence}"
WHITELIST="${DIVERGENCE_WHITELIST:-$REPO_ROOT/work/tracker-divergence-whitelist.txt}"
CURL_BIN="${DIVERGENCE_CURL:-curl}"

die() { echo "ERROR: $*" >&2; exit 2; }

case "${1:-}" in
    -h|--help|help)
        sed -n '4,70p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    "") : ;;
    *) die "unknown argument: $1 (this reporter takes no arguments; config is env-only)" ;;
esac

command -v python3 >/dev/null 2>&1 || die "python3 is required (harness prerequisite)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tracker-divergence.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/primary" "$WORK/mirror"

# --- Enumerate the fence (READ: primary search; see header on primary-only) --
"$PRIMARY_CMD" search > "$WORK/primary-search.tsv" \
    || die "primary adapter search failed ($PRIMARY_CMD)"

# Keys = col 1 of the canonical id<TAB>type<TAB>status<TAB>title lines.
cut -f1 "$WORK/primary-search.tsv" 2>/dev/null \
    | awk 'NF' | sort -u > "$WORK/keys.txt"

# --- Collect canonical dumps per side (READ: get) ----------------------------
# A failing `get` on one side is recorded as absence (presence divergence),
# not a reporter abort — that IS the finding.
while IFS= read -r key; do
    [ -n "$key" ] || continue
    "$PRIMARY_CMD" get "$key" > "$WORK/primary/$key.md" 2>/dev/null \
        || rm -f "$WORK/primary/$key.md"
    "$MIRROR_CMD" get "$key" > "$WORK/mirror/$key.md" 2>/dev/null \
        || rm -f "$WORK/mirror/$key.md"
done < "$WORK/keys.txt"

# --- fixVersion sweep (Jira side only; read-only, paged) ---------------------
# Only when the live-Jira env is present; stub/sandbox runs skip it. ABS-364: the
# /search/jql endpoint caps a page at maxResults=100 and returns a nextPageToken
# when more remain — page through ALL of them so a fence >100 tickets is swept in
# full instead of silently truncating at the first page (which would drop the
# fixVersion comparison for every ticket past #100).
FIXV_JSON=""
if [ -n "${JIRA_SITE:-}" ] && [ -n "${JIRA_EMAIL:-}" ] && [ -n "${JIRA_API_TOKEN:-}" ] \
        && [ -n "${JIRA_PROJECT_KEY:-}" ]; then
    jql="project = ${JIRA_PROJECT_KEY}"
    [ -z "${JIRA_JQL_FILTER:-}" ] || jql="$jql AND (${JIRA_JQL_FILTER})"
    # Token via --config, never argv (same secret hygiene as jira-tracker.sh).
    curlcfg="$WORK/curl.cfg"
    printf 'user = "%s:%s"\n' "$JIRA_EMAIL" "$JIRA_API_TOKEN" > "$curlcfg"

    next_token=""
    page=0
    sweep_ok=1
    while :; do
        page=$((page + 1))
        # nextPageToken is not a secret — build the body with python (json-safe),
        # keep only the credential in the curl --config file.
        payload="$(JQL="$jql" NEXT="$next_token" python3 -c 'import json,os
b = {"jql": os.environ["JQL"], "maxResults": 100, "fields": ["fixVersions"]}
n = os.environ.get("NEXT", "")
if n:
    b["nextPageToken"] = n
print(json.dumps(b))')"
        pagefile="$WORK/fixv-page-$page.json"
        if "$CURL_BIN" -sS --fail-with-body --config "$curlcfg" \
                -H "Content-Type: application/json" \
                -X POST "${JIRA_SITE%/}/rest/api/3/search/jql" \
                -d "$payload" > "$pagefile" 2>"$WORK/fixversions.err"; then
            # Next page token (empty/absent => last page). A parse failure here is
            # treated as "no more pages" rather than a crash.
            next_token="$(python3 -c 'import json,sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); sys.exit(0)
print(d.get("nextPageToken") or "")' "$pagefile")"
        else
            echo "WARNING: fixVersion sweep failed (page $page) — field skipped this run:" >&2
            sed 's/^/  /' "$WORK/fixversions.err" >&2 || true
            sweep_ok=0
            break
        fi
        [ -n "$next_token" ] || break
        if [ "$page" -ge 1000 ]; then
            echo "WARNING: fixVersion sweep hit the 1000-page safety cap — results may be truncated" >&2
            break
        fi
    done
    rm -f "$curlcfg"

    if [ "$sweep_ok" -eq 1 ]; then
        # Merge every page's issues into one {"issues":[...]} document (the shape
        # the report step already consumes). The page files are passed as argv
        # (glob), never stdin — python3 `-` already reads the program from stdin.
        # Guard it: a merge failure downgrades to "sweep skipped", never a crash.
        if python3 -c '
import json, sys
out = sys.argv[1]
issues = []
for p in sys.argv[2:]:
    with open(p) as fh:
        issues.extend(json.load(fh).get("issues", []) or [])
with open(out, "w") as fh:
    json.dump({"issues": issues}, fh)
' "$WORK/fixversions.json" "$WORK"/fixv-page-*.json; then
            FIXV_JSON="$WORK/fixversions.json"
        else
            echo "WARNING: fixVersion page merge failed — field skipped this run." >&2
        fi
    fi
fi

# --- Diff + report (python: parse frontmatter, whitelist, emit md/json) ------
mkdir -p "$STATE_DIR"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$WORK" "$STATE_DIR" "$NOW" "$WHITELIST" "$FIXV_JSON" <<'PYEOF'
import sys, os, json, glob, fnmatch

# ABS-364: crash != divergence. An UNCAUGHT exception in the reporter (a bug, a
# malformed fixtures file, an environment fault) must exit 2 (ERROR), never the
# interpreter's default 1 — which the bash wrapper reads as "unexplained
# divergence" and would gate on. A genuine divergence verdict still uses
# sys.exit(1) below (SystemExit bypasses the excepthook), so the three exit
# semantics stay disjoint: 0 clean, 1 unexplained divergence, 2 error.
def _crash_to_error(exc_type, exc, tb):
    import traceback
    traceback.print_exception(exc_type, exc, tb)
    sys.stderr.write("ERROR: divergence reporter crashed (uncaught exception) -> exit 2\n")
    sys.stderr.flush()
    os._exit(2)
sys.excepthook = _crash_to_error

work, state_dir, now, whitelist_path, fixv_path = sys.argv[1:6]

# Fault-injection seam for the crash-vs-divergence test (ABS-364): a set env var
# forces an internal reporter failure so the test can assert it exits 2, not 1.
if os.environ.get("DIVERGENCE_SELFTEST_RAISE"):
    raise RuntimeError("injected reporter failure (DIVERGENCE_SELFTEST_RAISE, ABS-364)")

BUILTIN_WHITELIST = [
    ("*", "fixVersion", "known field gap: v3 backend has no fixVersion field"),
]

def load_whitelist(path):
    rules = list(BUILTIN_WHITELIST)
    if path and os.path.isfile(path):
        with open(path) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                parts = ln.split("|", 2)
                if len(parts) != 3:
                    sys.stderr.write("WARNING: malformed whitelist line ignored: %s\n" % ln)
                    continue
                rules.append(tuple(p.strip() for p in parts))
    return rules

def explain(rules, key, field):
    for kglob, fglob, reason in rules:
        if fnmatch.fnmatch(key, kglob) and fnmatch.fnmatch(field, fglob):
            return reason
    return None

FIELDS = ["type", "title", "status", "parent", "lane", "priority", "role",
          "flags", "labels", "ac_blocking", "depends_on", "links"]

def parse_dump(path):
    """Parse a canonical adapter `get` dump: frontmatter fields + comment count."""
    t = {"comment_count": 0}
    in_fm = False
    fm_done = False
    in_comments = False
    with open(path) as fh:
        for ln in fh:
            ln = ln.rstrip("\n")
            if ln == "---" and not fm_done:
                if in_fm:
                    in_fm, fm_done = False, True
                else:
                    in_fm = True
                continue
            if in_fm and ":" in ln:
                k, _, v = ln.partition(":")
                t[k.strip()] = v.strip()
                continue
            if ln.strip() == "## Comments":
                in_comments = True
                continue
            if in_comments and ln.startswith("### "):
                t["comment_count"] += 1
    return t

def side(name):
    out = {}
    for p in sorted(glob.glob(os.path.join(work, name, "*.md"))):
        key = os.path.basename(p)[:-3]
        out[key] = parse_dump(p)
    return out

primary = side("primary")
mirror = side("mirror")

fixversions = None  # None = sweep skipped; {} = swept, values per key
if fixv_path:
    with open(fixv_path) as fh:
        data = json.load(fh)
    fixversions = {}
    for issue in data.get("issues", []):
        names = [v.get("name", "") for v in (issue.get("fields", {}) or {}).get("fixVersions", []) or []]
        fixversions[issue.get("key", "")] = ", ".join(sorted(n for n in names if n))

rules = load_whitelist(whitelist_path)
keys = sorted(set(primary) | set(mirror))

entries = []   # {key, field, primary, mirror, explained: reason|None}
def add(key, field, pv, mv):
    entries.append({"key": key, "field": field, "primary": pv, "mirror": mv,
                    "explained": explain(rules, key, field)})

for key in keys:
    p, m = primary.get(key), mirror.get(key)
    if p is None or m is None:
        add(key, "presence",
            "present" if p is not None else "MISSING",
            "present" if m is not None else "MISSING")
        continue
    for f in FIELDS:
        pv, mv = p.get(f, ""), m.get(f, "")
        if pv != mv:
            add(key, f, pv, mv)
    if p["comment_count"] != m["comment_count"]:
        add(key, "comment_count", str(p["comment_count"]), str(m["comment_count"]))
    if fixversions is not None:
        fv = fixversions.get(key, "")
        if fv:
            add(key, "fixVersion", fv, "(no field)")

unexplained = [e for e in entries if not e["explained"]]
explained = [e for e in entries if e["explained"]]

# --- JSON report -------------------------------------------------------------
report = {
    "generated_at": now,
    "tickets_compared": len(keys),
    "fixversion_swept": fixversions is not None,
    "divergences": entries,
    "unexplained_count": len(unexplained),
    "explained_count": len(explained),
    "gate_clean": not unexplained,
}
with open(os.path.join(state_dir, "report.json"), "w") as fh:
    json.dump(report, fh, indent=2, sort_keys=True)
    fh.write("\n")

# --- Markdown report -----------------------------------------------------------
def md_table(rows):
    out = ["| Ticket | Field | Primary (Jira) | Mirror (backend) | Explained |",
           "|---|---|---|---|---|"]
    for e in rows:
        cells = [e["key"], e["field"], e["primary"] or "(empty)", e["mirror"] or "(empty)",
                 e["explained"] or "**NO**"]
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(out)

md = ["# Tracker Divergence Report", "",
      "- Generated: %s" % now,
      "- Tickets compared (fence union): %d" % len(keys),
      "- fixVersion swept: %s" % ("yes" if fixversions is not None else "no (Jira env absent)"),
      "- Divergences: %d (%d unexplained, %d explained)"
      % (len(entries), len(unexplained), len(explained)),
      "- Gate verdict: %s" % ("CLEAN (exit 0)" if not unexplained else "UNEXPLAINED DIVERGENCE (exit 1)"),
      ""]
if unexplained:
    md += ["## Unexplained divergences", "", md_table(unexplained), ""]
if explained:
    md += ["## Explained divergences (whitelisted — do not gate)", "", md_table(explained), ""]
if not entries:
    md += ["No divergences. Both trackers agree on every compared field.", ""]
md += ["## Active whitelist rules", ""]
for kglob, fglob, reason in rules:
    md.append("- `%s|%s` — %s" % (kglob, fglob, reason))
md.append("")
with open(os.path.join(state_dir, "report.md"), "w") as fh:
    fh.write("\n".join(md))

# --- History line (append-only; the ">=N days clean" gate evidence) -----------
with open(os.path.join(state_dir, "history.log"), "a") as fh:
    fh.write("%s tickets=%d divergent=%d unexplained=%d\n"
             % (now, len(keys), len(entries), len(unexplained)))

sys.exit(1 if unexplained else 0)
PYEOF
rc=$?

case "$rc" in
    0) echo "divergence: CLEAN — report in $STATE_DIR/report.md" ;;
    1) echo "divergence: UNEXPLAINED entries found — report in $STATE_DIR/report.md" >&2 ;;
    *) die "report generation failed (rc=$rc)" ;;
esac
exit "$rc"
