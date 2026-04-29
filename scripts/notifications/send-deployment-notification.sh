#!/bin/bash
# Send deployment notifications to configured channels

set -e

NETWORK="${1:-testnet}"
STATUS="${2:-success}"
REPO_DIR="/opt/aitbc"

echo "=== Sending deployment notification for ${NETWORK} ==="

# Load notification configuration
if [[ -f "${REPO_DIR}/scripts/notifications/config.sh" ]]; then
  source "${REPO_DIR}/scripts/notifications/config.sh"
else
  echo "⚠️  Notification config not found, using defaults"
fi

# Prepare notification message
if [[ "$STATUS" == "success" ]]; then
  EMOJI="✅"
  COLOR="good"
  MESSAGE="Deployment to ${NETWORK} completed successfully"
elif [[ "$STATUS" == "failure" ]]; then
  EMOJI="❌"
  COLOR="danger"
  MESSAGE="Deployment to ${NETWORK} failed"
else
  EMOJI="⚠️"
  COLOR="warning"
  MESSAGE="Deployment to ${NETWORK} had issues"
fi

# Send Slack notification if configured
if [[ -n "${SLACK_WEBHOOK_URL}" ]]; then
  curl -X POST "${SLACK_WEBHOOK_URL}" \
    -H 'Content-Type: application/json' \
    -d "{
      \"text\": \"${EMOJI} ${MESSAGE}\",
      \"attachments\": [{
        \"color\": \"${COLOR}\",
        \"fields\": [
          {
            \"title\": \"Network\",
            \"value\": \"${NETWORK}\",
            \"short\": true
          },
          {
            \"title\": \"Status\",
            \"value\": \"${STATUS}\",
            \"short\": true
          },
          {
            \"title\": \"Timestamp\",
            \"value\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
            \"short\": true
          }
        ]
      }]
    }"
  echo "✅ Slack notification sent"
else
  echo "⚠️  Slack webhook not configured"
fi

# Send email notification if configured
if [[ -n "${ALERT_EMAIL}" ]] && command -v mail &> /dev/null; then
  echo "${EMOJI} ${MESSAGE}
  
Network: ${NETWORK}
Status: ${STATUS}
Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | mail -s "AITBC Deployment: ${NETWORK} - ${STATUS}" "${ALERT_EMAIL}"
  echo "✅ Email notification sent"
else
  echo "⚠️  Email notification not configured"
fi

echo "=== Deployment notification sent ==="
