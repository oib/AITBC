# Wallet Basics

**Level**: Beginner
**Prerequisites**: None
**Estimated Time**: 15 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Wallet Basics

---

## See Also

- **Previous Scenario**: None (this is the first scenario)
- **Next Scenario**: [Transaction Sending](./02_transaction_sending.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Agent SDK Quick Start**: [Quick Start Guide](../agent-sdk/QUICK_START_GUIDE.md)

---

## Scenario Overview

This scenario demonstrates how to create, manage, back up, and restore AITBC wallets using the real `aitbc` CLI. Wallets are the foundation for every action an AI agent performs on the AITBC network — sending transactions, receiving tokens, signing messages, and registering with the coordinator.

### Use Case

An AI agent needs a wallet to hold AIT tokens and sign transactions. The agent must be able to create wallets of different types, switch between them, back them up for disaster recovery, and restore them when needed.

### What You'll Learn

- How to create HD and simple wallets with the `aitbc wallet create` command
- How to list and switch between wallets
- How to back up a wallet to an external file and restore it
- How to delete a wallet safely
- How to create an agent identity with cryptographic keys using the `aitbc_agent` SDK

---

## Prerequisites

### Knowledge Required

- Basic command-line familiarity
- Understanding of public/private key cryptography concepts

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Python 3.13+ with the `aitbc_agent` package installed (`pip install aitbc-agent-sdk`)

### Setup Required

- Ensure the wallet directory exists (the CLI creates `~/.aitbc/wallets/` automatically)
- No running blockchain node is required for wallet creation and management

---

## Step-by-Step Workflow

### Step 1: Create an HD Wallet

HD (Hierarchical Deterministic) wallets use ECDSA with the SECP256K1 curve. The CLI generates a private key, derives the public key, and computes an address from the public key hash. By default, wallets are encrypted at rest.

```bash
# Create an HD wallet (default type) with encryption
aitbc wallet create my-agent-wallet
```

You will be prompted to enter and confirm a password for wallet encryption.

**Expected output:**
```
Wallet encryption is enabled. Your private key will be encrypted at rest.
Enter password for wallet 'my-agent-wallet':
Confirm password:
Wallet 'my-agent-wallet' created successfully
my-agent-wallet  hd   aitbc1a3f5e7b9c2d4e6f8a1b3c5d7e9f2a4b6c8d0e2  /home/user/.aitbc/wallets/my-agent-wallet.json
```

### Step 2: Create a Simple Wallet (No Encryption)

Simple wallets use random bytes for the private key and address. The `--no-encrypt` flag skips encryption — useful for testing and automated agent workflows where interactive password prompts are not available.

```bash
# Create a simple wallet without encryption (for testing/automation)
aitbc wallet create test-wallet --type simple --no-encrypt
```

**Expected output:**
```
Wallet 'test-wallet' created successfully
test-wallet  simple  aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6  /home/user/.aitbc/wallets/test-wallet.json
```

### Step 3: List All Wallets

List every wallet stored in the wallet directory (`~/.aitbc/wallets/`).

```bash
aitbc wallet list
```

**Expected output:**
```
my-agent-wallet: aitbc1a3f5e7b9c2d4e6f8a1b3c5d7e9f2a4b6c8d0e2
test-wallet: aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6
```

### Step 4: Switch the Active Wallet

The active wallet is stored in `~/.aitbc/config.yaml` and used by default by other CLI commands (transactions, messaging, etc.).

```bash
aitbc wallet switch test-wallet
```

**Expected output:**
```
Switched to wallet 'test-wallet'
active_wallet  test-wallet
address        aitbc1f2e4d6c8b0a2e4f6d8c0b2a4e6f8d0c2b4a6
```

### Step 5: Back Up a Wallet

Create a copy of the wallet JSON file at a specified destination. If no destination is provided, a timestamped filename is generated in the current directory.

```bash
# Back up to a specific destination
aitbc wallet backup my-agent-wallet --destination /tmp/my-agent-backup.json
```

**Expected output:**
```
Wallet 'my-agent-wallet' backed up to '/tmp/my-agent-backup.json'
wallet       my-agent-wallet
backup_path  /tmp/my-agent-backup.json
timestamp    2026-06-25T12:00:00Z
```

```bash
# Back up with auto-generated timestamped filename
aitbc wallet backup test-wallet
```

**Expected output:**
```
Wallet 'test-wallet' backed up to 'test-wallet_backup_20260625_120000.json'
```

### Step 6: Restore a Wallet from Backup

Restore a wallet from a backup file. The `--force` flag overrides an existing wallet with the same name.

```bash
# Restore to a new wallet name
aitbc wallet restore /tmp/my-agent-backup.json restored-wallet
```

**Expected output:**
```
Wallet 'restored-wallet' restored from '/tmp/my-agent-backup.json'
```

```bash
# Force-restore over an existing wallet
aitbc wallet restore /tmp/my-agent-backup.json my-agent-wallet --force
```

### Step 7: Delete a Wallet

Delete a wallet permanently. Use `--confirm` to skip the interactive confirmation prompt (useful in automated scripts).

```bash
# Interactive confirmation
aitbc wallet delete test-wallet
```

**Expected output:**
```
Are you sure you want to delete wallet 'test-wallet'? This cannot be undone. [y/N]: y
Wallet 'test-wallet' deleted
```

```bash
# Skip confirmation (for automation)
aitbc wallet delete test-wallet --confirm
```

---

## Code Examples Using Agent SDK

### Example 1: Create an Agent with Wallet Identity

The `aitbc_agent` SDK's `Agent.create()` classmethod generates an RSA key pair and wraps it in an `AgentIdentity` object. The agent's address is derived from the generated identity and is used for all network operations.

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# Create a new agent with generated cryptographic identity
agent = Agent.create(
    name="my-ai-agent",
    agent_type="inference",
    capabilities={
        "compute_type": "inference",
        "gpu_memory": 16384,
        "supported_models": ["llama-3", "mistral-7b"],
        "performance_score": 0.95,
        "max_concurrent_jobs": 4,
        "specialization": "natural-language",
    },
)

# The agent carries wallet-like identity info
print(f"Agent ID:    {agent.identity.id}")
print(f"Agent Name:  {agent.identity.name}")
print(f"Address:     {agent.identity.address}")
print(f"Public Key:  {agent.identity.public_key[:60]}...")
print(f"Registered:  {agent.registered}")
```

**Expected output:**
```
Agent ID:    agent_a1b2c3d4
Agent Name:  my-ai-agent
Address:     0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b
Public Key:  -----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxK7v...
Registered:  False
```

### Example 2: Sign and Verify a Message with Agent Identity

The `AgentIdentity` object provides `sign_message()` and `verify_signature()` methods using RSA with PSS padding and SHA-256.

```python
from aitbc_agent import Agent, AgentIdentity, AgentCapabilities

# Create an agent
agent = Agent.create(
    name="signing-demo",
    agent_type="processing",
    capabilities={"compute_type": "processing"},
)

# Sign a message
message = {"action": "register", "timestamp": "2026-06-25T12:00:00Z"}
signature = agent.identity.sign_message(message)
print(f"Signature: {signature[:64]}...")

# Verify the signature
is_valid = agent.identity.verify_signature(message, signature)
print(f"Signature valid: {is_valid}")
```

**Expected output:**
```
Signature: 3a7f2b1c4d5e6f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a...
Signature valid: True
```

### Example 3: Export Agent to Dictionary

The `to_dict()` method serializes the agent's identity and capabilities for storage or transmission.

```python
from aitbc_agent import Agent

agent = Agent.create(
    name="export-demo",
    agent_type="inference",
    capabilities={"compute_type": "inference", "gpu_memory": 8192},
)

agent_dict = agent.to_dict()
print(agent_dict)
```

**Expected output:**
```python
{
    'id': 'agent_e5f6a7b8',
    'name': 'export-demo',
    'address': '0x2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c',
    'capabilities': {
        'compute_type': 'inference',
        'gpu_memory': 8192,
        'supported_models': [],
        'performance_score': 0.0,
        'max_concurrent_jobs': 1,
        'specialization': None,
    },
    'reputation_score': 0.0,
    'registered': False,
    'earnings': 0.0,
}
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Create HD and simple wallets with the `aitbc wallet create` command
- List, switch between, and delete wallets using the CLI
- Back up wallets to external files and restore them with `--force` when needed
- Create an AI agent identity with RSA cryptographic keys using the `aitbc_agent` SDK
- Sign and verify messages using the `AgentIdentity` class

---

## Validation

Verify that your wallets are correctly created and manageable:

```bash
# List all wallets — should show your created wallets
aitbc wallet list

# Verify the active wallet is set correctly
cat ~/.aitbc/config.yaml | grep active_wallet

# Verify a backup file exists and contains valid JSON
cat /tmp/my-agent-backup.json | python -m json.tool

# Verify the restored wallet matches the original
aitbc wallet list
```

---

## Related Resources

- [Agent SDK Documentation](../agent-sdk/README.md)
- [Agent SDK API Reference](../agent-sdk/API_REFERENCE.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Next Scenario: Transaction Sending](./02_transaction_sending.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
