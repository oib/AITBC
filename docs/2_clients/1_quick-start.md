# Client Quick Start

**5 minutes** — Install, configure, submit your first job with the enhanced AITBC CLI.

## 1. Install & Configure

```bash
pip install -e .                                        # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key

# Verify installation
aitbc --version
aitbc --debug
```

## 2. Create Wallet

```bash
aitbc wallet create --name my-wallet
aitbc wallet balance
```

Save your seed phrase securely.

## 3. Submit a Job

```bash
# Enhanced job submission with more options
aitbc client submit \
  --prompt "Summarize this document" \
  --input data.txt \
  --model gpt2 \
  --priority normal \
  --timeout 3600
```

## 4. Track & Download

```bash
# Enhanced job tracking
aitbc client status --job-id <JOB_ID>
aitbc client list --status submitted
aitbc client download --job-id <JOB_ID> --output ./results

# Monitor job progress
aitbc monitor dashboard
```

## 5. Advanced Features

```bash
# Batch job submission
aitbc client batch-submit --jobs-file jobs.json

# Job management
aitbc client list --status completed
aitbc client cancel --job-id <JOB_ID>

# Configuration management
aitbc config show
aitbc config profiles create production
```

## Next

- [2_job-submission.md](./2_job-submission.md) — Advanced job options (GPU, priority, batch)
- [3_job-lifecycle.md](./3_job-lifecycle.md) — Status tracking, results, history
- [5_pricing-billing.md](./5_pricing-billing.md) — Cost structure
