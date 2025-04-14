# Task Monitoring & Troubleshooting

This document explains how Pixeletica handles task processing, monitors for stuck tasks, and provides troubleshooting tools.

## Problem Background

Tasks were sometimes getting stuck in the "in progress" state and never transitioning to "completed". This issue has been resolved by improving the task processing system with better error handling, status verification, and monitoring capabilities.

## Improvements Made

The following improvements have been implemented to address the task completion issue:

1. **Robust Error Handling**: Added comprehensive error handling in the task processing function, ensuring that even if an error occurs, the task will be properly marked as failed.

2. **Status Verification**: After updating task status, the system now verifies that the update was successful and attempts multiple approaches if needed.

3. **Task Monitoring Service**: Added a dedicated task monitor service that automatically detects and handles tasks that have been stuck in the "processing" state for too long.

4. **Task CLI Tool**: Added a command-line tool for inspecting and managing tasks, making it easier to debug issues.

5. **Atomic Writes**: Implemented atomic writes for task metadata to prevent corruption during updates.

6. **Retry Mechanism**: Added retries for task processing operations.

## Task Processing Flow

1. **Creation**: A task is created with status "queued" when a user submits a conversion request
2. **Processing**: The worker picks up the task and sets status to "processing"
3. **Completion/Failure**: When done, the worker sets status to "completed" or "failed"

## Task Monitor Service

The task monitor service runs alongside the API and worker services. It periodically scans for tasks that have been stuck in the "processing" state for longer than a configured time limit (default: 1 hour).

When a stuck task is detected, the monitor automatically marks it as failed with an appropriate error message, allowing the API to report this status to the client.

## Using the CLI Task Tool

The `cli_task.py` script provides several commands for inspecting and managing tasks:

### List Tasks

To list recent tasks:

```bash
# Windows
python src\pixeletica\cli_task.py list

# Linux/macOS
python src/pixeletica/cli_task.py list
```

Filter by status:

```bash
python src/pixeletica/cli_task.py list --status processing
```

### View Task Details

To view detailed information about a specific task:

```bash
python src/pixeletica/cli_task.py info <task_id>
```

### Find Stuck Tasks

To find tasks that have been stuck in "processing" state:

```bash
python src/pixeletica/cli_task.py find-stuck
```

You can specify a different maximum processing time (in seconds):

```bash
python src/pixeletica/cli_task.py find-stuck --max-time 1800  # 30 minutes
```

### Reset Stuck Tasks

To mark stuck tasks as failed:

```bash
python src/pixeletica/cli_task.py reset-stuck
```

### Update Task Status

To manually update a task's status:

```bash
python src/pixeletica/cli_task.py update <task_id> --status completed
```

## Docker Configuration

The system uses three main Docker containers:

1. **API**: Handles HTTP requests and manages the web interface
2. **Worker**: Processes image conversion tasks in the background
3. **Monitor**: Detects and handles stuck tasks

Configuration options for the task monitor:

```
TASK_MONITOR_INTERVAL: Time between checks (in seconds, default: 900)
TASK_MAX_PROCESSING_TIME: Maximum allowed processing time (in seconds, default: 3600)
```

## Troubleshooting Common Issues

### Task Stuck in Processing

1. Check if the task is genuinely stuck using the CLI tool:
   ```
   python src/pixeletica/cli_task.py info <task_id>
   ```

2. Check the worker logs for errors:
   ```
   docker logs pixeletica_worker_1
   ```

3. Reset stuck tasks if needed:
   ```
   python src/pixeletica/cli_task.py reset-stuck
   ```

### Workers Not Processing Tasks

1. Verify Redis connection:
   ```
   docker exec pixeletica_redis_1 redis-cli ping
   ```

2. Check Celery worker status:
   ```
   docker exec pixeletica_worker_1 celery -A pixeletica.api.services.task_queue.celery_app inspect active
   ```

3. Restart the worker container if needed:
   ```
   docker-compose restart worker
   ```

## Future Improvements

Potential future improvements to the task processing system:

1. **Web-based Task Management**: Add a UI for viewing and managing tasks in the admin interface
2. **Task Retention Policies**: Configure how long completed/failed tasks are kept
3. **Advanced Task Analytics**: Track processing times, failure rates, etc.
4. **Task Priorities**: Allow certain tasks to have higher priority
