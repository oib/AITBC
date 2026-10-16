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
# Deploy step for operators (this script never writes):
#   scripts/monitoring/deploy-rules.sh    # copy + promtool check + reload
# or by hand:
#   1. cp scripts/monitoring/<name>.yml /etc/prometheus/<name>.yml
#   2. promtool check rules /etc/prometheus/<name>.yml
#   3. systemctl reload prometheus        # authorized reloads only
#
# Usage: check-rules-deployed.sh [deployed-dir] [prometheus.yml]
#   deployed-dir defaults to /etc/prometheus; prometheus.yml inside it is
#   used to derive the rule-file list. If it is absent/unreadable the
#   check falls back to the repo's two known rule files.

set -euo pipefail

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
exit "$diffs"
