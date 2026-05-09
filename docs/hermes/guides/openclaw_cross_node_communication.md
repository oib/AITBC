# hermes Cross-Node Communication Implementation Guide

## Overview

This guide documents the successful implementation and testing of cross-node agent communication between the AITBC blockchain nodes (`aitbc` and `aitbc1`). hermes agents can now autonomously communicate across different blockchain nodes by leveraging transaction payloads for message passing.

## Architecture

### Network Topology
- **Genesis Node (aitbc1)**: `10.1.223.40:8006` - Primary blockchain node
- **Follower Node (aitbc)**: `10.1.223.93:8006` - Secondary blockchain node
- **RPC Port**: `8006` on both nodes

**Environment Variables**:
```bash
export GENESIS_IP="10.1.223.40"  # aitbc1 (genesis node)
export FOLLOWER_IP="10.1.223.93"  # aitbc (follower node)
export RPC_PORT="8006"
export CHAIN_ID="ait-mainnet"
```

### Communication Mechanism

Agents communicate by embedding messages in blockchain transaction payloads:

```json
{
  "type": "transfer",
  "from": "ait1d18e286fc0c12888aca94732b5507c8787af71a5",
  "to": "ait16af0b743fd6a2d3e2e2f28a820066706aa5813b5",
  "amount": 0,
  "fee": 10,
  "nonce": 1775819657114,
  "payload": "ping",
  "chain_id": "ait-mainnet",
  "signature": "...",
  "public_key": "..."
}
```

### Agent Daemon Architecture

The autonomous agent daemon is managed as a systemd service (`aitbc-agent-daemon.service`) and runs on both nodes. The daemon:

1. **Systemd Service**: Managed by systemd for reliable operation and automatic restart
2. **Polls Blockchain State**: Queries the local SQLite database (`chain.db`) for incoming transactions
3. **Filters Messages**: Identifies transactions addressed to the agent's wallet
4. **Parses Payloads**: Extracts message content from transaction payloads
5. **Autonomous Replies**: Constructs and broadcasts reply transactions
6. **Cryptographic Signing**: Uses wallet private keys for transaction signing

**Service Management**:
```bash
# Start the agent daemon
sudo systemctl start aitbc-agent-daemon.service

# Check service status
sudo systemctl status aitbc-agent-daemon.service

# View service logs
sudo journalctl -u aitbc-agent-daemon -f

# Restart the service
sudo systemctl restart aitbc-agent-daemon.service
```

**Service Configuration**:
- **Service File**: `/etc/systemd/system/aitbc-agent-daemon.service`
- **Wrapper Script**: `/opt/aitbc/scripts/wrappers/aitbc-agent-daemon-wrapper.py`
- **Main Script**: `/opt/aitbc/apps/agent-coordinator/scripts/agent_daemon.py`
- **Wallet**: `temp-agent`
- **Agent Address**: `ait1d18e286fc0c12888aca94732b5507c8787af71a5`
- **Password File**: `/var/lib/aitbc/keystore/.agent_daemon_password`
- **RPC URL**: `http://localhost:8006`
- **Poll Interval**: 2 seconds

## Implementation Details

### Wallet Configuration

#### Genesis Node (aitbc1)
- **Wallet**: `temp-agent`
- **Address**: `ait1d18e286fc0c12888aca94732b5507c8787af71a5`
- **Password File**: `/var/lib/aitbc/keystore/.agent_daemon_password`
- **Balance**: 49,990 AIT (after funding)

#### Follower Node (aitbc)
- **Wallet**: `temp-agent`
- **Address**: `ait1d18e286fc0c12888aca94732b5507c8787af71a5`
- **Password File**: `/var/lib/aitbc/keystore/.agent_daemon_password`
- **Balance**: 0 AIT (sends zero-fee messages)

### Transaction Signing Process

```python
def create_tx(private_bytes, from_addr, to_addr, amount, fee, payload):
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    pub_hex = priv_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, 
        format=serialization.PublicFormat.Raw
    ).hex()
    
    tx = {
        "type": "transfer",
        "from": from_addr,
        "to": to_addr,
        "amount": amount,
        "fee": fee,
        "nonce": int(time.time() * 1000),
        "payload": payload,
        "chain_id": "ait-mainnet"
    }
    
    tx_string = json.dumps(tx, sort_keys=True)
    tx_hash = hashlib.sha256(tx_string.encode()).hexdigest()
    tx["signature"] = priv_key.sign(tx_string.encode()).hex()
    tx["public_key"] = pub_hex
    return tx
```

### Database Query Mechanism

Due to the `/rpc/transactions` endpoint being unimplemented, the agent daemon directly queries the blockchain database:

```python
from sqlmodel import create_engine, Session, select
from aitbc_chain.models import Transaction

engine = create_engine("sqlite:////var/lib/aitbc/data/ait-mainnet/chain.db")

with Session(engine) as session:
    txs = session.exec(
        select(Transaction).where(Transaction.recipient == MY_ADDRESS)
    ).all()
    
    for tx in txs:
        payload = tx.payload.get("payload", "")
        if "ping" in str(payload):
            # Send pong reply
```

## Testing Results

### Ping-Pong Test Execution

**Date**: April 10, 2026
**Test**: Cross-node message exchange between `aitbc` and `aitbc1`

#### Step 1: Send Ping (Genesis Node)
```bash
# Executed on aitbc (follower node)
python /tmp/send_ping2.py
```

**Result**: 
```
Ping sent: {
  'success': True, 
  'transaction_hash': '0x2b3c15c6233da21dd8683bd1d58c19a14e3123d92ac5705c8cfc645ca7524a49',
  'message': 'Transaction submitted to mempool'
}
```

#### Step 2: Autonomous Pong (Follower Node)
The agent daemon on `aitbc1` detected the ping and autonomously replied:

```
Agent daemon started. Listening for messages to ait16af0b743fd6a2d3e2e2f28a820066706aa5813b5...
Wallet unlocked successfully.
Received 'ping' from ait1d18e286fc0c12888aca94732b5507c8787af71a5! Sending 'pong'...
Pong sent successfully: {
  'success': True, 
  'transaction_hash': '0x133f241ddcb32e94f3b84e2763a1fd4a1d919b34525d680811e600eb0c6942bf',
  'message': 'Transaction submitted to mempool'
}
```

#### Step 3: Verification
```bash
python /tmp/check_pong.py
```

**Result**:
```
Success! Received PONG from ait16af0b743fd6a2d3e2e2f28a820066706aa5813b5 in block 26952
```

### Performance Metrics
- **Round-trip Time**: ~10 seconds (including block mining time)
- **Block Confirmation**: Block 26952
- **Message Size**: 4 bytes ("ping", "pong")
- **Transaction Fee**: 10 AIT per message

## Blockchain Synchronization Fixes

### Issue 1: Rate Limiting on Import Block

**Problem**: The `/rpc/importBlock` endpoint had a 1-second minimum rate limit, causing slow synchronization.

**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py`

**Fix**: Temporarily disabled the rate limit:
```python
# Before
if time_since_last < 1.0:
    await asyncio.sleep(1.0 - time_since_last)

# After
if False:  # time_since_last < 1.0
    await asyncio.sleep(1.0 - time_since_last)
```

### Issue 2: Blocks-Range Endpoint Limitation

**Problem**: The `/rpc/blocks-range` endpoint returns block metadata but not transaction data, causing follower nodes to import "empty" blocks.

**Location**: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py`

**Current Behavior**:
```python
return {
    "success": True,
    "blocks": [
        {
            "height": b.height, 
            "hash": b.hash, 
            "timestamp": b.timestamp.isoformat(), 
            "tx_count": b.tx_count  # Metadata only
        }
    ],
    "count": len(blocks)
}
```

**Workaround**: Agent daemon directly queries the local SQLite database instead of relying on RPC endpoints.

## Training Workflow

### Training Script
Location: `/opt/aitbc/scripts/training/hermes_cross_node_comm.sh`

### Workflow Documentation
Location: `/opt/aitbc/.windsurf/workflows/hermes-cross-node-communication.md`

### Training Modules
1. **Module 1**: Cross-Node Agent Registration
2. **Module 2**: Cross-Node Messaging Protocol
3. **Module 3**: Message Retrieval and Parsing
4. **Module 4**: Distributed Task Execution

## Known Limitations

### CLI Limitations
- `aitbc-cli agent message` command returns "Not implemented yet"
- `aitbc-cli agent messages` command returns "Not implemented yet"
- `/rpc/transactions?address={addr}` endpoint returns "Not Found"

### Workarounds Implemented
- Custom Python scripts for transaction creation and signing
- Direct database queries for transaction retrieval
- Autonomous agent daemon for message handling

## Security Considerations

### Wallet Security
- Wallets use AES-256-GCM encryption with PBKDF2 key derivation
- Private keys are stored in `/var/lib/aitbc/keystore/`
- Passwords are stored in `/var/lib/aitbc/keystore/.password`

### Transaction Security
- All transactions are cryptographically signed using Ed25519
- Nonce management prevents replay attacks
- Chain ID validation prevents cross-chain confusion

## Future Improvements

### Planned Enhancements
1. Implement missing RPC endpoints (`/rpc/transactions`, agent messaging)
2. Fix `/rpc/blocks-range` to include transaction data
3. Add encryption for message payloads
4. Implement message acknowledgment protocol
5. Add message queue management
6. Implement agent discovery service

### CLI Integration
- Implement proper `agent message` command
- Add `agent messages` for message retrieval
- Integrate with existing wallet commands

## Troubleshooting

### Agent Daemon Not Starting
```bash
# Check service status
sudo systemctl status aitbc-agent-daemon.service

# Check service logs
sudo journalctl -u aitbc-agent-daemon -n 50

# Start the service
sudo systemctl start aitbc-agent-daemon.service

# Verify wallet decryption
/opt/aitbc/venv/bin/python -c "
from pathlib import Path
import json
keystore_path = Path('/var/lib/aitbc/keystore/temp-agent.json')
with open(keystore_path) as f:
    data = json.load(f)
    print('Wallet loaded successfully')
"
```

### Sync Issues
```bash
# Check block heights on both nodes
NODE_URL=http://${GENESIS_IP}:${RPC_PORT} ./aitbc-cli blockchain height
NODE_URL=http://${FOLLOWER_IP}:${RPC_PORT} ./aitbc-cli blockchain height

# Check sync status
curl http://${GENESIS_IP}:${RPC_PORT}/rpc/head
curl http://${FOLLOWER_IP}:${RPC_PORT}/rpc/head
```

### Transaction Not Mining
```bash
# Check mempool
curl http://localhost:${RPC_PORT}/rpc/mempool

# Verify nonce uniqueness
# Ensure nonces are unique per sender

# Check blockchain node status
sudo systemctl status aitbc-blockchain-node.service
```

## References

### Related Documentation
- [hermes README](../README.md)
- [Training Workflow](../../../.windsurf/workflows/hermes-cross-node-communication.md)
- [Blockchain Operations](../../blockchain/)

### Source Code
- Agent Daemon Service: `/etc/systemd/system/aitbc-agent-daemon.service`
- Agent Daemon Wrapper: `/opt/aitbc/scripts/wrappers/aitbc-agent-daemon-wrapper.py`
- Agent Daemon Script: `/opt/aitbc/apps/agent-coordinator/scripts/agent_daemon.py`
- Training Script: `/opt/aitbc/scripts/training/hermes_cross_node_comm.sh`

---

**Last Updated**: 2026-05-09
**Version**: 2.0
**Status**: Production Tested - Updated for systemd service management
