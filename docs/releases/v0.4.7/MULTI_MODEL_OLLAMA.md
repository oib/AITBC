# Multi-Model Ollama Support - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 enables shop owners to offer multiple Ollama models with different pricing, supporting both local and cloud deployment.

## Features

### Deployment Type Auto-Detection
Models ending with `:cloud` are automatically classified as cloud deployment:
```bash
# Local model (auto-detected)
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour

# Cloud model (auto-detected)
aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour
```

### Blockchain Payload
```json
{
  "action": "software_offer",
  "deployment_type": "local|cloud",
  "model": "llama3.2:3b",
  ...
}
```

### CLI Options
- `--deployment-type` - Manual override (removed in v0.4.7, now inferred from model name suffix)
- Different pricing per model
- Deployment type visible in offer listings

## Results

- ✅ Multiple Ollama models can be offered (local and cloud)
- ✅ Auto-detection of deployment type from model name suffix
- ✅ Different pricing per model
- ✅ Deployment type visible in offer listings

---

*Last Updated: 2026-06-05*
