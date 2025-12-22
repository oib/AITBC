---
title: Creating Jobs
description: Learn how to create and submit AI jobs
---

# Creating Jobs

Jobs are the primary way to execute AI workloads on the AITBC platform.

## Job Types

- **AI Inference**: Run pre-trained models
- **Model Training**: Train new models
- **Data Processing**: Process datasets
- **Custom**: Custom computations

## Job Specification

A job specification includes:
- Model configuration
- Input/output formats
- Resource requirements
- Pricing constraints

## Example

```yaml
name: "image-classification"
type: "ai-inference"
model:
  type: "python"
  entrypoint: "model.py"
```

## Submitting Jobs

Use the CLI or API to submit jobs:

```bash
aitbc job submit job.yaml
```

## Monitoring

Track job progress through:
- CLI commands
- Web interface
- API endpoints
- WebSocket streams
