# Network Policy Documentation

> **Last verified:** 2026-06-20 (v0.5.3, Agent B)
> **Source of truth:** `/etc/systemd/system/aitbc-*.service` `ExecStart` lines + app source defaults.

This document is the authoritative map of which AITBC services bind to which
network interfaces, and the policy that governs exposure.

## Policy

1. **Public / P2P services** bind to `0.0.0.0` — they must be reachable from
   external peers or clients.
2. **Internal services** bind to `127.0.0.1` — they are consumed only by other
   local services, the CLI, or the public-facing gateway/explorer which proxy
   to them.
3. Services that read a `*_BIND_HOST` env var default to `0.0.0.0` in source for
   dev convenience; production must set `*_BIND_HOST=127.0.0.1` in the service
   env file unless the service is in the public list below.

---

## Public / P2P services (intentionally `0.0.0.0`)

| Service | Port | Purpose | Binding |
|---------|------|---------|---------|
| `aitbc-api-gateway` | 8201 | Public API gateway | `0.0.0.0` (systemd `--host 0.0.0.0`) |
| `aitbc-blockchain-explorer` | 8100 | Public block explorer web UI | `0.0.0.0` (hardcoded in `apps/blockchain-explorer/main.py`) |
| `aitbc-blockchain-p2p` | p2p port (config) | P2P peer networking | `0.0.0.0` (intentional, `nosec B104`) |
| `aitbc-blockchain-node` | p2p/rpc (config) | Node process hosting P2P + RPC | P2P `0.0.0.0`; RPC exposed separately via `aitbc-blockchain-rpc` at `127.0.0.1` |

These must NOT be changed to `127.0.0.1`.

---

## Internal services (verified `127.0.0.1`)

These bind to loopback only. Verified from systemd `ExecStart` or source.

| Service | Port | Binding | Verification |
|---------|------|---------|--------------|
| `aitbc-ai` | 8005 | `127.0.0.1` | **FIXED in v0.5.3** — systemd unit changed from `0.0.0.0` to `127.0.0.1` |
| `aitbc-blockchain-rpc` | 8202 | `127.0.0.1` | systemd `--host 127.0.0.1` |
| `aitbc-coordinator-api` | 8203 | `127.0.0.1` | systemd `--host 127.0.0.1` |
| `aitbc-learning` | 8012 | `127.0.0.1` | systemd `--host 127.0.0.1` (runs `adaptive_learning_app`) |
| `aitbc-modality-optimization` | 8021 | `127.0.0.1` | systemd `--host 127.0.0.1` |
| `aitbc-multimodal` | 8020 | `127.0.0.1` | systemd `--host 127.0.0.1` |
| `aitbc-exchange` | 8106 | `127.0.0.1` | source: `HTTPServer(("localhost", port), ...)` |

### Coordinator-API sub-app `__main__` blocks (hardened in v0.5.3)

These files are not run as standalone systemd units in production (the three
above are), but their `if __name__ == "__main__"` dev entrypoints were changed
from `host="0.0.0.0"` to `host="127.0.0.1"` so accidental `python -m` execution
does not expose internal services:

- `apps/coordinator-api/src/app/services/adaptive_learning_app.py` (8005)
- `apps/coordinator-api/src/app/services/modality_optimization_app.py` (8004)
- `apps/coordinator-api/src/app/services/multimodal_app.py` (8002)
- `apps/coordinator-api/src/app/services/gpu_multimodal_app.py` (8003)
- `apps/coordinator-api/src/app/services/advanced_ai_service.py` (8015)
- `apps/coordinator-api/src/app/services/enterprise_integration/api_gateway.py` (8010)
- `apps/coordinator-api/src/app/routers/marketplace_enhanced_app.py` (8002)
- `apps/coordinator-api/src/app/contexts/hermes/routers/hermes_enhanced_app.py` (8014)

---

## Services with `*_BIND_HOST` env-var default `0.0.0.0` (review pending)

These services default to `0.0.0.0` in source but honor a `*_BIND_HOST` env var.
They were **not** changed in v0.5.3 because they were not in the explicit
hardening list and some may require external access depending on deployment
topology. Operators should set `*_BIND_HOST=127.0.0.1` in the service env file
(`/etc/aitbc/%N.env`) for any that are purely internal.

| Service | Port | Env var | Default | Recommended |
|---------|------|---------|---------|-------------|
| `aitbc-edge` | 8111 | `EDGE_BIND_HOST` (settings.api_host) | `0.0.0.0` | Review — likely internal |
| `aitbc-gpu` | 8101 | `GPU_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-hermes` | 8103 | `HERMES_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-marketplace` | 8102 | `MARKETPLACE_BIND_HOST` | `0.0.0.0` | Review — public website proxies to it |
| `aitbc-trading` | 8104 | `TRADING_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-wallet` | 8108 | `WALLET_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-whisper` | 8110 | `WHISPER_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-governance` | 8105 | `GOVERNANCE_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-ffmpeg` | 8230 | `FFMPEG_BIND_HOST` | `0.0.0.0` | Review — likely internal |
| `aitbc-plugin` | 8109 | (hardcoded in wrapper) | `0.0.0.0` | Review — wrapper hardcodes host; refactor to env var |

**Action for operators:** for each "likely internal" service, add
`<SERVICE>_BIND_HOST=127.0.0.1` to `/etc/aitbc/aitbc-<service>.env` and restart.
Re-verify with `ss -tlnp | grep <port>`.

---

## Defense-in-Depth Recommendations

For localhost-only services, consider adding additional security:

```ini
# Example for coordinator-api
[Service]
# Existing localhost binding
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8203

# Additional defense-in-depth (optional)
# IPDeny=any  # Deny all external IP connections
# IPAllow=127.0.0.1  # Only allow localhost
```

## Firewall Recommendations

### UFW (Uncomplicated Firewall)

```bash
# Allow SSH
ufw allow 22/tcp

# Allow public AITBC services
ufw allow 8201/tcp  # api-gateway
ufw allow 8100/tcp  # blockchain-explorer web
ufw allow <p2p-port>/tcp  # blockchain P2P

# Deny all other incoming traffic
ufw default deny incoming
ufw default allow outgoing

# Enable firewall
ufw enable
```

### iptables

```bash
# Allow established connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow public AITBC services
iptables -A INPUT -p tcp --dport 8201 -j ACCEPT  # api-gateway
iptables -A INPUT -p tcp --dport 8100 -j ACCEPT  # explorer web
iptables -A INPUT -p tcp --dport <p2p-port> -j ACCEPT  # P2P

# Allow localhost
iptables -A INPUT -i lo -j ACCEPT

# Drop everything else
iptables -A INPUT -j DROP
```

## Monitoring and Alerting

### Network Connection Monitoring

Monitor for unexpected external connections to localhost-only services:

```bash
# List all AITBC listening sockets and their bind addresses
ss -tlnp | grep -E ':(8005|8202|8203|8012|8020|8021|8106)\b'

# Any of the above NOT showing 127.0.0.1 is a policy violation.
```

### Alert Thresholds

- **Critical**: External connection to a localhost-only service
- **Warning**: Unexpected port binding on a public service
- **Info**: Normal service startup/port binding

## Implementation Status

- ✅ Public vs internal service classification complete
- ✅ `aitbc-ai` systemd unit hardened to `127.0.0.1` (v0.5.3)
- ✅ Coordinator-API sub-app `__main__` defaults hardened to `127.0.0.1` (v0.5.3)
- ✅ Service binding documentation complete and verified against systemd units
- ⏳ `*_BIND_HOST` env-var-default services pending operator review (see table above)
- ⏳ IPDeny/IPAllow directives not yet implemented (optional)
- ⏳ Firewall rules not yet deployed (DevOps task)
