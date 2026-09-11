# Network Policy

**Last Updated:** 2026-09-11
**Version:** 2.0

## Overview

AITBC services run in containers that carry **no firewall of their own**.
Filtering is administered outside the guest -- at the container host and at the
provider perimeter. That yields two planes, with different answers:

- **From the internet -- filtered.** Application ports are not exposed at the
  perimeter; public reachability is limited to the surfaces listed below.
- **Between co-located containers -- flat.** Containers on a shared bridge reach
  each other unfiltered, and that bridge is not exclusive to AITBC: unrelated
  services share it. A bind-all port is reachable by every one of them.

So **the bind address is the entire access control on the container plane**, and
that plane decides blast radius once any single service is compromised. It is not
what keeps a port off the internet -- the perimeter does that. Write bind
decisions against lateral movement, not against internet exposure.

> Host names, addresses and bridge layout are deliberately absent from this
> repository. Verify the live state against the operator's own topology notes.

## Authorized public surfaces

Only these may be internet-reachable. Anything else on a public interface is a
policy violation.

| Surface | Port | Where | Why |
|---------|------|-------|-----|
| nginx (TLS) | 443, 80 | TLS terminator host | The entire customer-facing surface; proxies `/api/`, `/rpc/`, `/c/`, `/explorer-api/` |
| Blockchain P2P | 7070 | Hub | Followers on other hosts gossip over the public internet; registered via `aitbc node hub register --public-address <ip> --public-port 7070` |
| IPFS Swarm | 4002 | Island hosts | Private-swarm IPFS needs inbound peer connections; TCP and UDP (QUIC) |

`80` is permitted only to redirect to `443`, never to serve an application.

## Proxied backends: private interface

TLS terminates on a *different host* from the services, so nginx reaches its
backends over the private link. `127.0.0.1` would break the proxy; `0.0.0.0`
would expose the backend directly. These bind the private interface address:

| Service | Port |
|---------|------|
| API Gateway | 8201 |
| Blockchain RPC | 8202 |
| Blockchain Explorer | 8100 |
| Coordinator API | 8203 |

## Everything else: `127.0.0.1`

Every other service is an internal caller's dependency and binds loopback. This
is the whole internal tier plus the internal support services; see
[Service Ports Reference](../reference/SERVICE_PORTS.md) for the current roster
and the bind each one actually has today.

Set the bind **explicitly in the systemd unit** rather than relying on an
application default. `apps/marketplace/aitbc-marketplace.service` is the pattern
to copy:

```ini
Environment=MARKETPLACE_BIND_HOST=127.0.0.1
Environment=MARKETPLACE_BIND_PORT=8102
```

Relying on a code default is how a service ends up public without anyone
deciding that it should be: the default in most of these applications is
`0.0.0.0`, so an absent line is a decision to expose.

### Why not a firewall rule instead

Earlier revisions of this document prescribed `ufw allow`/`ufw deny` rules and
systemd `IPDeny=any`. Neither belongs in the guest:

- The containers run no firewall of their own. Filtering is administered outside
  the guest, so a `ufw` rule in a guest runbook edits a control that does not
  live there.
- `IPDeny=` requires systemd 242+ and was reverted after it broke services.

A perimeter control does exist -- but it is not visible from inside the container
and does not separate one co-located container from another. Bind the socket; that is the
only lever the guest actually holds.

The `# nosec B104` comments in the codebase justify a bind-all with "the real
boundary is the firewall/reverse-proxy layer". That is true of the internet plane
and false of the container plane: a bind-all service is reachable by every other
container on the bridge, whether or not a proxy fronts it from outside.

## Known deviations

**None.** As of 2026-09-11 every service pins its bind explicitly in its systemd
unit, and no service binds `0.0.0.0` except the authorized public surfaces above.

This section is kept deliberately. When a bind cannot be pinned in the change
that introduces it, record it here with the reason -- the drift gate reads this
table, warns on what it lists, and fails on anything it does not. An empty table
means the gate now fails on *any* new bind-all service, which is the intended
resting state.

Two entries were closed by code changes rather than unit edits, and both are
worth knowing about:

- **Blockchain Explorer (8100)** hardcoded `host="0.0.0.0"` in `uvicorn.run()`
  with no environment variable, so no unit could override it. It now reads
  `EXPLORER_BIND_HOST` and defaults to loopback.
- **Edge (8111)** used one setting as both the bind address and the endpoint it
  advertised to `/rpc/edge/register`, so it registered itself at
  `http://0.0.0.0:8111`. Bind and advertised address are now separate
  (`APP_HOST` and `EDGE_ADVERTISE_HOST`).

## Verification

Check what is actually listening, on each host:

```bash
# Any AITBC service reachable from outside this host
ss -ltnp | grep -E '0\.0\.0\.0:(70[0-9]{2}|8[0-2][0-9]{2})'
```

Every hit must correspond to a row in [Authorized public surfaces](#authorized-public-surfaces)
or [Proxied backends](#proxied-backends-private-interface). Anything else is a finding.

Note that several units load `EnvironmentFile=/etc/aitbc/%N.env`, which is not in
this repository. A bind may be overridden there, in either direction -- so the
repo defaults recorded in SERVICE_PORTS.md are a starting point for this check,
never a substitute for running it.

```bash
# Confirm a specific service's effective bind
systemctl show aitbc-marketplace.service -p Environment
```

## Drift control

`scripts/docs/check_bind_policy.py` cross-checks the two documents: every service
that SERVICE_PORTS.md records as binding `0.0.0.0` must be named as an authorized
public surface here. Adding a bind-all service without a policy decision fails the
check. It runs in pre-commit and in CI alongside the port consistency gate.

## References

- [Service Ports Reference](../reference/SERVICE_PORTS.md) -- observed ports and binds
- [Dependencies](./DEPENDENCIES.md#port-exposure-policy) -- deployment prerequisites
- [Service Users](./SERVICE_USERS.md) -- service account separation
