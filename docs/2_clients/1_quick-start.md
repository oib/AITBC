# Client Quick Start

**5 minutes** — Install, configure, submit your first job.

## 1. Install & Configure

```bash
pip install -e .                                        # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key
```

## 2. Create Wallet

```bash
aitbc wallet create --name my-wallet
```

Save your seed phrase securely.

## 3. Submit a Job

```bash
aitbc client submit --prompt "Summarize this document" --input data.txt
```

## 4. Track & Download

```bash
aitbc client status --job-id <JOB_ID>
aitbc client download --job-id <JOB_ID> --output ./results
```

## Next

- [2_job-submission.md](./2_job-submission.md) — Advanced job options (GPU, priority, batch)
- [3_job-lifecycle.md](./3_job-lifecycle.md) — Status tracking, results, history
- [5_pricing-billing.md](./5_pricing-billing.md) — Cost structure
