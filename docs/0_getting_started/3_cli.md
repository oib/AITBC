# CLI Usage

## Setup

```bash
pip install -e .                                    # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key                       # or use --api-key
```

## Global Options

| Option | Description |
|--------|-------------|
| `--url URL` | Coordinator API URL |
| `--api-key KEY` | API key for authentication |
| `--output table\|json\|yaml` | Output format |
| `-v / -vv / -vvv` | Verbosity level |
| `--debug` | Debug mode |

## Command Groups

| Group | Key commands |
|-------|-------------|
| `client` | `submit`, `status`, `list`, `cancel`, `download`, `batch-submit` |
| `miner` | `register`, `poll`, `mine`, `earnings`, `deregister` |
| `wallet` | `balance`, `send`, `stake`, `backup`, `multisig-create` |
| `auth` | `login`, `logout`, `token`, `keys` |
| `blockchain` | `status`, `blocks`, `transaction`, `validators` |
| `marketplace` | `gpu list`, `gpu book`, `orders`, `reviews` |
| `admin` | `status`, `jobs`, `miners`, `audit-log` |
| `config` | `set`, `show`, `profiles`, `secrets` |
| `monitor` | `dashboard`, `metrics`, `alerts`, `webhooks` |
| `simulate` | `workflow`, `load-test`, `scenario` |

## Client Workflow

```bash
aitbc wallet balance                                # check funds
aitbc client submit --prompt "What is AI?"          # submit job
aitbc client status --job-id <JOB_ID>               # check progress
aitbc client download --job-id <JOB_ID> --output ./ # get results
```

## Miner Workflow

```bash
aitbc miner register --name gpu-1 --gpu a100 --count 4
aitbc miner poll                                    # start accepting jobs
aitbc wallet balance                                # check earnings
```

## Configuration

Config file: `~/.aitbc/config.yaml`
```yaml
coordinator_url: http://localhost:8000
api_key: your-api-key
output_format: table
log_level: INFO
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Auth error | `export AITBC_API_KEY=your-key` or `aitbc auth login` |
| Connection refused | Check coordinator: `curl http://localhost:8000/v1/health` |
| Unknown command | Update CLI: `pip install -e .` from monorepo root |

## Full Reference

See [5_reference/1_cli-reference.md](../5_reference/1_cli-reference.md) for all 90+ commands with detailed options.
