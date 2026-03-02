# Job Submission Guide

Submit compute jobs to the AITBC network using the enhanced CLI.

## Basic Submission

```bash
aitbc client submit --model gpt2 --input data.txt --output results/
```

## Enhanced Options Reference

| Option | Required | Description |
|--------|----------|-------------|
| `--model` | Yes | Model to run (e.g., gpt2, llama, stable-diffusion) |
| `--input` | Yes | Input file or data |
| `--output` | Yes | Output directory |
| `--gpu` | No | GPU requirements (v100, a100, rtx3090) |
| `--gpu-count` | No | Number of GPUs (default: 1) |
| `--timeout` | No | Job timeout in seconds (default: 3600) |
| `--priority` | No | Job priority (low, normal, high) |
| `--agent-id` | No | Specific agent ID for execution |
| `--workflow` | No | Agent workflow to use |

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

## Agent Workflow Submission (New)

```bash
# Submit job to specific agent workflow
aitbc client submit \
  --workflow ai_inference \
  --input '{"prompt": "Hello world"}' \
  --agent-id agent_123

# Submit with custom workflow configuration
aitbc client submit \
  --workflow custom_workflow \
  --input data.txt \
  --workflow-config '{"temperature": 0.8, "max_tokens": 1000}'
```

## Input Methods

### File Input

```bash
aitbc client submit --model gpt2 --input ./data/training_data.txt
```

### Direct Data Input

```bash
aitbc client submit --model gpt2 --input "What is AI?"
```

### JSON Input

```bash
aitbc client submit --model gpt2 --input '{"prompt": "Summarize this", "context": "AI training"}'
```

## Batch Submission (New)

```bash
# Create jobs file
cat > jobs.json << EOF
[
  {
    "model": "gpt2",
    "input": "What is machine learning?",
    "priority": "normal"
  },
  {
    "model": "llama",
    "input": "Explain blockchain",
    "priority": "high"
  }
]
EOF

# Submit batch jobs
aitbc client batch-submit --jobs-file jobs.json
```

## Job Templates (New)

```bash
# Create job template
aitbc client template create \
  --name inference_template \
  --model gpt2 \
  --priority normal \
  --timeout 3600

# Use template
aitbc client submit --template inference_template --input "Hello world"
```

## Advanced Submission Options

### Priority Jobs

```bash
aitbc client submit --model gpt2 --input data.txt --priority high
```

### Custom Timeout

```bash
aitbc client submit --model gpt2 --input data.txt --timeout 7200
```

### Specific Agent

```bash
aitbc client submit --model gpt2 --input data.txt --agent-id agent_456
```

### Custom Workflow

```bash
aitbc client submit \
  --workflow custom_inference \
  --input data.txt \
  --workflow-config '{"temperature": 0.7, "top_p": 0.9}'
```

## Marketplace Integration

### Find Available GPUs

```bash
aitbc marketplace gpu list
aitbc marketplace gpu list --model gpt2 --region us-west
```

### Submit with Marketplace GPU

```bash
aitbc client submit \
  --model gpt2 \
  --input data.txt \
  --gpu-type rtx4090 \
  --use-marketplace
```

## Job Monitoring

### Track Submission

```bash
aitbc client status --job-id <JOB_ID>
aitbc client list --status submitted
```

### Real-time Monitoring

```bash
aitbc monitor dashboard
aitbc monitor metrics --component jobs
```

## Troubleshooting

### Common Issues

```bash
# Check CLI configuration
aitbc --config

# Test connectivity
aitbc blockchain status

# Debug mode
aitbc --debug
```

### Job Failure Analysis

```bash
# Get detailed job information
aitbc client status --job-id <JOB_ID> --verbose

# Check agent status
aitbc agent status --agent-id <AGENT_ID>
```

## Best Practices

1. **Use appropriate GPU types** for your model requirements
2. **Set reasonable timeouts** based on job complexity
3. **Use batch submission** for multiple similar jobs
4. **Monitor job progress** with the dashboard
5. **Use templates** for recurring job patterns
6. **Leverage agent workflows** for complex processing pipelines

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
