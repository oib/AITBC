# AITBC Apps Documentation

**Level**: Intermediate
**Prerequisites**: Familiarity with the AITBC service layout
**Estimated Time**: 15-25 minutes
**Last Updated**: 2026-08-13
**Version**: 2.0 (Refreshed to current apps/ tree)

## Navigation Path

**[Documentation Home](../README.md)** → **Apps** → *You are here*

## See Also

- [Documentation Template Standard](../meta/DOCUMENTATION_TEMPLATE_STANDARD.md)
- [Master Index](../MASTER_INDEX.md) — full catalog
- [Getting Started](../getting-started/) — install and configure a node
- [Service Ports Reference](../reference/SERVICE_PORTS.md) — authoritative ports

---

Source code lives under `apps/` in the repository. Each app has its own `README.md` with status, node type, GPU requirements, systemd services, and source layout.

## App catalog

| App | Status | Node Type | GPU | Service(s) | Core | Source |
|-----|--------|-----------|-----|------------|------|--------|
| [agent-coordinator](../../apps/agent-coordinator/README.md) | active | island, hub | no | 1 systemd service(s): aitbc-agent-coordinator.service | no | src/ directory with 61 Python file(s) |
| [ai-engine](../../apps/ai-engine/README.md) | under development | island, hub | Yes | 4 systemd service(s): aitbc-ai.service, aitbc-learning.service, aitbc-modality-optimization.service, aitbc-multimodal.service | no | src/ directory with 2 Python file(s) |
| [api-gateway](../../apps/api-gateway/README.md) | under development | all | no | 1 systemd service(s): aitbc-api-gateway.service | yes | src/ directory with 2 Python file(s) |
| [blockchain-event-bridge](../../apps/blockchain-event-bridge/README.md) | active | hub | no | 1 systemd service(s): aitbc-blockchain-event-bridge.service | no | src/ directory with 16 Python file(s) |
| [blockchain-explorer](../../apps/blockchain-explorer/README.md) | Agent-First API Service - Pure JSON API for blockchain data access. | — | — | 1 systemd service: aitbc-blockchain-explorer.service | — | — |
| [blockchain-node](../../apps/blockchain-node/README.md) | active | all | no | 4 systemd service(s): aitbc-blockchain-node.service, aitbc-blockchain-p2p.service, aitbc-blockchain-rpc.service, aitbc-blockchain-sync.service | yes | src/ directory with 89 Python file(s) |
| [bridge-monitor](../../apps/bridge-monitor/README.md) | active | hub | no | 1 systemd service(s): aitbc-bridge-monitor.service | no | src/ directory with 3 Python file(s) |
| [coordinator-api](../../apps/coordinator-api/README.md) | active | all | no | 1 systemd service(s): aitbc-coordinator-api.service | yes | src/ directory with 508 Python file(s) |
| [edge](../../apps/edge/README.md) | active | island | Optional | 1 systemd service(s): aitbc-edge.service | no | src/ directory with 25 Python file(s) |
| [exchange](exchange/) ([exchange](../../apps/exchange/README.md)) | active | shop | no | 1 systemd service: aitbc-exchange.service (port 8106) | no | simple_exchange/ — stdlib HTTP server with handler mixins: |
| [ffmpeg](../../apps/ffmpeg/README.md) | active | island | Optional | 1 systemd service(s): aitbc-ffmpeg.service | no | main.py entry point |
| [governance](../../apps/governance/README.md) | active | hub | no | 1 systemd service(s): aitbc-governance.service | no | src/ directory with 7 Python file(s) |
| [gpu](../../apps/gpu/README.md) | active | hub, island | Yes | 1 systemd service(s): aitbc-gpu.service | no | src/ directory with 9 Python file(s) |
| [marketplace](marketplace/) ([marketplace](../../apps/marketplace/README.md)) | active | shop, hub | no | 1 systemd service(s): aitbc-marketplace.service | no | src/ directory with 9 Python file(s) |
| [miner](../../apps/miner/README.md) | active | island | Yes | 1 systemd service(s): aitbc-miner.service | no | production_miner.py entry point |
| [pool-hub](../../apps/pool-hub/README.md) | active | hub | no | No systemd service file | no | src/ directory with 37 Python file(s) |
| [shared-core](../../apps/shared-core/README.md) | shared library | n/a | no | No systemd service file — imported as a library by other apps. | no | src/ directory with 6 Python file(s) |
| [shared-domain](../../apps/shared-domain/README.md) | shared library | n/a | no | No systemd service file — imported as a library by other apps. | no | src/ directory with 1 Python file(s) |
| [trading](../../apps/trading/README.md) | active | shop | no | 1 systemd service(s): aitbc-trading.service | no | src/ directory with 7 Python file(s) |
| [wallet](wallet/) ([wallet](../../apps/wallet/README.md)) | active | all | no | 1 systemd service(s): aitbc-wallet.service | yes | src/ directory with 29 Python file(s) |
| [whisper](../../apps/whisper/README.md) | active | island | Optional | 1 systemd service(s): aitbc-whisper.service | no | main.py entry point |
| [zk-circuits](../../apps/zk-circuits/README.md) | experimental — and specifically, the trusted setup is development-only. | hub, island | no | No systemd service file | no | Circom circuits with Python compilation scripts |

## Concept and topic docs

These directories cover cross-cutting concerns rather than a single app:

- [agents](agents/)
- [blockchain](blockchain/)
- [compliance](compliance/)
- [coordinator](coordinator/)
- [crypto](crypto/)
- [explorer](explorer/)
- [global-ai](global-ai/)
- [infrastructure](infrastructure/)
- [openclaw](openclaw/)

## Notes

- Start services with `systemctl start aitbc-<app>.service`, not the `aitbc` CLI.
- For authoritative port numbers, health endpoints, and binding addresses, see [Service Ports Reference](../reference/SERVICE_PORTS.md).
- `shared-core` and `shared-domain` are libraries consumed by other apps; they do not have their own systemd services.
- `ai-engine`, `api-gateway`, and `zk-circuits` are experimental or under development; see [Release Status](../releases/STATUS.md).

## Related Resources

- [Getting Started](../getting-started/README.md) — pick a hub/shop/client path
- [CLI README](../../cli/README.md) — command reference
- [Release Status](../releases/STATUS.md) — what is complete vs. in flight
- [Master Index](../MASTER_INDEX.md) — complete documentation catalog

---

*Last updated: 2026-08-13*
*Version: 2.0*
*Status: Apps documentation hub*
