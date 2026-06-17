# aitbc.queue

Queue management and job scheduling for AITBC applications.

## Exports

- `Job`, `JobStatus`, `JobPriority` - Job types and enums
- `TaskQueue` - Task queue management
- `JobScheduler` - Job scheduling
- `BackgroundTaskManager` - Background task runner
- `WorkerPool` - Worker pool management
- `debounce`, `throttle` - Rate limiting decorators

## Usage

```python
from aitbc.queue import TaskQueue, JobScheduler
```
