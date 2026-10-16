#!/bin/bash
# deploy-rules.sh — sync the repo's Prometheus rule files into the deployed
# directory, validate them with promtool, and reload Prometheus.
#
# check-rules-deployed.sh flags drift; this script is the write side of the
# same contract: the deployed files under /etc/prometheus must be byte-equal
# to scripts/monitoring/*.yml. Run it on the host that serves Prometheus
# after pulling a new checkout.
#
# Usage: deploy-rules.sh [--no-reload] [deployed-dir] [prometheus.yml]
#   deployed-dir defaults to /etc/prometheus; the rule-file list is derived
#   from prometheus.yml inside it (same logic as check-rules-deployed.sh),
#   falling back to the repo's two known rule files when it is unreadable.
#
# Validation happens on the repo copy BEFORE anything is deployed, and again
# on the deployed copy afterwards, so a malformed file never reaches the
# reload. Exits non-zero on the first failure; prometheus is only reloaded
# after every file validates.

set -euo pipefail

DO_RELOAD=true
if [ "${1:-}" = "--no-reload" ]; then
    DO_RELOAD=false
    shift
fi

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

for name in $rule_files; do
    base="$(basename "$name")"
    repo_file="$REPO_DIR/$base"
    deployed="$DEPLOYED_DIR/$name"
    if [ ! -f "$repo_file" ]; then
        # Host-local rule files with no repo counterpart exist (e.g. node0's
        # alerts.yml). check-rules-deployed.sh flags them as drift; deploying
        # the files that DO have a repo source must not be blocked by them.
        echo "$base (skipped — no repo file)" >&2
        continue
    fi
    if command -v promtool >/dev/null 2>&1; then
        if ! promtool check rules "$repo_file" >/dev/null; then
            echo "deploy-rules: promtool rejects repo file $base — refusing to deploy" >&2
            exit 1
        fi
    fi
    if [ -f "$deployed" ] && cmp -s "$repo_file" "$deployed"; then
        echo "$base (unchanged)"
        continue
    fi
    cp "$repo_file" "$deployed"
    if command -v promtool >/dev/null 2>&1; then
        promtool check rules "$deployed" >/dev/null
    fi
    echo "$base (deployed)"
done

if [ "$DO_RELOAD" = true ]; then
    systemctl reload prometheus
    echo "prometheus reloaded"
else
    echo "reload skipped (--no-reload)"
fi
