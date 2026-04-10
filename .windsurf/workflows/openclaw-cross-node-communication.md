---
description: OpenClaw specialized training workflow for agent-to-agent cross-node communication via AITBC blockchain
title: OpenClaw Cross-Node Communication Training
version: 1.0
---

# OpenClaw Cross-Node Communication Training

## Purpose
This specialized training module teaches OpenClaw agents how to establish, verify, and utilize cross-node communication channels over the AITBC blockchain network (between genesis node `aitbc` and follower node `aitbc1`).

## Learning Objectives
1. **Agent Registration**: Register OpenClaw agents on multiple distinct blockchain nodes.
2. **Peer Discovery**: Discover agent endpoints and IDs across the blockchain state.
3. **Cross-Node Messaging**: Send and receive secure messages via blockchain transactions.
4. **Task Coordination**: Delegate AI tasks from a genesis-based agent to a follower-based agent.
5. **Event Monitoring**: Subscribe to and parse blockchain events for incoming messages.

## Prerequisites
- Completed [Stage 2 of the Mastery Plan](/OPENCLAW_AITBC_MASTERY_PLAN.md)
- Both nodes synchronized and communicating on port 8006
- Funded wallets on both nodes (`openclaw-trainee` and `follower-ops`)

## Training Modules

### Module 1: Cross-Node Agent Registration
Agents must be registered on the blockchain to receive messages.

```bash
# Genesis Node (aitbc: 10.1.223.40)
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent create \
  --name "openclaw-genesis-commander" \
  --description "Primary coordinator agent on genesis node" \
  --verification full \
  --verbose

# Follower Node (aitbc1: <aitbc1-ip>)
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent create \
  --name "openclaw-follower-worker" \
  --description "Worker agent on follower node" \
  --verification full \
  --debug
```

### Module 2: Cross-Node Messaging Protocol
Learn to format and transmit messages between the registered agents.

```bash
# Get follower agent ID
FOLLOWER_AGENT_ID=$(NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent list --output json | jq -r '.[] | select(.name=="openclaw-follower-worker") | .id')

# Send instruction from genesis to follower
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent message \
  --to $FOLLOWER_AGENT_ID \
  --content "{\"cmd\":\"STATUS_REPORT\",\"priority\":\"high\"}" \
  --verbose
```

### Module 3: Message Retrieval and Parsing
The follower agent must listen for and decode messages.

```bash
# Retrieve messages on follower node
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent messages \
  --from openclaw-genesis-commander \
  --output json

# Acknowledge receipt (Follower -> Genesis)
GENESIS_AGENT_ID=$(NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent list --output json | jq -r '.[] | select(.name=="openclaw-genesis-commander") | .id')

NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent message \
  --to $GENESIS_AGENT_ID \
  --content "{\"cmd\":\"ACK\",\"status\":\"READY\"}" \
  --debug
```

### Module 4: Distributed Task Execution
Combine AI job submission with cross-node agent coordination.

```bash
# Genesis instructs Follower to execute AI Job
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent message \
  --to $FOLLOWER_AGENT_ID \
  --content "{\"cmd\":\"EXECUTE_AI_JOB\",\"type\":\"inference\",\"prompt\":\"Analyze load\"}"

# Follower receives, executes locally, and returns result to Genesis
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli ai job submit \
  --type inference \
  --prompt "Analyze load" \
  --yes

NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent message \
  --to $GENESIS_AGENT_ID \
  --content "{\"cmd\":\"JOB_COMPLETE\",\"result_id\":\"job_123\"}"
```

## Automated Training Script
Execute the specialized training script to practice these operations autonomously.

**Script Path:** `/opt/aitbc/scripts/training/openclaw_cross_node_comm.sh`

```bash
# Run the interactive training
cd /opt/aitbc/scripts/training
./openclaw_cross_node_comm.sh

# Run in automated evaluation mode
./openclaw_cross_node_comm.sh --auto-eval
```

## Success Validation
An OpenClaw agent has mastered cross-node communication when it can:
1. Parse the local state to find remote agent IDs.
2. Construct and broadcast a valid JSON payload in an `agent message` transaction.
3. Automatically poll or listen for response messages on the remote node.
4. Handle network latency or temporary sync delays gracefully using retry logic.
5. Successfully complete a round-trip (Genesis -> Follower -> Genesis) message exchange within 60 seconds.

## Related Skills
- [aitbc-node-coordinator](/aitbc-node-coordinator.md)
- [openclaw-coordination-orchestrator](/openclaw-coordination-orchestrator.md)
