# Job Submission Guide

Submit compute jobs to the AITBC network.

## Basic Submission

```bash
aitbc client submit --model gpt2 --input data.txt --output results/
```

## Options Reference

| Option | Required | Description |
|--------|----------|-------------|
| `--model` | Yes | Model to run (e.g., gpt2, llama, stable-diffusion) |
| `--input` | Yes | Input file or data |
| `--output` | Yes | Output directory |
| `--gpu` | No | GPU requirements (v100, a100, rtx3090) |
| `--gpu-count` | No | Number of GPUs (default: 1) |
| `--timeout` | No | Job timeout in seconds (default: 3600) |
| `--priority` | No | Job priority (low, normal, high) |

## GPU Requirements

### Single GPU

```bash
aitbc client submit --model gpt2 --input data.txt --gpu v100
```

### Multiple GPUs

```bash
aitbc client submit --model llama --input data.txt --gpu a100 --gpu-count 4
```

### Specific GPU Type

```bash
aitbc client submit --model stable-diffusion --input data.txt --gpu rtx3090
```

## Input Methods

### File Input

```bash
aitbc client submit --model gpt2 --input ./data/training_data.txt
```

### Inline Input

```bash
aitbc client submit --model gpt2 --input "Hello, world!"
```

### URL Input

```bash
aitbc client submit --model gpt2 --input https://example.com/data.txt
```

## Output Options

### Local Directory

```bash
aitbc client submit --model gpt2 --input data.txt --output ./results
```

### S3 Compatible Storage

```bash
aitbc client submit --model gpt2 --input data.txt --output s3://my-bucket/results
```

## Job Priority

| Priority | Speed | Cost |
|----------|-------|------|
| low | Standard | 1x |
| normal | Fast | 1.5x |
| high | Priority | 2x |

## Examples

### Training Job

```bash
aitbc client submit \
  --model llama \
  --input ./training_data.csv \
  --output ./model_weights \
  --gpu a100 \
  --gpu-count 4 \
  --timeout 7200 \
  --priority high
```

### Inference Job

```bash
aitbc client submit \
  --model gpt2 \
  --input ./prompts.txt \
  --output ./outputs \
  --gpu v100 \
  --timeout 600
```

## Batch Jobs

Submit multiple jobs at once:

```bash
# Using a job file
aitbc client submit-batch --file jobs.yaml
```

Example `jobs.yaml`:

```yaml
jobs:
  - model: gpt2
    input: data1.txt
    output: results1/
  - model: gpt2
    input: data2.txt
    output: results2/
```

## Next

- [3_job-lifecycle.md](./3_job-lifecycle.md) — Status, results, history, cancellation
- [5_pricing-billing.md](./5_pricing-billing.md) — Cost structure and invoices
