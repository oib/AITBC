# How to Configure Firehol for AITBC

## Overview

Firehol is a firewall configuration tool used to manage iptables rules. This guide covers the AITBC-specific configuration for allowing public service access while securing internal services.

## Current Configuration

The current `/etc/firehol/firehol.conf` configuration:

```bash
version 6

# IPv4
interface4 any world
    protection bad-packets
    server "ssh dhcp"        accept 
    server "dns echo icmp"   accept
    server "http https"      accept
    server custom aitbc tcp/8200 default accept
    server custom aitbc tcp/8201 default accept
    server custom aitbc tcp/8202 default accept
    server custom aitbc tcp/8203 default accept
    client all accept

# IPv6
interface6 any world6
    protection bad-packets 
    server "icmpv6 ipv6neigh" accept
    client "icmpv6 ipv6neigh" accept
    client all accept

# my-bridge (Incus)
interface4 incusbr0 br
    server      all     accept
    client      all     accept

# Fixed router rules for proper traffic flow
router br_to_host inface incusbr0 outface any
    server all accept
    route all accept
```

## Port Configuration

### Public Services (Allowed from External Network)

| Port | Service | Purpose |
|------|---------|---------|
| 8200 | API Gateway | Single entry point for external API calls |
| 8201 | Blockchain P2P | P2P network communication |
| 8202 | Blockchain RPC | External blockchain node access |
| 8203 | Coordinator API | Legacy failover service |

### Internal Services (Blocked from External Network)

| Port | Service | Binding | Status |
|------|---------|---------|--------|
| 8101 | GPU Service | 127.0.0.1 | Blocked by service binding |
| 8102 | Marketplace Service | 127.0.0.1 | Blocked by service binding |
| 8103 | Trading Service | 127.0.0.1 | Blocked by service binding |
| 8104 | Governance Service | 127.0.0.1 | Blocked by service binding |
| 8105 | Hermes Service | 127.0.0.1 | Blocked by service binding |

**Note**: Internal services are protected by binding to localhost (127.0.0.1), so they are not accessible from external networks even if firewall rules are misconfigured.

## Add a New Public Service

To expose a new service on a public port:

1. **Edit the firehol configuration:**
   ```bash
   sudo vim /etc/firehol/firehol.conf
   ```

2. **Add the new port rule in the `interface4 any world` section:**
   ```bash
   server custom aitbc tcp/8204 default accept
   ```

3. **Restart firehol:**
   ```bash
   sudo firehol restart
   ```

4. **Verify the rule is active:**
   ```bash
   sudo iptables -L -n | grep 8204
   ```

## Remove a Public Service

To remove a public service:

1. **Edit the firehol configuration:**
   ```bash
   sudo vim /etc/firehol/firehol.conf
   ```

2. **Remove the port rule from the `interface4 any world` section:**
   ```bash
   # Remove this line:
   server custom aitbc tcp/8203 default accept
   ```

3. **Restart firehol:**
   ```bash
   sudo firehol restart
   ```

## Block Internal Ports (Additional Security)

While internal services bind to localhost, you can add explicit firewall rules to block them:

```bash
# Add to interface4 any world section (after accept rules)
server custom aitbc tcp/8101 default drop
server custom aitbc tcp/8102 default drop
server custom aitbc tcp/8103 default drop
server custom aitbc tcp/8104 default drop
server custom aitbc tcp/8105 default drop
```

## Test Firewall Rules

### Check if a port is accessible from external network:

```bash
# From external host:
curl http://<your-server-ip>:8200/health
```

### Check firewall rules:

```bash
# List all firewall rules
sudo iptables -L -n -v

# Check specific port
sudo iptables -L -n | grep 8200
```

### Check service binding:

```bash
# Check if service is listening on localhost only
ss -lntup | grep 8101
# Should show: 127.0.0.1:8101 (not 0.0.0.0:8101)
```

## Incus Bridge Configuration

The configuration includes special rules for the Incus bridge (`incusbr0`):

```bash
# my-bridge (Incus)
interface4 incusbr0 br
    server      all     accept
    client      all     accept

# Fixed router rules for proper traffic flow
router br_to_host inface incusbr0 outface any
    server all accept
    route all accept
```

This allows:
- Full communication between containers on the bridge
- Traffic from containers to the host
- Traffic from containers to external networks (subject to external interface rules)

## Troubleshooting

### Service Not Accessible from External Network

1. **Check firewall rules:**
   ```bash
   sudo iptables -L -n | grep <port>
   ```

2. **Check service is running:**
   ```bash
   systemctl status <service-name>
   ```

3. **Check service binding:**
   ```bash
   ss -lntup | grep <port>
   ```

4. **Check Incus port forwarding:**
   ```bash
   incus config device show aitbc
   ```

### Firehol Fails to Start

1. **Check configuration syntax:**
   ```bash
   sudo firehol try
   ```

2. **Check for syntax errors:**
   ```bash
   sudo firehol explain /etc/firehol/firehol.conf
   ```

3. **Review logs:**
   ```bash
   sudo journalctl -u firehol -n 50
   ```

## Security Best Practices

1. **Principle of Least Privilege**: Only expose ports that are absolutely necessary
2. **Service Binding**: Always bind internal services to 127.0.0.1
3. **Regular Audits**: Review firewall rules regularly and remove unused ports
4. **Testing**: Test firewall rules in a non-production environment first
5. **Backups**: Keep a backup of working firehol.conf before making changes

## Complete Example: Adding a New Service

```bash
# 1. Add Incus port forwarding
incus config device add aitbc new-service proxy listen=tcp:0.0.0.0:8204 connect=tcp:192.168.100.10:8204

# 2. Edit firehol configuration
sudo vim /etc/firehol/firehol.conf
# Add: server custom aitbc tcp/8204 default accept

# 3. Test configuration
sudo firehol try

# 4. Apply configuration
sudo firehol restart

# 5. Verify
sudo iptables -L -n | grep 8204
curl http://localhost:8204
```

## Related Documentation

- [Incus Port Forwarding](incus-port-forwarding.md) - Container port configuration
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration
- [Security Notes](../getting-started/reference/security-notes.md) - Security best practices
