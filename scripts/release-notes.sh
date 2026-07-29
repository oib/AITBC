#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# release-notes.sh — structured release notes from a HARNESS_CHANGELOG entry
# =============================================================================
# Turns one HARNESS_CHANGELOG.yml release entry into the two artifacts humans
# actually look at, in the v2.24.1 reference format (ABS-226):
#
#   page <version>          -> Confluence page body (storage/XHTML): info panel,
#                              change table with ticket links + category chips,
#                              operations/migration notes. Governor-only patches
#                              (changes: []) degrade to a summary-only stub page.
#   description <version>    -> the Jira version-description text: a Confluence
#                              link on line 1 (when --page-url is given) plus the
#                              one-paragraph summary.
#   publish <version>        -> LIVE: render the page, create/update it in the
#                              Confluence ADB space under a "Release Notes" parent
#                              via the Confluence REST API (curl, v2, storage
#                              format), then stamp the Jira version-description
#                              with the page link via jira-version.sh release
#                              --description-file. Confluence-unreachable degrades
#                              to a WARN (no abort): the release still proceeds.
#
# DESIGN DECISION (ABS-226 scope item 3): Confluence writes go through curl
# against the Confluence REST API (v2, storage format), NOT the Atlassian MCP
# server. Rationale: (1) headless orchestrator seats have no MCP — the sanctioned
# Atlassian path is curl with a mode-600 --config file (see jira-version.sh /
# jira-tracker.sh); (2) the confluence-docs skill explicitly does not publish via
# MCP; (3) reuses the exact human-provisioned Keychain creds already used for
# Jira (JIRA_EMAIL + JIRA_API_TOKEN on the same *.atlassian.net site). NO new
# secrets enter the repo.
#
# Rendering (page/description) is PURE and offline — no network, no creds — so it
# is covered by a golden-file fixture test (tests/test-release-notes.sh). Only
# `publish` touches the live APIs, and that stays in the operator's release train
# (ADR-A-0004), mirroring jira-version.sh's "printed HUMAN follow-up" contract.
#
# Environment (publish only; human-provisioned, identical to jira-version.sh):
#   JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN         Atlassian auth (Confluence lives
#                                                 at $JIRA_SITE/wiki)
#   CONFLUENCE_SPACE_KEY   (default: ADB)         target space
#   CONFLUENCE_PARENT_TITLE (default: "Release Notes")
#                                                 parent page the notes nest under
#   CONFLUENCE_CURL        (default: curl)        test seam
#
# bash 3.2 + python3 (PyYAML). Token safety mirrors jira-version.sh: the token
# reaches curl only via a mode-600 --config file, never argv, never output.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_CHANGELOG="$PROJECT_ROOT/HARNESS_CHANGELOG.yml"

die() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }

# --- shared arg state ---------------------------------------------------------
MODE=""
VERSION=""
CHANGELOG="$DEFAULT_CHANGELOG"
JIRA_BASE="${JIRA_SITE:-}"
PAGE_URL=""

usage() {
    cat <<'USAGE'
usage: release-notes.sh <command> <version> [options]

commands:
  page <version>          emit the Confluence page body (storage/XHTML) to stdout
  description <version>    emit the Jira version-description text to stdout
  publish <version>        render + create/update the Confluence page and stamp
                           the Jira version-description (live; needs creds)

options:
  --changelog <file>       changelog to read (default: HARNESS_CHANGELOG.yml)
  --jira-base <url>        base for ticket links, e.g. https://x.atlassian.net
                           (default: $JIRA_SITE; omitted -> ticket refs stay plain)
  --page-url <url>         Confluence page URL to link from the description
                           (description/publish)
USAGE
}

# The Python renderer — emitted once to a temp file, invoked for page/description.
render_py() {
    cat <<'PYEOF'
import sys, os, re, html
try:
    import yaml
except Exception:
    sys.stderr.write("ERROR: PyYAML is required (python3 -m pip install pyyaml)\n")
    sys.exit(2)

mode      = os.environ["RN_MODE"]
version   = os.environ["RN_VERSION"].lstrip("v")
changelog = os.environ["RN_CHANGELOG"]
jira_base = os.environ.get("RN_JIRA_BASE", "").rstrip("/")
page_url  = os.environ.get("RN_PAGE_URL", "")

with open(changelog) as fh:
    data = yaml.safe_load(fh) or {}

entry = None
for rel in data.get("releases", []) or []:
    if str(rel.get("version", "")).lstrip("v") == version:
        entry = rel
        break
if entry is None:
    sys.stderr.write("ERROR: version '%s' not found in %s\n" % (version, changelog))
    sys.exit(3)

summary = entry.get("summary", "") or ""
date    = entry.get("date", "") or ""
changes = entry.get("changes", []) or []
mnotes  = entry.get("migration_notes", []) or []

# Category -> chip colour (Confluence status-macro palette). Covers the schema
# enum plus the extra categories the live changelog uses (AGENT/SKILL/DOCS).
COLOURS = {
    "NEW_FILE": "Green", "METHODOLOGY": "Purple", "AGENT": "Purple",
    "UPDATED_FILE": "Blue", "SKILL": "Blue", "DOCS": "Blue",
    "CONFIG": "Grey", "BREAKING": "Red",
}

TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

def esc(s):
    return html.escape(str(s), quote=True)

def linkify(text):
    # text is already HTML-escaped; ticket tokens contain no special chars.
    if not jira_base:
        return text
    return TICKET_RE.sub(
        lambda m: '<a href="%s/browse/%s">%s</a>' % (jira_base, m.group(1), m.group(1)),
        text,
    )

def chip(category):
    colour = COLOURS.get(category, "Grey")
    return ('<ac:structured-macro ac:name="status">'
            '<ac:parameter ac:name="colour">%s</ac:parameter>'
            '<ac:parameter ac:name="title">%s</ac:parameter>'
            '</ac:structured-macro>') % (colour, esc(category))

def emit_description():
    out = []
    if page_url:
        out.append("Release notes: %s" % page_url)
        out.append("")
    out.append(summary)
    sys.stdout.write("\n".join(out) + "\n")

def emit_page():
    L = []
    # Info panel: version, date, one-paragraph summary.
    L.append('<ac:structured-macro ac:name="info"><ac:rich-text-body>')
    L.append('<p><strong>Version %s</strong> &middot; released %s</p>' % (esc(version), esc(date)))
    L.append('<p>%s</p>' % linkify(esc(summary)))
    L.append('</ac:rich-text-body></ac:structured-macro>')

    if not changes:
        # AC5: governor-only patch -> summary-only stub page.
        L.append('<p>Governor-only patch release &mdash; no <code>.claude/</code> '
                 'harness file changes. This page exists for tag/changelog parity.</p>')
        sys.stdout.write("\n".join(L) + "\n")
        return

    # Change table: File | Category | Change | Breaking | Details (ticket-linked).
    L.append('<h2>Changes</h2>')
    L.append('<table><tbody>')
    L.append('<tr>'
             '<th>File</th><th>Category</th><th>Change</th>'
             '<th>Breaking</th><th>Details</th>'
             '</tr>')
    for c in changes:
        path        = esc(c.get("path", ""))
        category    = c.get("category", "")
        change_type = esc(c.get("change_type", ""))
        breaking    = "Yes" if c.get("breaking") else "No"
        details     = linkify(esc(c.get("description", "")))
        renamed     = c.get("renamed_from")
        if renamed:
            details += ' <em>(from <code>%s</code>)</em>' % esc(renamed)
        L.append('<tr>'
                 '<td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                 '</tr>' % (path, chip(category), change_type, breaking, details))
    L.append('</tbody></table>')

    # Operations notes ("Betriebsnotizen"): migration notes when present.
    L.append('<h2>Operations notes</h2>')
    if mnotes:
        L.append('<ul>')
        for n in mnotes:
            L.append('<li>%s</li>' % linkify(esc(n)))
        L.append('</ul>')
    else:
        L.append('<p>No migration steps &mdash; backward-compatible release.</p>')

    sys.stdout.write("\n".join(L) + "\n")

if mode == "page":
    emit_page()
elif mode == "description":
    emit_description()
else:
    sys.stderr.write("ERROR: unknown render mode '%s'\n" % mode)
    sys.exit(4)
PYEOF
}

run_render() {
    local mode="$1"
    local tmp
    tmp="$(mktemp)"
    render_py > "$tmp"
    RN_MODE="$mode" RN_VERSION="$VERSION" RN_CHANGELOG="$CHANGELOG" \
        RN_JIRA_BASE="$JIRA_BASE" RN_PAGE_URL="$PAGE_URL" \
        python3 "$tmp"
    local rc=$?
    rm -f "$tmp"
    return $rc
}

# --- publish (live) -----------------------------------------------------------
cmd_publish() {
    local site="${JIRA_SITE:-}" email="${JIRA_EMAIL:-}" token="${JIRA_API_TOKEN:-}"
    local space="${CONFLUENCE_SPACE_KEY:-ADB}"
    local parent_title="${CONFLUENCE_PARENT_TITLE:-Release Notes}"
    local curl_bin="${CONFLUENCE_CURL:-curl}"

    [ -n "$site" ]  || die "publish: JIRA_SITE is not set"
    [ -n "$email" ] || die "publish: JIRA_EMAIL is not set"
    [ -n "$token" ] || die "publish: JIRA_API_TOKEN is not set"

    [ -n "$JIRA_BASE" ] || JIRA_BASE="$site"
    local wiki="$site/wiki"
    local title="Release $VERSION"

    # Render the page body first (offline, deterministic).
    local body_file
    body_file="$(mktemp)"
    run_render page > "$body_file" || { rm -f "$body_file"; die "publish: page render failed"; }

    # cfg holds the credential out-of-band (mode 600, never argv/output).
    local cfg
    cfg="$(mktemp)"; chmod 600 "$cfg"
    printf 'user = "%s:%s"\n' "$email" "$token" > "$cfg"

    # cwrite <METHOD> <path> [json-body-file] -> prints "<http_code>\n<json>" or
    # empty on transport failure. Confluence-unreachable is a soft failure.
    cwrite() {
        local method="$1" path="$2" bodyfile="${3:-}"
        local out
        set -- -sS --config "$cfg" -H "Accept: application/json" \
            -w '\n%{http_code}' -X "$method" "$wiki$path"
        if [ -n "$bodyfile" ]; then
            set -- "$@" -H "Content-Type: application/json" --data-binary "@$bodyfile"
        fi
        out="$("$curl_bin" "$@" 2>/dev/null)" || return 1
        printf '%s' "$out"
    }

    # Resolve space id + parent page id (best-effort; failures degrade to WARN).
    local space_json space_id parent_id page_json page_body_json page_url

    space_json="$(cwrite GET "/api/v2/spaces?keys=$space" || true)"
    space_id="$(printf '%s' "$space_json" | sed $'$d' | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin); print((d.get("results") or [{}])[0].get("id",""))
except Exception:
    pass' 2>/dev/null || true)"

    if [ -z "$space_id" ]; then
        warn "publish: could not reach/resolve Confluence space '$space' — skipping page creation (release proceeds; create the page by hand from the rendered body)."
        rm -f "$cfg" "$body_file"
        _publish_stamp_description ""
        return 0
    fi

    parent_id="$(printf '%s' "$(cwrite GET "/api/v2/spaces/$space_id/pages?title=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$parent_title")" || true)" | sed $'$d' | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin); print((d.get("results") or [{}])[0].get("id",""))
except Exception:
    pass' 2>/dev/null || true)"

    # Build the create-page JSON (storage representation) from the body file.
    page_body_json="$(mktemp)"
    python3 - "$space_id" "$title" "$parent_id" "$body_file" > "$page_body_json" <<'PYEOF'
import sys, json
space_id, title, parent_id, body_file = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(body_file) as fh:
    body = fh.read()
obj = {
    "spaceId": space_id,
    "status": "current",
    "title": title,
    "body": {"representation": "storage", "value": body},
}
if parent_id:
    obj["parentId"] = parent_id
json.dump(obj, sys.stdout)
PYEOF

    page_json="$(cwrite POST "/api/v2/pages" "$page_body_json" || true)"
    rm -f "$page_body_json"
    local code
    code="$(printf '%s' "$page_json" | tail -n1)"
    if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        page_url="$(printf '%s' "$page_json" | sed $'$d' | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    base = d.get("_links",{}).get("base","")
    webui = d.get("_links",{}).get("webui","")
    print(base + webui if webui else "")
except Exception:
    pass' 2>/dev/null || true)"
        echo "published Confluence page: ${page_url:-<created>}"
    else
        warn "publish: Confluence page create returned HTTP ${code:-?} — skipping (release proceeds; create the page by hand from the rendered body)."
        page_url=""
    fi

    rm -f "$cfg" "$body_file"
    _publish_stamp_description "$page_url"
}

# Stamp the Jira version-description via jira-version.sh (atomic with release).
_publish_stamp_description() {
    local page_url="$1"
    local desc_file
    desc_file="$(mktemp)"
    PAGE_URL="$page_url" run_render description > "$desc_file" || { rm -f "$desc_file"; die "publish: description render failed"; }
    bash "$SCRIPT_DIR/jira-version.sh" release "$VERSION" --description-file "$desc_file"
    rm -f "$desc_file"
    echo "NOTE: 'Add related work' on the Jira release page is not API-settable — add it by hand (ABS-226)."
}

# -----------------------------------------------------------------------------
# Parse args
# -----------------------------------------------------------------------------
[ $# -ge 1 ] || { usage >&2; exit 1; }
MODE="$1"; shift
case "$MODE" in
    page|description|publish) ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown command '$MODE' (page|description|publish)" ;;
esac

[ $# -ge 1 ] || die "$MODE: version required"
VERSION="$1"; shift
while [ $# -gt 0 ]; do
    case "$1" in
        --changelog) [ $# -ge 2 ] || die "$MODE: --changelog requires a value"; CHANGELOG="$2"; shift 2 ;;
        --jira-base) [ $# -ge 2 ] || die "$MODE: --jira-base requires a value"; JIRA_BASE="$2"; shift 2 ;;
        --page-url)  [ $# -ge 2 ] || die "$MODE: --page-url requires a value"; PAGE_URL="$2"; shift 2 ;;
        *) die "$MODE: unknown argument '$1'" ;;
    esac
done

[ -f "$CHANGELOG" ] || die "$MODE: changelog '$CHANGELOG' not found"

case "$MODE" in
    page)        run_render page ;;
    description) run_render description ;;
    publish)     cmd_publish ;;
esac
