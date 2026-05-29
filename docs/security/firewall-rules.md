# Firewall Rules

This guide covers UFW and iptables configuration for network access control.

## UFW Configuration

```bash
# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow AITBC services
sudo ufw allow 8080/tcp  # Blockchain
sudo ufw allow 8011/tcp  # Coordinator
sudo ufw allow 8071/tcp  # Wallet
sudo ufw allow 8102/tcp  # Marketplace

# Enable firewall
sudo ufw enable
```

## iptables Configuration

```bash
# Block all incoming except specific ports
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
iptables -A INPUT -p tcp --dport 8011 -j ACCEPT
iptables -A INPUT -p tcp --dport 8071 -j ACCEPT
iptables -A INPUT -p tcp --dport 8102 -j ACCEPT
```

## See Also

- [Network Security](network-security.md) - Network segmentation
- [Access Control](access-control.md) - User permissions
- [Authentication](authentication.md) - IP whitelisting
