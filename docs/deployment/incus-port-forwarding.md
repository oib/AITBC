# How to Configure Incus Port Forwarding for aitbc Container

## Current Configuration

The `aitbc` container is configured with the following port forwardings:

- **8200** → Blockchain P2P
- **8201** → API Gateway
- **8202** → Blockchain RPC
- **8203** → Coordinator API (failover)
- **8204** → Agent Registry

All forwarded to container IP: `192.168.100.10`

## View Current Port Forwardings

```bash
incus config device show aitbc
```

## Add a New Port Forwarding

```bash
incus config device add aitbc <device-name> proxy listen=tcp:0.0.0.0:<host-port> connect=tcp:<container-ip>:<container-port>
```

Example:
```bash
incus config device add aitbc my-service proxy listen=tcp:0.0.0.0:8204 connect=tcp:192.168.100.10:8204
```

## Remove a Port Forwarding

```bash
incus config device remove aitbc <device-name>
```

Example:
```bash
incus config device remove aitbc api-gateway
```

## Update Firewall Rules

After adding/removing port forwardings, update the firewall configuration in `/etc/firehol/firehol.conf`:

```bash
# Add to the interface4 any world section
server custom aitbc tcp/8204 default accept
```

Then restart firehol:
```bash
firehol restart
```

## Verify Port Forwarding

Check if the proxy device is active:
```bash
incus config device show aitbc
```

Check if the port is listening on the host:
```bash
ss -lntup | grep :<port>
```

Test connectivity from host:
```bash
curl http://localhost:<port>
```

## Important Notes

1. **Port conflicts**: Ensure the host port is not already in use (check with `ss -lntup | grep :<port>`)
2. **Container service**: The service must be listening on the specified container port
3. **Firewall**: Always update firehol rules to allow the new port
4. **Incus daemon port**: The Incus daemon uses port 8443 (changed from default 8006 to avoid conflicts)

## Complete Example: Adding a New Service

```bash
# 1. Add the proxy device
incus config device add aitbc new-service proxy listen=tcp:0.0.0.0:8204 connect=tcp:192.168.100.10:8204

# 2. Update firewall
vim /etc/firehol/firehol.conf
# Add: server custom aitbc tcp/8204 default accept

# 3. Restart firewall
firehol restart

# 4. Verify
incus config device show aitbc
ss -lntup | grep :8204
curl http://localhost:8204
```
