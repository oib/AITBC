#!/bin/bash
# AITBC Security Monitoring Script

SECURITY_LOG="/var/log/aitbc/security.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Create log directory
mkdir -p /var/log/aitbc

# Function to log security events
log_security() {
    echo "[$TIMESTAMP] SECURITY: $1" >> $SECURITY_LOG
}

# Check for failed SSH attempts
FAILED_SSH=$(grep "authentication failure" /var/log/auth.log | grep "$(date '+%b %d')" | wc -l)
if [ "$FAILED_SSH" -gt 10 ]; then
    log_security "High number of failed SSH attempts: $FAILED_SSH"
fi

# Check for unusual login activity
UNUSUAL_LOGINS=$(last -n 20 | grep -v "reboot" | grep -v "shutdown" | wc -l)
if [ "$UNUSUAL_LOGINS" -gt 0 ]; then
    log_security "Recent login activity detected: $UNUSUAL_LOGINS logins"
fi

# Check service status
SERVICES_DOWN=$(systemctl list-units --state=failed | grep aitbc | wc -l)
if [ "$SERVICES_DOWN" -gt 0 ]; then
    log_security "Failed AITBC services detected: $SERVICES_DOWN"
fi

# Check disk space
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    log_security "High disk usage: $DISK_USAGE%"
fi

echo "Security monitoring completed"
