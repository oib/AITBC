# AITBC Local Simulation

Simulate client and GPU provider interactions with independent wallets and AITBC transactions.

## Structure

```
home/
├── genesis.py          # Creates genesis block and distributes initial AITBC
├── client/            # Customer/client wallet
│   └── wallet.py      # Client wallet management
├── miner/             # GPU provider wallet
│   └── wallet.py      # Miner wallet management
└── simulate.py        # Complete workflow simulation
```

## Quick Start

### 1. Initialize the Economy
```bash
cd /home/oib/windsurf/aitbc/home
python3 genesis.py
```
This creates:
- Genesis wallet: 1,000,000 AITBC
- Client wallet: 10,000 AITBC 
- Miner wallet: 1,000 AITBC

### 2. Check Wallets
```bash
# Client wallet
cd client && python3 wallet.py balance

# Miner wallet  
cd miner && python3 wallet.py balance
```

### 3. Run Complete Simulation
```bash
cd /home/oib/windsurf/aitbc/home
python3 simulate.py
```

## Wallet Commands

### Client Wallet
```bash
cd client

# Check balance
python3 wallet.py balance

# Show address
python3 wallet.py address

# Pay for services
python3 wallet.py send <amount> <address> <description>

# Transaction history
python3 wallet.py history
```

### Miner Wallet
```bash
cd miner

# Check balance with stats
python3 wallet.py balance

# Add earnings from completed job
python3 wallet.py earn <amount> --job <job_id> --desc "Service description"

# Withdraw earnings
python3 wallet.py withdraw <amount> <address>

# Mining statistics
python3 wallet.py stats
```

## Example Workflow

### 1. Client Submits Job
```bash
cd /home/oib/windsurf/aitbc/cli
python3 client.py submit inference --model llama-2-7b --prompt "What is AI?"
```

### 2. Miner Processes Job
```bash
# Miner polls and gets job
python3 miner.py poll

# Miner earns AITBC
cd /home/oib/windsurf/aitbc/home/miner
python3 wallet.py earn 50.0 --job abc123 --desc "Inference task"
```

### 3. Client Pays
```bash
cd /home/oib/windsurf/aitbc/home/client

# Get miner address
cd ../miner && python3 wallet.py address
# Returns: aitbc1721d5bf8c0005ded6704

# Send payment
cd ../client
python3 wallet.py send 50.0 aitbc1721d5bf8c0005ded6704 "Payment for inference"
```

## Wallet Files

- `client/client_wallet.json` - Client's wallet data
- `miner/miner_wallet.json` - Miner's wallet data
- `genesis_wallet.json` - Genesis wallet with remaining AITBC

## Integration with CLI Tools

The home wallets integrate with the CLI tools:

1. Submit jobs using `cli/client.py`
2. Process jobs using `cli/miner.py`
3. Track payments using `home/*/wallet.py`

## Tips

- Each wallet has a unique address
- All transactions are recorded with timestamps
- Genesis wallet holds the remaining AITBC supply
- Use `simulate.py` for a complete demo
- Check `wallet.py history` to see all transactions
