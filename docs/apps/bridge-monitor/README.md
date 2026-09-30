# bridge-monitor

**Source code:** [apps/bridge-monitor/README.md](../../../apps/bridge-monitor/README.md)

Ethereum→AIT bridge payout monitor: watches the Sepolia deposit address,
prices each inflow via the oracle pair, and pays the AIT equivalent from a
dedicated payout wallet — ledger-first; a deposit is `COMPLETED` only once
its payout is sealed. Holds signed payout envelopes, enforces per-deposit
caps (fraction + absolute), and records funding-source inflows separately
(`BRIDGE_FUNDING_SOURCES`).

## App metadata

| Field | Value |
|-------|-------|
| Status | active |
| Node Type | hub |
| GPU Required | no |
| Service | 1 systemd service(s): aitbc-bridge-monitor.service |
| Core Service | no |
| Source | src/ directory with 4 Python file(s) |

## Operational reference

The payout lifecycle (ledger states, admin commands, caps, env knobs) is
documented in the app README linked above — that file is authoritative.

## See also

- [Apps documentation index](../README.md)
- [Service Ports Reference](../../reference/SERVICE_PORTS.md)
- [Bridge custodian security model](../../security/bridge-custodian.md)
- [Getting Started](../../getting-started/)
