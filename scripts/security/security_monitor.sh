#!/bin/bash
# AITBC Security Monitoring Script
set -euo pipefail

SECURITY_LOG="${AITBC_SECURITY_LOG:-/var/log/aitbc/security.log}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Create log directory
mkdir -p "$(dirname "$SECURITY_LOG")"

# Function to log security events
log_security() {
    echo "[$TIMESTAMP] SECURITY: $1" >> $SECURITY_LOG
}

# Check for failed SSH attempts today. auth.log dates are syslog style
# "Nov  4" (space-padded), not "$(date '+%b %d')" ("Nov 04") — that grep never
# matched, and journald-based systems have no auth.log at all.
if command -v journalctl >/dev/null 2>&1; then
    FAILED_SSH=$(journalctl -u ssh.service -u sshd.service --since today --no-pager -q 2>/dev/null | grep -ciE 'authentication failure|failed password|invalid user' || true)
elif [ -r /var/log/auth.log ]; then
    today=$(date '+%b %e')
    FAILED_SSH=$(grep -cE "^${today}.*(authentication failure|Failed password|Invalid user)" /var/log/auth.log || true)
else
    FAILED_SSH=0
fi
if [ "${FAILED_SSH:-0}" -gt 10 ]; then
    log_security "High number of failed SSH attempts: $FAILED_SSH"
fi

# Check for unusual login activity
UNUSUAL_LOGINS=$(last -n 20 2>/dev/null | grep -cvE 'reboot|shutdown' || true)
if [ "${UNUSUAL_LOGINS:-0}" -gt 0 ]; then
    log_security "Recent login activity detected: $UNUSUAL_LOGINS logins"
fi

# Check service status
SERVICES_DOWN=$(systemctl list-units --state=failed 2>/dev/null | grep -c aitbc || true)
if [ "${SERVICES_DOWN:-0}" -gt 0 ]; then
    log_security "Failed AITBC services detected: $SERVICES_DOWN"
fi

# Check disk space
DISK_USAGE=$(df / 2>/dev/null | awk 'NR==2 {print $5}' | sed 's/%//' || true)
if [ "${DISK_USAGE:-0}" -gt 80 ]; then
    log_security "High disk usage: $DISK_USAGE%"
fi

echo "Security monitoring completed"
