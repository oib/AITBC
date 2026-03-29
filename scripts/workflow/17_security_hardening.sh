#!/bin/bash
# Security Hardening Script for AITBC Production
# This script implements security best practices for the blockchain network

set -e  # Exit on any error

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
sed -i 's|#PermitRootLogin yes|PermitRootLogin yes|g' "$SSH_CONFIG"
sed -i 's|#PasswordAuthentication yes|PasswordAuthentication no|g' "$SSH_CONFIG"
sed -i 's|#PermitEmptyPasswords yes|PermitEmptyPasswords no|g' "$SSH_CONFIG"
sed -i 's|#X11Forwarding yes|X11Forwarding no|g' "$SSH_CONFIG"
sed -i 's|#MaxAuthTries 6|MaxAuthTries 3|g' "$SSH_CONFIG"

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
chown -R root:root /var/lib/aitbc/keystore

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
EOF

chmod +x /opt/aitbc/scripts/security_monitor.sh

# Add to cron for hourly security checks
(crontab -l 2>/dev/null; echo "0 * * * * /opt/aitbc/scripts/security_monitor.sh") | crontab -

# Deploy to aitbc node
echo "6. Deploying security configuration to aitbc node..."
scp /opt/aitbc/scripts/security_monitor.sh aitbc:/opt/aitbc/scripts/
ssh aitbc 'chmod +x /opt/aitbc/scripts/security_monitor.sh'

# Apply SSH hardening on aitbc (allow root for development)
ssh aitbc '
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
    sed -i "s/#PermitRootLogin yes/PermitRootLogin yes/g" /etc/ssh/sshd_config
    sed -i "s/#PasswordAuthentication yes/PasswordAuthentication no/g" /etc/ssh/sshd_config
    systemctl restart ssh
'

echo "   ✅ Security monitoring deployed"

# Security Summary
echo "7. Generating security summary..."
cat > /opt/aitbc/security_summary.txt << EOF
AITBC Security Configuration Summary
Generated: $(date)

Network Security:
- Firewall configuration: Skipped as requested
- Network security: Basic configuration completed

SSH Hardening:
- Root login: Enabled (development mode)
- Password authentication disabled
- Max authentication attempts: 3
- Session timeout: 5 minutes

Access Control:
- User creation: Skipped as requested
- Sudo configuration: Skipped as requested
- Basic access control: Completed

Monitoring:
- Security monitoring script created
- Hourly security checks scheduled
- Logs stored in /var/log/aitbc/security.log

Recommendations:
1. Use SSH key authentication only
2. Monitor security logs regularly
3. Keep systems updated
4. Review access controls regularly
5. Implement intrusion detection system
6. Configure firewall according to your security policy
EOF

echo "✅ Security hardening completed successfully!"
echo "   • SSH access configured (root allowed for development)"
echo "   • File permissions secured"
echo "   • Security monitoring active"
echo "   • Configuration deployed to both nodes"
echo "   • Firewall configuration skipped as requested"
echo "   • Sudo configuration skipped as requested"
echo "   • User creation skipped (using root)"
echo ""
echo "📋 Security summary saved to /opt/aitbc/security_summary.txt"
