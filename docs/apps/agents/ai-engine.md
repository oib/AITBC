# AI Engine

## Status
✅ Operational

## Overview
AI engine for autonomous agent operations, decision making, and learning capabilities.

## Architecture

### Core Components
- **Decision Engine**: AI-powered decision making module
- **Learning System**: Real-time learning and adaptation
- **Model Management**: Model deployment and versioning
- **Inference Engine**: High-performance inference for AI models
- **Task Scheduler**: AI-driven task scheduling and optimization

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- GPU support (optional for accelerated inference)
- AI model files

### Installation
```bash
cd /opt/aitbc/apps/ai-engine
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
AI_MODEL_PATH=/path/to/models
INFERENCE_DEVICE=cpu|cuda
MAX_CONCURRENT_TASKS=10
LEARNING_ENABLED=true
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Download or train AI models
5. Configure model paths
6. Run tests: `pytest tests/`

### Project Structure
```
ai-engine/
├── src/
│   ├── decision_engine/     # Decision making logic
│   ├── learning_system/     # Learning and adaptation
│   ├── model_management/    # Model deployment
│   ├── inference_engine/    # Inference service
│   └── task_scheduler/      # AI-driven scheduling
├── models/                  # AI model files
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_inference.py

# Run with GPU support
CUDA_VISIBLE_DEVICES=0 pytest tests/
```

## API Reference

### Decision Making

#### Make Decision
```http
POST /api/v1/ai/decision
Content-Type: application/json

{
  "context": {},
  "options": ["option1", "option2"],
  "constraints": {}
}
```

#### Get Decision History
```http
GET /api/v1/ai/decisions?limit=10
```

### Learning

#### Trigger Learning
```http
POST /api/v1/ai/learning/train
Content-Type: application/json

{
  "data_source": "string",
  "epochs": 100,
  "batch_size": 32
}
```

#### Get Learning Status
```http
GET /api/v1/ai/learning/status
```

### Inference

#### Run Inference
```http
POST /api/v1/ai/inference
Content-Type: application/json

{
  "model": "string",
  "input": {},
  "parameters": {}
}
```

#### Batch Inference
```http
POST /api/v1/ai/inference/batch
Content-Type: application/json

{
  "model": "string",
  "inputs": [{}],
  "parameters": {}
}
```

## Configuration

### Environment Variables
- `AI_MODEL_PATH`: Path to AI model files
- `INFERENCE_DEVICE`: Device for inference (cpu/cuda)
- `MAX_CONCURRENT_TASKS`: Maximum concurrent inference tasks
- `LEARNING_ENABLED`: Enable/disable learning system
- `LEARNING_RATE`: Learning rate for training
- `BATCH_SIZE`: Batch size for inference
- `MODEL_CACHE_SIZE`: Cache size for loaded models

### Model Management
- **Model Versioning**: Track model versions and deployments
- **Model Cache**: Cache loaded models for faster inference
- **Model Auto-scaling**: Scale inference based on load

## Troubleshooting

**Model loading failed**: Check model path and file integrity.

**Inference slow**: Verify GPU availability and batch size settings.

**Learning not progressing**: Check learning rate and data quality.

**Out of memory errors**: Reduce batch size or model size.

## Security Notes

- Validate all inference inputs
- Sanitize model outputs
- Monitor for adversarial attacks
- Regularly update AI models
- Implement rate limiting for inference endpoints
