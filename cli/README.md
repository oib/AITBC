# AITBC CLI Tools

Command-line tools for interacting with the AITBC network without using the web frontend.

## Tools

### 1. Client CLI (`client.py`)
Submit jobs and check their status.

```bash
# Submit an inference job
python3 client.py submit inference --model llama-2-7b --prompt "What is AITBC?"

# Check job status
python3 client.py status <job_id>

# List recent blocks
python3 client.py blocks --limit 5

# Submit a quick demo job
python3 client.py demo
```

### 2. Miner CLI (`miner.py`)
Register as a miner, poll for jobs, and earn AITBC.

```bash
# Register as a miner
python3 miner.py register --gpu "RTX 4060 Ti" --memory 16

# Poll for a single job
python3 miner.py poll --wait 5

# Mine continuously (process jobs as they come)
python3 miner.py mine --jobs 10

# Send heartbeat to coordinator
python3 miner.py heartbeat
```

### 3. Wallet CLI (`wallet.py`)
Track your AITBC earnings and manage your wallet.

```bash
# Check balance
python3 wallet.py balance

# Show transaction history
python3 wallet.py history --limit 10

# Add earnings (after completing a job)
python3 wallet.py earn 10.0 --job abc123 --desc "Inference task"

# Spend AITBC
python3 wallet.py spend 5.0 "Coffee break"

# Show wallet address
python3 wallet.py address
```

## GPU Testing

Before mining, verify your GPU is accessible:

```bash
# Quick GPU check
python3 test_gpu_access.py

# Comprehensive GPU test
python3 gpu_test.py

# Test miner with GPU
python3 miner_gpu_test.py --full
```

## Quick Start

1. **Start the SSH tunnel to remote server** (if not already running):
   ```bash
   cd /home/oib/windsurf/aitbc
   ./scripts/start_remote_tunnel.sh
   ```

2. **Run the complete workflow test**:
   ```bash
   cd /home/oib/windsurf/aitbc/cli
   python3 test_workflow.py
   ```

3. **Start mining continuously**:
   ```bash
   # Terminal 1: Start mining
   python3 miner.py mine
   
   # Terminal 2: Submit jobs
   python3 client.py submit training --model "stable-diffusion"
   ```

## Configuration

All tools default to connecting to `http://localhost:8001` (the remote server via SSH tunnel). You can override this:

```bash
python3 client.py --url http://localhost:8000 --api-key your_key submit inference
```

Default credentials:
- Client API Key: `REDACTED_CLIENT_KEY`
- Miner API Key: `REDACTED_MINER_KEY`

## Examples

### Submit and Process a Job

```bash
# 1. Submit a job
JOB_ID=$(python3 client.py submit inference --prompt "Test" | grep "Job ID" | cut -d' ' -f4)

# 2. In another terminal, mine it
python3 miner.py poll

# 3. Check the result
python3 client.py status $JOB_ID

# 4. See it in the blockchain
python3 client.py blocks
```

### Continuous Mining

```bash
# Register and start mining
python3 miner.py register
python3 miner.py mine --jobs 5

# In another terminal, submit multiple jobs
for i in {1..5}; do
    python3 client.py submit inference --prompt "Job $i"
    sleep 1
done
```

## Tips

- The wallet is stored in `~/.aitbc_wallet.json`
- Jobs appear as blocks immediately when created
- The proposer is assigned when a miner polls for the job
- Use `--help` with any command to see all options
- Mining earnings are added manually for now (will be automatic in production)

## Troubleshooting

- If you get "No jobs available", make sure a job was submitted recently
- If registration fails, check the coordinator is running and API key is correct
- If the tunnel is down, restart it with `./scripts/start_remote_tunnel.sh`
