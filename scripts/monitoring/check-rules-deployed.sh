#!/bin/bash
# check-rules-deployed.sh — flag drift between deployed Prometheus rule
# files (/etc/prometheus/*.yml) and the checked-in copies in this repo.
#
# Prometheus on a monitored host reads rule files from /etc/prometheus, and
# those files are hand-copied from scripts/monitoring/ — they are copies,
# not symlinks, so they can silently go stale (OPS-1 found exactly that).
# This check is the tripwire: read-only, prints only the names of files
# that differ or are missing, exits 1 on any difference, 0 if all match.
#
# It also catches the inverse drift (#915): a repo rule file whose deployed
# copy exists under the deployed dir but which prometheus.yml does NOT list
# in rule_files — the file sits on disk yet Prometheus never loads it. A
# repo rule file with no deployed copy on this host is skipped (e.g.
# aitbc_hub_rules.yml legitimately exists only where its timer runs).
#
# Deploy step for operators (this script never writes):
#   scripts/monitoring/deploy-rules.sh    # copy + promtool check + reload
# or by hand:
#   1. cp scripts/monitoring/<name>.yml /etc/prometheus/<name>.yml
#   2. promtool check rules /etc/prometheus/<name>.yml
#   3. systemctl reload prometheus        # authorized reloads only
#
# Usage: check-rules-deployed.sh [--live] [deployed-dir] [prometheus.yml]
#   deployed-dir defaults to /etc/prometheus; prometheus.yml inside it is
#   used to derive the rule-file list. If it is absent/unreadable the
#   check falls back to the repo's two known rule files.
#   --live additionally compares listed repo rule files against the groups
#   Prometheus reports loaded via ${PROMETHEUS_API:-http://127.0.0.1:9090}
#   /api/v1/rules; exits 2 when the API is unreachable or unparseable.

set -euo pipefail

LIVE=false
while [ "${1:-}" = "--live" ]; do
    LIVE=true
    shift
done

DEPLOYED_DIR="${1:-/etc/prometheus}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PROM_YML="${2:-$DEPLOYED_DIR/prometheus.yml}"

rule_files=""
if [ -r "$PROM_YML" ]; then
    # Lines under "rule_files:" look like:  - aitbc_rules.yml
    rule_files=$(sed -n '/^rule_files:/,/^[a-z_]/p' "$PROM_YML" | sed -n 's/^ *- *\([^ ]*\.yml\).*/\1/p')
fi
if [ -z "$rule_files" ]; then
    rule_files="aitbc_rules.yml aitbc_hub_rules.yml"
fi

# Basename-normalized list of rule files prometheus.yml loads (entries may
# be absolute paths, e.g. node0's /etc/prometheus/alerts.yml).
listed_bases=" "
for name in $rule_files; do
    listed_bases="$listed_bases$(basename "$name") "
done
is_listed() {
    case "$listed_bases" in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

diffs=0
for name in $rule_files; do
    base="$(basename "$name")"
    repo_file="$REPO_DIR/$base"
    # Entries may be absolute paths (node0 lists /etc/prometheus/alerts.yml);
    # join only relative names onto the deployed dir.
    case "$name" in
        /*) deployed="$name" ;;
        *)  deployed="$DEPLOYED_DIR/$name" ;;
    esac
    if [ ! -f "$repo_file" ]; then
        # Host-local rule files with no repo counterpart are legitimate —
        # deploy-rules.sh skips them; flagging them here is not drift.
        echo "$base (skipped — no repo file)" >&2
        continue
    fi
    if [ ! -f "$deployed" ]; then
        echo "$base (missing)"
        diffs=1
        continue
    fi
    if ! cmp -s "$repo_file" "$deployed"; then
        echo "$base"
        diffs=1
    fi
done

# Inverse drift: a repo rule file deployed on this host but absent from
# rule_files is on disk yet never loaded by Prometheus (#915).
shopt -s nullglob
for repo_rule in "$REPO_DIR"/*_rules.yml; do
    base="$(basename "$repo_rule")"
    is_listed "$base" && continue
    if [ -f "$DEPLOYED_DIR/$base" ]; then
        echo "$base (deployed but not in rule_files)"
        diffs=1
    else
        echo "$base (not deployed on this host — skipped)" >&2
    fi
done

if $LIVE; then
    api="${PROMETHEUS_API:-http://127.0.0.1:9090}/api/v1/rules"
    if ! rules_json=$(curl -fsS -m 5 "$api" 2>/dev/null); then
        echo "check-rules-deployed: --live cannot reach $api" >&2
        exit 2
    fi
    if ! loaded_files=$(printf '%s' "$rules_json" | python3 -c '
import json, os, sys
d = json.load(sys.stdin)
for g in d.get("data", {}).get("groups", []):
    f = g.get("file") or ""
    if f:
        print(os.path.basename(f))
'); then
        echo "check-rules-deployed: --live returned unparseable rules JSON from $api" >&2
        exit 2
    fi
    for name in $rule_files; do
        base="$(basename "$name")"
        [ -f "$REPO_DIR/$base" ] || continue
        if ! printf '%s\n' "$loaded_files" | grep -qxF "$base"; then
            echo "$base (listed but not loaded)"
            diffs=1
        fi
    done
fi

exit "$diffs"
