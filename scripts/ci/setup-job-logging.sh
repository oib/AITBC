#!/bin/bash
set -euo pipefail

LOG_DIR="${AITBC_CI_LOG_DIR:-/opt/gitea-runner/logs}"
WORKFLOW_NAME="${GITHUB_WORKFLOW:-workflow}"
JOB_NAME="${GITHUB_JOB:-job}"
RUN_ID="${GITHUB_RUN_ID:-${GITHUB_RUN_NUMBER:-$(date +%s)}}"
RUN_NUMBER="${GITHUB_RUN_NUMBER:-}"
RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
GITHUB_ENV_FILE="${GITHUB_ENV:-${GITEA_ENV:-}}"

sanitize() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
}

SAFE_WORKFLOW="$(sanitize "$WORKFLOW_NAME")"
SAFE_JOB="$(sanitize "$JOB_NAME")"
SAFE_ATTEMPT="$(sanitize "$RUN_ATTEMPT")"
SAFE_WORKFLOW="${SAFE_WORKFLOW:-workflow}"
SAFE_JOB="${SAFE_JOB:-job}"

mkdir -p "$LOG_DIR"

LOG_BASENAME="${SAFE_WORKFLOW}_${SAFE_JOB}_${RUN_ID}_attempt-${SAFE_ATTEMPT}"
LOG_FILE="$LOG_DIR/${LOG_BASENAME}.log"
INDEX_FILE="$LOG_DIR/index.tsv"
LATEST_FILE="$LOG_DIR/latest.log"
WORKFLOW_LATEST_FILE="$LOG_DIR/latest-${SAFE_WORKFLOW}.log"
JOB_LATEST_FILE="$LOG_DIR/latest-${SAFE_WORKFLOW}-${SAFE_JOB}.log"
ENV_FILE="/tmp/aitbc-ci-log-${RUN_ID}-${SAFE_JOB}.env"

: > "$LOG_FILE"
touch "$INDEX_FILE"

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" \
    "$RUN_ID" \
    "$RUN_NUMBER" \
    "$RUN_ATTEMPT" \
    "$WORKFLOW_NAME" \
    "$JOB_NAME" \
    "$LOG_FILE" >> "$INDEX_FILE"

ln -sfn "$LOG_FILE" "$LATEST_FILE"
ln -sfn "$LOG_FILE" "$WORKFLOW_LATEST_FILE"
ln -sfn "$LOG_FILE" "$JOB_LATEST_FILE"

cat > "$ENV_FILE" <<EOF
if [[ "\${AITBC_CI_LOGGING_ACTIVE:-}" == "1" ]]; then
  return 0 2>/dev/null || :
fi
export AITBC_CI_LOGGING_ACTIVE=1
export AITBC_CI_LOG_FILE="$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== \${GITHUB_WORKFLOW:-workflow} / \${GITHUB_JOB:-job} :: \$(date -Iseconds) ==="
EOF

if [[ -n "$GITHUB_ENV_FILE" ]]; then
    {
        printf 'AITBC_CI_LOG_DIR=%s\n' "$LOG_DIR"
        printf 'AITBC_CI_LOG_FILE=%s\n' "$LOG_FILE"
        printf 'AITBC_CI_LOG_INDEX=%s\n' "$INDEX_FILE"
        printf 'AITBC_CI_LOG_LATEST=%s\n' "$LATEST_FILE"
        printf 'AITBC_CI_LOG_WORKFLOW_LATEST=%s\n' "$WORKFLOW_LATEST_FILE"
        printf 'AITBC_CI_LOG_JOB_LATEST=%s\n' "$JOB_LATEST_FILE"
        printf 'BASH_ENV=%s\n' "$ENV_FILE"
    } >> "$GITHUB_ENV_FILE"
else
    echo "CI logging warning: GITHUB_ENV/GITEA_ENV not set; automatic logging for later steps is unavailable"
fi

echo "CI log file: $LOG_FILE"
echo "CI latest log: $LATEST_FILE"
echo "CI workflow latest: $WORKFLOW_LATEST_FILE"
echo "CI job latest: $JOB_LATEST_FILE"
echo "CI log index: $INDEX_FILE"
