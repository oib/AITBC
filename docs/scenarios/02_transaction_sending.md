# Transaction Sending

**Level**: Beginner
**Prerequisites**: [Scenario 01 — Wallet Basics](./01_wallet_basics.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Transaction Sending

---

## See Also

- **Previous Scenario**: [Wallet Basics](./01_wallet_basics.md)
- **Next Scenario**: [Genesis Deployment](./03_genesis_deployment.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Agent Communication Guide**: [Agent Communication Guide](../agent-sdk/AGENT_COMMUNICATION_GUIDE.md)

---

## Scenario Overview

This scenario covers sending AIT token transactions and tracking their status on the blockchain. You will learn to use the `aitbc transactions` command group to send single transactions, batch multiple transfers from a JSON file, and query transaction status via the blockchain RPC or the Explorer API.

### Use Case

An AI agent needs to transfer AIT tokens to another address — for example, paying for compute resources, settling a marketplace purchase, or distributing rewards. The agent must sign the transaction with its wallet's private key, submit it to the blockchain node, and verify that it was included in a block.

### What You'll Learn

- How to send a single transaction with `aitbc transactions send`
- How to provide wallet passwords non-interactively (flag, file, or environment variable)
- How to send batch transactions from a JSON file
- How to check transaction status via RPC or the Explorer API
- How to estimate transaction fees before sending

---

## Prerequisites

### Knowledge Required

- Completion of [Scenario 01 — Wallet Basics](./01_wallet_basics.md)
- Understanding of blockchain transactions (sender, recipient, amount, fee, nonce)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A wallet created in Scenario 01 (e.g., `my-agent-wallet`)
- A running blockchain node at `http://localhost:8202` (the default RPC URL)

### Setup Required

- Ensure your wallet has a positive balance (use `aitbc agent request-coins` to get test tokens from the hub)
- Note the recipient address for testing (you can use a second wallet's address)

---

## Step-by-Step Workflow

### Step 1: Send a Single Transaction

The `send` command signs a transfer transaction with the sender wallet's private key (Ed25519) and submits it to the blockchain RPC endpoint. The default RPC URL is `http://localhost:8202`.

```bash
# Send 10 AIT from my-agent-wallet to a recipient address
aitbc transactions send \
  --from my-agent-wallet \
  --to aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6 \
  --amount 10.0 \
  --fee 0.001
```

**Password resolution** (in priority order):
1. `--password` flag (inline)
2. `--password-file` flag (read from file)
3. `AITBC_WALLET_PASSWORD` environment variable
4. Auto-detect unencrypted wallets (skip password)
5. Interactive `getpass` prompt (only if TTY available)

**Expected output:**
```
Transaction submitted: 0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b
Transaction sent: 0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b
```

### Step 2: Send with Non-Interactive Password (Automation)

For automated agent workflows, provide the password via environment variable or file to avoid TTY prompts:

```bash
# Using environment variable
export AITBC_WALLET_PASSWORD="my-secret-password"
aitbc transactions send \
  --from my-agent-wallet \
  --to aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6 \
  --amount 5.0

# Using password file
echo "my-secret-password" > /tmp/wallet.pass
aitbc transactions send \
  --from my-agent-wallet \
  --to aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6 \
  --amount 5.0 \
  --password-file /tmp/wallet.pass
```

### Step 3: Check Transaction Status via RPC

Query the blockchain node directly for transaction status using the transaction hash returned by `send`.

```bash
aitbc transactions status 0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b
```

**Expected output:**
```json
{
  "status": "confirmed",
  "block_height": 12345,
  "from": "aitbc1a3f5e7b9c2d4e6f8a1b3c5d7e9f2a4b6c8d0e2",
  "to": "aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6",
  "amount": 10,
  "fee": 1,
  "nonce": 0,
  "type": "TRANSFER"
}
```

### Step 4: Check Transaction Status via Explorer

Use the `--use-explorer` flag to query the Explorer API instead of the RPC endpoint:

```bash
aitbc transactions status 0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b --use-explorer
```

### Step 5: Send Batch Transactions

Create a JSON file with multiple transactions and submit them all at once. Each entry requires `from_wallet`, `to_address`, and `amount`; `fee` is optional (defaults to 10.0).

```bash
cat > /tmp/batch_tx.json << 'EOF'
[
  {
    "from_wallet": "my-agent-wallet",
    "to_address": "aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6",
    "amount": 5.0,
    "fee": 0.001
  },
  {
    "from_wallet": "my-agent-wallet",
    "to_address": "aitbc1a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
    "amount": 3.0
  }
]
EOF

aitbc transactions batch --transactions-file /tmp/batch_tx.json --password-file /tmp/wallet.pass
```

**Expected output:**
```
Transaction submitted: 0xabc123...
Transaction sent: my-agent-wallet → aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6 (5.0 AIT)
Transaction submitted: 0xdef456...
Transaction sent: my-agent-wallet → aitbc1a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8 (3.0 AIT)
Batch completed: 2/2 successful
```

### Step 6: Estimate Transaction Fee

Before sending, estimate the fee for a transaction:

```bash
aitbc transactions estimate-fee \
  --from my-agent-wallet \
  --to aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6 \
  --amount 10.0
```

**Expected output:**
```
Estimated fee: 36.0 AIT (default)
```

### Step 7: View Pending Transactions

List transactions in the mempool that have not yet been included in a block:

```bash
aitbc transactions pending
```

**Expected output:**
```
Pending transactions: 2
  - 0xabc123...: 5 AIT
  - 0xdef456...: 3 AIT
```

---

## Code Examples Using Agent SDK

The `aitbc_agent` SDK's `Agent` class does not expose a direct `send_transaction` method — transaction signing in the CLI uses Ed25519 keys, while the SDK's `AgentIdentity` uses RSA for message signing. For agent workflows, the recommended pattern is to invoke the `aitbc` CLI via `subprocess` or to use the shared `AITBCHTTPClient` to submit pre-signed transactions to the RPC endpoint.

### Example 1: Send a Transaction via CLI Subprocess

```python
import subprocess
import json

def send_transaction(from_wallet: str, to_address: str, amount: float,
                     password: str, rpc_url: str = "http://localhost:8202") -> str | None:
    """Send a transaction by invoking the aitbc CLI."""
    result = subprocess.run(
        [
            "aitbc", "transactions", "send",
            "--from", from_wallet,
            "--to", to_address,
            "--amount", str(amount),
            "--password", password,
            "--rpc-url", rpc_url,
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Transaction failed: {result.stderr}")
        return None
    # Parse the transaction hash from stdout
    for line in result.stdout.splitlines():
        if "Transaction sent:" in line:
            return line.split("Transaction sent:")[1].strip()
    return None

# Usage
tx_hash = send_transaction(
    from_wallet="my-agent-wallet",
    to_address="aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6",
    amount=10.0,
    password="my-secret-password",
)
print(f"Transaction hash: {tx_hash}")
```

### Example 2: Check Transaction Status via HTTP Client

```python
from aitbc.network import AITBCHTTPClient

def get_transaction_status(tx_hash: str, rpc_url: str = "http://localhost:8202") -> dict:
    """Query transaction status from the blockchain RPC."""
    client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
    return client.get(f"/rpc/transaction/{tx_hash}")

# Usage
status = get_transaction_status("0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b")
print(f"Status: {status.get('status')}")
print(f"Block:  {status.get('block_height')}")
```

### Example 3: Agent Identity for Message Signing

While the CLI handles transaction signing with Ed25519 wallet keys, the SDK's `Agent` class signs inter-agent messages with RSA. Here is how the agent signs a payload that can be verified by other agents:

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

agent = Agent.create(
    name="tx-agent",
    agent_type="inference",
    capabilities={"compute_type": "inference"},
)

# Sign a transaction notification message
notification = {
    "event": "transaction_sent",
    "tx_hash": "0x7a3b5c2d8e1f4a6b9c0d3e5f7a8b2c4d6e0f1a3b5c7d9e2f4a6b8c0d3e5f7a9b",
    "amount": 10.0,
}
signature = agent.identity.sign_message(notification)
print(f"Signed notification: {signature[:64]}...")

# Another agent can verify it
is_valid = agent.identity.verify_signature(notification, signature)
print(f"Verification: {is_valid}")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Send single transactions using `aitbc transactions send` with proper password handling
- Send batch transactions from a JSON file with `aitbc transactions batch`
- Query transaction status via RPC (`aitbc transactions status`) or the Explorer API (`--use-explorer`)
- Estimate fees and view pending transactions
- Integrate transaction sending into agent workflows via subprocess or HTTP client

---

## Validation

Verify that your transactions were sent and confirmed:

```bash
# Check the status of your last transaction
aitbc transactions status <your_tx_hash>

# View pending transactions (should be empty if all confirmed)
aitbc transactions pending

# Check your wallet balance
aitbc wallet balance my-agent-wallet
```

---

## Related Resources

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Previous Scenario: Wallet Basics](./01_wallet_basics.md)
- [Next Scenario: Genesis Deployment](./03_genesis_deployment.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
