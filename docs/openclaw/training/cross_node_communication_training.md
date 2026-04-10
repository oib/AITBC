# Cross-Node Communication Training Module

## Overview

This training module teaches OpenClaw agents how to establish, verify, and utilize cross-node communication channels over the AITBC blockchain network. It enables agents to coordinate tasks and exchange messages between different blockchain nodes.

## Prerequisites

### System Requirements
- AITBC blockchain nodes synchronized and communicating on port 8006
- Both nodes operational (genesis node `aitbc1` and follower node `aitbc`)
- Funded wallets on both nodes for transaction fees
- Python 3.13+ with cryptography library
- SQLModel for database access

### Wallet Configuration
- **Genesis Node (aitbc1)**: `temp-agent2` wallet with AIT for fees
- **Follower Node (aitbc)**: `temp-agent` wallet for message sending
- Both wallets should be created with known passwords

## Training Workflow

### Module 1: Cross-Node Agent Registration

**Objective**: Register OpenClaw agents on multiple distinct blockchain nodes.

**Commands**:
```bash
# Genesis Node (aitbc1: 10.1.223.40)
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent create \
  --name "openclaw-genesis-commander" \
  --description "Primary coordinator agent on genesis node" \
  --verification full

# Follower Node (aitbc: 10.1.223.93)
NODE_URL=http://localhost:8006 ./aitbc-cli agent create \
  --name "openclaw-follower-worker" \
  --description "Worker agent on follower node" \
  --verification full
```

**Expected Output**:
```
Agent create:
  Agent Id: agent_1775817987
  Name: openclaw-genesis-commander
  Status: Created
  Verification Level: full
```

### Module 2: Cross-Node Messaging Protocol

**Objective**: Send messages between agents using blockchain transaction payloads.

**Implementation**: Since `aitbc-cli agent message` is currently mocked, use custom Python scripts:

```python
# send_ping.py
import requests, json, hashlib, time
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

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

# Send ping message
priv = decrypt_wallet("/var/lib/aitbc/keystore/temp-agent.json", "temp123")
tx = create_tx(priv, "ait1d18e286fc0c12888aca94732b5507c8787af71a5", 
              "ait16af0b743fd6a2d3e2e2f28a820066706aa5813b5", 0, 10, "ping")
response = requests.post("http://10.1.223.40:8006/rpc/transaction", json=tx)
print("Ping sent:", response.json())
```

### Module 3: Message Retrieval and Parsing

**Objective**: The follower agent must listen for and decode messages.

**Agent Daemon Implementation**:
```python
# agent_daemon.py
import time
from sqlmodel import create_engine, Session, select
from aitbc_chain.models import Transaction

MY_ADDRESS = "ait16af0b743fd6a2d3e2e2f28a820066706aa5813b5"
engine = create_engine("sqlite:////var/lib/aitbc/data/ait-mainnet/chain.db")

processed_txs = set()

while True:
    with Session(engine) as session:
        txs = session.exec(
            select(Transaction).where(Transaction.recipient == MY_ADDRESS)
        ).all()
        
        for tx in txs:
            if tx.id in processed_txs: continue
            processed_txs.add(tx.id)
            
            # Parse payload
            data = ""
            if hasattr(tx, "tx_metadata") and tx.tx_metadata:
                if isinstance(tx.tx_metadata, dict):
                    data = tx.tx_metadata.get("payload", "")
            elif hasattr(tx, "payload") and tx.payload:
                if isinstance(tx.payload, dict):
                    data = tx.payload.get("payload", "")
            
            # Process message
            if "ping" in str(data):
                print(f"Received ping from {tx.sender}")
                # Send pong reply
    time.sleep(2)
```

### Module 4: Distributed Task Execution

**Objective**: Combine AI job submission with cross-node agent coordination.

**Workflow**:
1. Genesis agent instructs follower to execute AI job
2. Follower receives instruction and executes locally
3. Follower returns result to genesis via blockchain transaction

**Example Transaction**:
```python
# Send AI job instruction
job_payload = {
    "cmd": "EXECUTE_AI_JOB",
    "type": "inference",
    "prompt": "Analyze system load"
}

tx = create_tx(priv, genesis_addr, follower_addr, 0, 10, json.dumps(job_payload))
response = requests.post(f"{RPC_URL}/rpc/transaction", json=tx)
```

## Automated Training Script

### Location
`/opt/aitbc/scripts/training/openclaw_cross_node_comm.sh`

### Usage
```bash
# Interactive training mode
cd /opt/aitbc/scripts/training
./openclaw_cross_node_comm.sh

# Automated evaluation mode
./openclaw_cross_node_comm.sh --auto-eval
```

### Script Features
- Automated agent registration on both nodes
- Simulated message exchange protocol
- Message retrieval and parsing demonstration
- Distributed task execution simulation
- Logging and success verification

## Success Validation

An OpenClaw agent has mastered cross-node communication when it can:

1. **Parse Local State**: Find remote agent IDs from blockchain state
2. **Construct Messages**: Create valid JSON payload transactions
3. **Broadcast Transactions**: Successfully submit messages via RPC
4. **Poll for Messages**: Automatically check for incoming messages
5. **Handle Latency**: Manage network delays with retry logic
6. **Complete Round-Trip**: Genesis → Follower → Genesis within 60 seconds

## Test Results

### Ping-Pong Test Execution
**Date**: April 10, 2026
**Test Block**: 26952
**Result**: ✅ Success

```
Genesis Node: Sent "ping" → Follower Node
Follower Node: Received "ping" → Sent "pong" → Genesis Node
Genesis Node: Received "pong" in Block 26952
```

### Performance Metrics
- **Round-trip Time**: ~10 seconds
- **Message Size**: 4 bytes
- **Transaction Fee**: 10 AIT per message
- **Success Rate**: 100%

## Known Limitations

### CLI Limitations
- `aitbc-cli agent message` returns "Not implemented yet"
- `aitbc-cli agent messages` returns "Not implemented yet"
- `/rpc/transactions` endpoint returns "Not Found"

### Workarounds
- Custom Python scripts for transaction creation
- Direct database queries for message retrieval
- Autonomous agent daemon for message handling

## Troubleshooting

### Agent Daemon Not Starting
```bash
# Check logs
ssh aitbc1 'cat /tmp/agent_daemon4.log'

# Verify wallet access
ssh aitbc1 '/opt/aitbc/venv/bin/python -c "from scripts import decrypt_wallet"'
```

### Transactions Not Mining
```bash
# Check mempool
curl http://localhost:8006/rpc/mempool

# Verify nonce uniqueness
# Ensure nonces are unique per sender
```

### Sync Issues
```bash
# Manual sync
python /tmp/sync_once.py

# Check block heights
NODE_URL=http://localhost:8006 ./aitbc-cli blockchain height
```

## Related Documentation

- [Cross-Node Communication Implementation Guide](../guides/openclaw_cross_node_communication.md)
- [Blockchain Synchronization Issues](../blockchain/blockchain_synchronization_issues_and_fixes.md)
- [Training Workflow](../../../../.windsurf/workflows/openclaw-cross-node-communication.md)

## Advanced Topics

### Message Encryption
Future implementations should add encryption for sensitive message payloads.

### Message Queuing
Implement message queue management for high-volume communication.

### Agent Discovery
Add agent discovery service for dynamic agent-to-agent communication.

### Acknowledgment Protocol
Implement reliable message acknowledgment protocol for critical communications.

---

**Last Updated**: 2026-04-10
**Version**: 1.0
**Status**: Production Tested
