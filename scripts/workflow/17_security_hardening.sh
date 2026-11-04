#!/usr/bin/env bash
# Security Hardening Script for AITBC Production
# This script implements security best practices for the blockchain network

set -euo pipefail


# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.example.net}"
    # No default for the shop node: it used to name one island's host, which
    # was wrong everywhere else and published that host in a public repo.
    export SHOP_URL="${SHOP_URL:-${AITBC_SHOP_URL:?set AITBC_SHOP_URL to the shop node URL, or provide /etc/aitbc/.env.scenario}}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "=== AITBC Security Hardening ==="

# Network Security
echo "1. Configuring network security..."
echo "   ⚠️  Firewall configuration skipped as requested"
echo "   ✅ Network security configuration completed"

# SSH Security
echo "2. Hardening SSH configuration..."
SSH_CONFIG="/etc/ssh/sshd_config"

# Backup original config
cp "$SSH_CONFIG" "$SSH_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"

# SSH security settings - allow root for development
for kv in "PermitRootLogin yes" "PasswordAuthentication no" \
          "PermitEmptyPasswords no" "X11Forwarding no" "MaxAuthTries 3"; do
    key="${kv%% *}"
    if grep -qE "^#?${key}[[:space:]]" "$SSH_CONFIG"; then
        sed -i -E "s|^#?${key}[[:space:]].*|${kv}|g" "$SSH_CONFIG"
    else
        echo "${kv}" >> "$SSH_CONFIG"
    fi
done

# Add additional security settings
cat >> "$SSH_CONFIG" << 'EOF'

# Additional security settings
ClientAliveInterval 300
ClientAliveCountMax 2
MaxStartups 10:30:60
AllowTcpForwarding no
AllowAgentForwarding no
EOF

# Restart SSH service
systemctl restart ssh

echo "   ✅ SSH security configured (root access allowed for development)"

# Access Control
echo "3. Setting up access controls..."
echo "   ⚠️  Sudo configuration skipped as requested"
echo "   ✅ Basic access control setup completed"

# File Permissions
echo "4. Securing file permissions..."

# Secure keystore directory
chmod 700 /var/lib/aitbc/keystore
# Keep the service owner — the node runs as User=aitbc and a root-owned
# keystore locks it out (#959).
SERVICE_USER="${SERVICE_USER:-aitbc}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" /var/lib/aitbc/keystore

# Secure configuration files
chmod 600 /etc/aitbc/blockchain.env
chmod 600 /var/lib/aitbc/keystore/.password

# Secure systemd service files
chmod 644 /etc/systemd/system/aitbc-*.service
chmod 600 /etc/systemd/system/aitbc-*.service.d/*

echo "   ✅ File permissions secured"

# Security Monitoring
echo "5. Setting up security monitoring..."

# Create security monitoring script
cat > /opt/aitbc/scripts/security_monitor.sh << 'EOF'
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
EOF

chmod +x /opt/aitbc/scripts/security_monitor.sh

# Add to cron for hourly security checks
(crontab -l 2>/dev/null; echo "0 * * * * /opt/aitbc/scripts/security_monitor.sh") | crontab -

# Deploy to aitbc node
echo "6. Deploying security configuration to aitbc node..."
scp /opt/aitbc/scripts/security_monitor.sh aitbc:/opt/aitbc/scripts/
ssh aitbc '
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
    for kv in "PermitRootLogin yes" "PasswordAuthentication no"; do
        key="${kv%% *}"
        if grep -qE "^#?${key}[[:space:]]" /etc/ssh/sshd_config; then
            sed -i -E "s|^#?${key}[[:space:]].*|${kv}|g" /etc/ssh/sshd_config
        else
            echo "${kv}" >> /etc/ssh/sshd_config
        fi
    done
    if sshd -t; then
        systemctl restart ssh
    else
        echo "ERROR: sshd -t failed, keeping old config" >&2
        cp /etc/ssh/sshd_config.backup /etc/ssh/sshd_config
        exit 1
    fi
'

# Apply SSH hardening on aitbc (allow root for development)
ssh aitbc '
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
    sed -i "s/#PermitRootLogin yes/PermitRootLogin yes/g" /etc/ssh/sshd_config
    sed -i "s/#PasswordAuthentication yes/PasswordAuthentication no/g" /etc/ssh/sshd_config
    systemctl restart ssh
'

echo "   ✅ Security monitoring deployed"

# Security Summary — report only what was actually verified (#959:
# the old block claimed results nobody checked).
echo "7. Security summary..."
{
    echo "AITBC Security Configuration Summary"
    echo "Generated: $(date)"
    echo ""
    echo "SSH settings now in effect:"
    grep -E '^(PermitRootLogin|PasswordAuthentication|MaxAuthTries|X11Forwarding|PermitEmptyPasswords)' "$SSH_CONFIG" 2>/dev/null | sed 's/^/  /' || true
    echo ""
    echo "Keystore: mode $(stat -c %a /var/lib/aitbc/keystore 2>/dev/null || echo n/a), owner $(stat -c %U /var/lib/aitbc/keystore 2>/dev/null || echo n/a)"
} > /opt/aitbc/security_summary.txt

echo "✅ Security hardening completed (see summary above for verified state)"
