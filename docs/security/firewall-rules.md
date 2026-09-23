# Firewall Rules

This guide covers UFW and iptables configuration for network access control.

> **Authoritative reference:** [docs/deployment/NETWORK_POLICY.md](../deployment/NETWORK_POLICY.md).
> The short version: AITBC nodes carry no guest firewall — filtering happens at
> the container host and provider perimeter. On a flat container bridge, **the
> bind address is the access control**, so most services bind `127.0.0.1` and
> should never be opened in a firewall at all.

## What actually needs inbound access

Only these surfaces may be reachable from outside the node:

| Surface | Port | Where |
|---------|------|-------|
| nginx (TLS) | 443 (80 only redirects to 443) | TLS terminator host — proxies `/api/`, `/rpc/`, `/c/`, `/explorer-api/` |
| Blockchain P2P gossip | 7070 | Hub — followers on other hosts gossip over the internet |
| IPFS swarm | 4002 (private island swarm) / 4001 (public Kubo swarm) | Island / GPU nodes |
| SSH | 22 | All nodes |

Everything else — blockchain RPC `8202`, coordinator-api `8203`, agent
coordinator `8107`, market `8102`, wallet `8108`, exchange `8106`, GPU
`8101`, governance `8105`, trading `8104` — is either loopback-bound or
reachable only through nginx on the private link. Do **not** open these in
the firewall.

## UFW Configuration (host with a public interface)

```bash
# Default policies
ufw default deny incoming
ufw default allow outgoing

# SSH
ufw allow 22/tcp

# nginx TLS terminator (80 only for the redirect to 443)
ufw allow 443/tcp
ufw allow 80/tcp

# Hub only: blockchain P2P gossip between hosts
ufw allow 7070/tcp

# IPFS nodes only
ufw allow 4002/tcp   # private island swarm
ufw allow 4001/tcp   # public Kubo swarm (customer/shop GPU nodes)

# Enable firewall
ufw enable
```

## iptables Configuration

```bash
# Block all incoming except specific ports
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
# Hub only:
iptables -A INPUT -p tcp --dport 7070 -j ACCEPT
# IPFS nodes only:
iptables -A INPUT -p tcp --dport 4002 -j ACCEPT
iptables -A INPUT -p tcp --dport 4001 -j ACCEPT
iptables -A INPUT -p udp --dport 4001 -j ACCEPT   # QUIC
```

## See Also

- [Network Policy](../deployment/NETWORK_POLICY.md) — authoritative bind/exposure policy
- [Network Security](network-security.md) - Network segmentation
- [Access Control](access-control.md) - User permissions
- [Authentication](authentication.md) - IP whitelisting
