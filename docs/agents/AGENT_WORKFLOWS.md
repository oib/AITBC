# Agent Workflows

This document describes the workflow orchestration system for multi-agent coordination in AITBC v0.4.6.

## Overview

The workflow orchestration system enables:
- Multi-step agent workflows with dependencies
- Workflow execution with state tracking
- Workflow templates for common patterns
- Error handling and retry logic
- Redis-based persistence

## Workflow Definition

A workflow consists of multiple steps, each executed by a specific agent with dependencies on other steps.

### Workflow Structure

```json
{
  "workflow_id": "wf_20260604103000_abc12345",
  "name": "transcription_pipeline",
  "description": "Audio transcription and translation pipeline",
  "created_at": "2026-06-04T10:30:00Z",
  "created_by": "user_001",
  "steps": [
    {
      "step_id": "wf_20260604103000_abc12345_step_0",
      "agent_id": "agent_whisper_001",
      "action": "transcribe",
      "parameters": {
        "model": "whisper-large",
        "language": "auto"
      },
      "dependencies": [],
      "timeout": 300,
      "max_retries": 3,
      "status": "pending"
    },
    {
      "step_id": "wf_20260604103000_abc12345_step_1",
      "agent_id": "agent_translation_001",
      "action": "translate",
      "parameters": {
        "target_language": "en",
        "model": "nllb-200"
      },
      "dependencies": ["wf_20260604103000_abc12345_step_0"],
      "timeout": 180,
      "max_retries": 3,
      "status": "pending"
    }
  ]
}
```

### Step Fields

- `step_id`: Unique identifier for the step
- `agent_id`: ID of the agent that executes this step
- `action`: The action/task to perform
- `parameters`: Input parameters for the action
- `dependencies`: List of step IDs that must complete before this step
- `timeout`: Maximum time (seconds) for step execution
- `max_retries`: Number of retry attempts on failure
- `status`: Current status (pending, running, completed, failed, skipped)

## Creating Workflows

### CLI

```bash
aitbc agent workflow create \
  --name "transcription_pipeline" \
  --description "Audio transcription pipeline" \
  --steps-file workflow.json \
  --coordinator-url http://localhost:9001
```

**workflow.json:**
```json
[
  {
    "agent_id": "agent_whisper_001",
    "action": "transcribe",
    "parameters": {"model": "whisper-large"},
    "dependencies": [],
    "timeout": 300
  },
  {
    "agent_id": "agent_translation_001",
    "action": "translate",
    "parameters": {"target_language": "en"},
    "dependencies": [],
    "timeout": 180
  }
]
```

### API

```bash
curl -X POST http://localhost:9001/api/v1/agent/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "transcription_pipeline",
    "description": "Audio transcription pipeline",
    "steps": [
      {
        "agent_id": "agent_whisper_001",
        "action": "transcribe",
        "parameters": {"model": "whisper-large"},
        "dependencies": [],
        "timeout": 300
      }
    ],
    "created_by": "user_001"
  }'
```

## Executing Workflows

### CLI

```bash
aitbc agent workflow execute \
  --workflow-id wf_20260604103000_abc12345 \
  --input-file inputs.json \
  --coordinator-url http://localhost:9001
```

**inputs.json:**
```json
{
  "audio_file": "/path/to/audio.mp3",
  "source_language": "auto"
}
```

### API

```bash
curl -X POST http://localhost:9001/api/v1/agent/workflows/wf_20260604103000_abc12345/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_parameters": {
      "audio_file": "/path/to/audio.mp3",
      "source_language": "auto"
    }
  }'
```

## Workflow Status

### CLI

```bash
aitbc agent workflow status \
  --workflow-id wf_20260604103000_abc12345 \
  --coordinator-url http://localhost:9001
```

### API

```bash
curl http://localhost:9001/api/v1/agent/workflows/wf_20260604103000_abc12345/status
```

**Response:**
```json
{
  "execution_id": "exec_20260604103100_def67890",
  "workflow_id": "wf_20260604103000_abc12345",
  "status": "running",
  "current_step_index": 1,
  "results": {
    "wf_20260604103000_abc12345_step_0": {
      "status": "success",
      "output": "...",
      "timestamp": "2026-06-04T10:31:00Z"
    }
  },
  "error": null,
  "started_at": "2026-06-04T10:31:00Z",
  "completed_at": null,
  "steps": [...]
}
```

## Listing Workflows

### CLI

```bash
aitbc agent workflow list --coordinator-url http://localhost:9001
```

### API

```bash
curl http://localhost:9001/api/v1/agent/workflows
```

**Response:**
```json
{
  "workflows": [
    {
      "workflow_id": "wf_20260604103000_abc12345",
      "name": "transcription_pipeline",
      "description": "Audio transcription pipeline",
      "steps": [...],
      "created_at": "2026-06-04T10:30:00Z",
      "created_by": "user_001"
    }
  ],
  "count": 1
}
```

## Workflow Templates

### Transcription Pipeline

```json
[
  {
    "agent_id": "${whisper_agent}",
    "action": "transcribe",
    "parameters": {
      "model": "whisper-large",
      "language": "${source_language}"
    },
    "dependencies": [],
    "timeout": 300
  },
  {
    "agent_id": "${translation_agent}",
    "action": "translate",
    "parameters": {
      "target_language": "${target_language}"
    },
    "dependencies": ["step_0"],
    "timeout": 180
  }
]
```

### Multi-Model Inference

```json
[
  {
    "agent_id": "${ollama_agent}",
    "action": "inference",
    "parameters": {
      "model": "${model}",
      "prompt": "${prompt}"
    },
    "dependencies": [],
    "timeout": 600
  },
  {
    "agent_id": "${validation_agent}",
    "action": "validate",
    "parameters": {
      "check_quality": true
    },
    "dependencies": ["step_0"],
    "timeout": 60
  }
]
```

## Error Handling

### Retry Logic

Steps that fail are automatically retried up to `max_retries` times. The retry count is incremented after each failure.

### Step Failure

If a step fails after all retries:
- The workflow status is set to `failed`
- The `error` field contains the error message
- Subsequent dependent steps are skipped

### Cancellation

Workflows can be cancelled at any time:

```bash
# CLI
aitbc agent workflow cancel --execution-id exec_20260604103100_def67890

# API
curl -X POST http://localhost:9001/api/v1/agent/workflows/executions/exec_20260604103100_def67890/cancel
```

## Execution States

- `pending` - Workflow created, not yet started
- `running` - Workflow is executing
- `completed` - All steps completed successfully
- `failed` - One or more steps failed
- `cancelled` - Workflow was cancelled
- `paused` - Workflow is paused (not yet implemented)

## Step States

- `pending` - Step waiting to execute
- `running` - Step is currently executing
- `completed` - Step completed successfully
- `failed` - Step failed after retries
- `skipped` - Step skipped due to dependency failure

## API Endpoints

- `POST /api/v1/agent/workflows` - Create workflow
- `POST /api/v1/agent/workflows/{workflow_id}/execute` - Execute workflow
- `GET /api/v1/agent/workflows/{workflow_id}/status` - Get workflow status
- `GET /api/v1/agent/workflows` - List workflows
- `GET /api/v1/agent/workflows/executions` - List executions
- `POST /api/v1/agent/workflows/executions/{execution_id}/cancel` - Cancel execution

## Persistence

Workflows and executions are stored in Redis with a 24-hour TTL. This provides:
- Fast access to workflow state
- Automatic cleanup of old data
- Persistence across service restarts

## Performance

- Workflow creation: <100ms
- Step execution: Depends on agent action
- Status queries: <50ms
- Redis persistence: <10ms

## Best Practices

1. **Set appropriate timeouts** - Balance between allowing enough time and detecting failures
2. **Use dependencies wisely** - Only create dependencies when steps truly require previous results
3. **Handle errors gracefully** - Design workflows to handle partial failures
4. **Monitor execution** - Use status queries to track workflow progress
5. **Clean up old workflows** - Redis TTL automatically cleans up, but monitor storage usage

## Troubleshooting

### Workflow Stuck in Running State

If a workflow remains in `running` state:
- Check if the agent-coordinator service is running
- Verify Redis is accessible
- Check agent status (agents may be offline)
- Review step-specific errors in the execution status

### Step Failures

If steps fail repeatedly:
- Verify the agent is registered and healthy
- Check agent capabilities match the action
- Review agent logs for specific errors
- Increase timeout if the action takes longer than expected
- Check network connectivity between coordinator and agents

### Redis Connection Issues

If workflows cannot be persisted:
- Verify Redis is running: `systemctl status redis`
- Check Redis configuration in agent-coordinator config
- Verify Redis URL: `redis://localhost:6379/1`
- Check Redis memory usage
