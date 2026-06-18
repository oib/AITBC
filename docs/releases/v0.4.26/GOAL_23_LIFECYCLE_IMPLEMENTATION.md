# Goal 23: Add Lifecycle Management for Async Tasks - Implementation Summary

## Overview

Implemented comprehensive lifecycle management for async background tasks in the Coordinator API to ensure proper startup/shutdown hooks and graceful task termination.

## Problem

The coordinator-api had background async tasks (job processor, GPU worker) that:
- Lacked proper lifecycle management
- Did not check for application shutdown state
- Could hang indefinitely during shutdown
- Had no centralized task management
- Used naive `datetime.now()` instead of timezone-aware timestamps

## Solution

Created a lifecycle management system with:

### 1. New Lifecycle Module (`apps/coordinator-api/src/app/core/lifecycle.py`)

**Components:**

- **BackgroundTaskManager**: Manages lifecycle of background async tasks
  - `start_task()`: Start a background task with tracking
  - `stop_task()`: Stop a specific task with timeout
  - `stop_all()`: Stop all tasks gracefully
  - `get_task_status()`: Get status of all managed tasks

- **LifecycleState**: Tracks application lifecycle state
  - States: STARTING, RUNNING, SHUTTING_DOWN, STOPPED
  - `set_state()`: Set lifecycle state
  - `get_state()`: Get current state
  - `is_running()`: Check if application is running
  - `is_shutting_down()`: Check if application is shutting down

- **managed_lifespan()**: Context manager for proper async task cleanup

### 2. Updated Existing Lifespan

**File**: `apps/coordinator-api/src/app/core/lifespan.py`

- Integrated lifecycle state tracking
- Added background task cleanup on shutdown
- Proper state transitions (STARTING → RUNNING → SHUTTING_DOWN → STOPPED)

### 3. Updated Main Application Lifespan

**File**: `apps/coordinator-api/src/app/main.py`

- Integrated lifecycle state and task manager
- Added background task cleanup in shutdown sequence
- Proper state management throughout lifecycle

### 4. Updated Background Services

**JobProcessor** (`apps/coordinator-api/src/app/services/job_processor.py`):
- Added lifecycle state checking in main loop
- Uses `datetime.now(UTC)` for timezone-aware timestamps
- Checks `is_shutting_down()` to exit gracefully

**GPUWorker** (`apps/coordinator-api/src/app/services/gpu_worker.py`):
- Added lifecycle state checking in main loop
- Uses `datetime.now(UTC)` for timezone-aware timestamps
- Checks `is_shutting_down()` to exit gracefully

### 5. Updated Core Exports

**File**: `apps/coordinator-api/src/app/core/__init__.py`

- Exported `get_lifecycle_state()` and `get_task_manager()` for use across the application

## Key Features

### Graceful Shutdown

Background tasks now check `lifecycle_state.is_shutting_down()` in their main loops:

```python
while self._running and not self._lifecycle_state.is_shutting_down():
    # Process work
    await asyncio.sleep(self._poll_interval)
```

### Task Management

Centralized task manager with timeout-based shutdown:

```python
task_manager = get_task_manager()
await task_manager.start_task("job_processor", processor.start)
await task_manager.stop_all(timeout=5.0)
```

### State Tracking

Clear lifecycle state transitions with logging:

```
Lifecycle state transition: STOPPED -> STARTING
Lifecycle state transition: STARTING -> RUNNING
Lifecycle state transition: RUNNING -> SHUTTING_DOWN
Lifecycle state transition: SHUTTING_DOWN -> STOPPED
```

### Timezone-Aware Timestamps

Updated all datetime usage to use UTC:

```python
from datetime import UTC, datetime
timestamp = datetime.now(UTC)
```

## Benefits

1. **Graceful Shutdown**: Background tasks exit cleanly when application shuts down
2. **No Hanging Tasks**: Timeout-based task termination prevents hanging
3. **Centralized Management**: Single point of control for all background tasks
4. **State Visibility**: Clear lifecycle state for monitoring and debugging
5. **Timezone Safety**: UTC timestamps prevent DST-related issues
6. **Scalability**: Easy to add new background tasks with proper lifecycle

## Testing

The implementation can be tested by:

1. Starting the coordinator-api
2. Verifying lifecycle state transitions in logs
3. Triggering shutdown (SIGTERM)
4. Verifying background tasks stop gracefully
5. Checking for no hanging processes

## Future Enhancements

Potential improvements for future work:

1. Add health check endpoint for lifecycle state
2. Add metrics for task lifecycle events
3. Add task-specific timeout configurations
4. Add task dependency management (start order)
5. Add task restart policies
6. Add task resource limits (CPU, memory)

## Files Modified

- ✅ `apps/coordinator-api/src/app/core/lifecycle.py` (new)
- ✅ `apps/coordinator-api/src/app/core/lifespan.py` (updated)
- ✅ `apps/coordinator-api/src/app/main.py` (updated)
- ✅ `apps/coordinator-api/src/app/services/job_processor.py` (updated)
- ✅ `apps/coordinator-api/src/app/services/gpu_worker.py` (updated)
- ✅ `apps/coordinator-api/src/app/core/__init__.py` (updated)

## Integration Notes

The lifecycle management system is now integrated into the coordinator-api and ready for use. Background services should:

1. Import lifecycle state: `from ..core.lifecycle import get_lifecycle_state`
2. Check shutdown state in loops: `while running and not lifecycle_state.is_shutting_down()`
3. Use task manager for managed tasks: `get_task_manager().start_task(...)`

## Success Criteria

- ✅ Lifecycle state tracking implemented
- ✅ Background task manager created
- ✅ Graceful shutdown hooks added
- ✅ Timezone-aware timestamps in background services
- ✅ Integration with existing lifespan
- ✅ No breaking changes to existing functionality
