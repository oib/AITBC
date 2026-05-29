# Network Issues

This guide covers network problems including connection timeouts, DNS issues, and firewall configuration.

## Connection Timeouts

**Symptoms:**
- Services unable to connect to each other
- Intermittent connection failures
- High latency

**Diagnosis:**
```bash
# Test connectivity
ping -c 10 localhost

# Check DNS
nslookup localhost

# Check ports
telnet localhost 8011
```

**Solutions:**
1. Check network configuration
```bash
# Check IP configuration
ip addr show

# Check routing
ip route show

# Check DNS
cat /etc/resolv.conf
```

2. Check firewall rules
```bash
# Check UFW status
ufw status

# Check iptables
iptables -L -n
```

3. Check MTU
```bash
# Check MTU
ip link show

# Adjust MTU if needed
ip link set eth0 mtu 1500
```

## DNS Issues

**Symptoms:**
- Domain names not resolving
- Services unable to connect by hostname
- Slow DNS resolution

**Diagnosis:**
```bash
# Test DNS resolution
nslookup google.com

# Check DNS servers
cat /etc/resolv.conf

# Test local DNS
dig localhost
```

**Solutions:**
1. Change DNS servers
```bash
# Use Google DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
```

2. Clear DNS cache
```bash
# Clear systemd cache
systemd-resolve --flush-caches

# Restart DNS service
systemctl restart systemd-resolved
```

## See Also

- [Blockchain Issues](blockchain-issues.md) - P2P network and peer connectivity issues
- [Service Management](service-management.md) - General service troubleshooting
- [Security Issues](security-issues.md) - Firewall and access control issues
