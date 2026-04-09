# Direct TCP P2P Mesh Network Update

The AITBC blockchain network has been upgraded from a Redis-backed PubSub gossip model to a **Direct TCP P2P Mesh Network** running on port `7070`.

## Architecture Changes
- The `P2PNetworkService` (`p2p_network.py`) now directly binds to port `7070` via `asyncio.start_server`.
- The `gossip_backend` variable is now strictly set to `memory` since external block/transaction propagation is handled via P2P TCP streams rather than a centralized Redis bus.
- Nodes identify themselves securely via a JSON handshake (`{'type': 'handshake', 'node_id': '...'}`).

## Configuration Flags
The `/etc/aitbc/blockchain.env` configuration now requires explicit peer targeting instead of Redis connection strings:

```bash
# Removed:
# gossip_backend=broadcast
# gossip_broadcast_url=redis://localhost:6379

# Updated/Added:
gossip_backend=memory
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
p2p_peers=aitbc1:7070,aitbc2:7070 # Comma-separated list of known nodes
```

## Systemd Service
The systemd service (`/etc/systemd/system/aitbc-blockchain-p2p.service`) has been updated to reflect the new CLI arguments:
```ini
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.p2p_network \
  --host ${p2p_bind_host} \
  --port ${p2p_bind_port} \
  --peers ${p2p_peers} \
  --node-id ${proposer_id}
```

## Troubleshooting
If a node is failing to sync, verify that TCP port `7070` is open between the nodes (`ufw allow 7070/tcp`), and check the mesh connectivity status using the journal logs:
```bash
journalctl -u aitbc-blockchain-p2p -n 50 --no-pager
```
You should see output similar to `Successfully dialed outbound peer at aitbc1:7070` or `Handshake accepted from node...`
