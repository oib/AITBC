# Network Security

This guide covers network segmentation, VPN access, and private network configuration.

## Network Segmentation

```
Internet
    |
    v
[DMZ] - Public Services (Load Balancer, Nginx)
    |
    v
[Internal] - Application Services
    |
    v
[Database] - PostgreSQL, Redis
```

## VPN Access

```bash
# Configure WireGuard VPN
wg genkey | tee privatekey | wg pubkey > publickey

# Configure server
[Interface]
PrivateKey = YOUR_PRIVATE_KEY
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = CLIENT_PUBLIC_KEY
AllowedIPs = 10.0.0.2/32
```

## Private Networks

```bash
# Configure private network for multi-node deployment
# Use VPN or private VPC
# Restrict access to specific IP ranges
```

## See Also

- [Firewall Rules](firewall-rules.md) - Access control
- [SSL/TLS Configuration](ssl-tls-configuration.md) - Encryption
- [Access Control](access-control.md) - Permissions
