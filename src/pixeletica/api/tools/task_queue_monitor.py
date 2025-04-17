#!/usr/bin/env python
"""
Pixeletica Task Queue Monitor

A utility script to monitor and debug the Celery task queue.
Provides insights into queue health, task status, and Redis connectivity.
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("task_queue_monitor")


class TaskQueueMonitor:
    """Monitor Celery task queues and task statuses."""

    def __init__(self, redis_url: str = None, tasks_dir: str = None):
        """
        Initialize the task queue monitor.

        Args:
            redis_url: Redis URL to connect to
            tasks_dir: Directory containing task data
        """
        self.redis_url = redis_url or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self.tasks_dir = Path(tasks_dir or "/app/tasks")
        self.redis_client = None
        self.celery_app = None

    def connect_to_redis(self) -> bool:
        """Connect to Redis."""
        try:
            import redis

            self.redis_client = redis.Redis.from_url(self.redis_url)
            ping_result = self.redis_client.ping()
            logger.info(f"Connected to Redis: {self.redis_url}, ping={ping_result}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    def get_celery_app(self):
        """Get or create Celery app."""
        if self.celery_app is None:
            from celery import Celery

            self.celery_app = Celery(broker=self.redis_url, backend=self.redis_url)
        return self.celery_app

    def check_redis_health(self) -> Dict:
        """Check Redis health and queue stats."""
        if not self.redis_client:
            if not self.connect_to_redis():
                return {"status": "error", "message": "Failed to connect to Redis"}

        try:
            info = self.redis_client.info()
            keys = self.redis_client.keys("*")
            celery_keys = [k.decode() for k in keys if b"celery" in k]

            # Get queue length
            queue_stats = {}
            queue_keys = [k for k in celery_keys if "celery" == k]
            for queue in queue_keys:
                queue_stats[queue] = self.redis_client.llen(queue)

            # Get registered task count
            task_keys = [k for k in celery_keys if "celery-task-meta" in k]

            return {
                "status": "healthy" if info.get("redis_version") else "unhealthy",
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", "unknown"),
                "total_keys": len(keys),
                "celery_keys": len(celery_keys),
                "queue_stats": queue_stats,
                "task_keys": len(task_keys),
            }
        except Exception as e:
            logger.error(f"Failed to check Redis health: {e}")
            return {"status": "error", "message": str(e)}

    def get_queue_tasks(self, queue_name: str = "celery") -> List:
        """Get tasks in a specific queue."""
        if not self.redis_client:
            if not self.connect_to_redis():
                return []

        try:
            queue_length = self.redis_client.llen(queue_name)
            if queue_length == 0:
                return []

            # Peek at the queue (without removing items)
            # This is complex in Redis as LRANGE doesn't guarantee full data for complex objects
            tasks = []
            for i in range(min(queue_length, 10)):  # Get up to 10 tasks
                task_data = self.redis_client.lindex(queue_name, i)
                if task_data:
                    tasks.append(task_data.decode())

            return tasks
        except Exception as e:
            logger.error(f"Failed to get queue tasks: {e}")
            return []

    def get_task_metadata(self, task_id: str) -> Optional[Dict]:
        """Get task metadata from file storage."""
        task_dir = self.tasks_dir / task_id
        metadata_file = task_dir / "task.json"  # Use root, not metadata/
        if not metadata_file.exists():
            return None
        try:
            with open(metadata_file, "r") as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"Failed to load task metadata: {e}")
            return None

    def find_stuck_tasks(self, hours: int = 1) -> List[Dict]:
        """Find tasks that appear to be stuck."""
        stuck_tasks = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Check task directories
        if not self.tasks_dir.exists():
            logger.warning(f"Tasks directory not found: {self.tasks_dir}")
            return []

        for task_dir in self.tasks_dir.iterdir():
            if not task_dir.is_dir():
                continue

            task_id = task_dir.name
            metadata = self.get_task_metadata(task_id)

            if not metadata:
                continue

            status = metadata.get("status")
            # Check for stuck tasks (queued or processing but not progressing)
            if status in ["queued", "processing"]:
                try:
                    updated_time = datetime.fromisoformat(metadata.get("updated", ""))
                    if updated_time < cutoff_time:
                        metadata["task_dir"] = str(task_dir)
                        stuck_tasks.append(metadata)
                except (ValueError, TypeError):
                    # If we can't parse the date, skip this task
                    pass

        return stuck_tasks

    def get_task_status_from_redis(self, task_id: str) -> Optional[Dict]:
        """Get task status from Redis."""
        if not self.redis_client:
            if not self.connect_to_redis():
                return None

        try:
            # Try to find the task in Redis
            task_key_patterns = [
                f"celery-task-meta-{task_id}",
                f"_celery_task_meta-{task_id}",
                f"celery-task-{task_id}",
            ]

            for key_pattern in task_key_patterns:
                keys = self.redis_client.keys(key_pattern)
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        try:
                            return json.loads(data)
                        except json.JSONDecodeError:
                            return {"raw_data": data.decode()}

            return None
        except Exception as e:
            logger.error(f"Failed to get task status from Redis: {e}")
            return None

    def get_worker_status(self) -> Dict:
        """Get status of Celery workers."""
        celery = self.get_celery_app()

        try:
            inspection = celery.control.inspect()
            ping = inspection.ping() or {}
            stats = inspection.stats() or {}
            active = inspection.active() or {}
            scheduled = inspection.scheduled() or {}
            reserved = inspection.reserved() or {}

            workers = {}
            # Combine data for each worker
            for worker in set(list(ping.keys()) + list(stats.keys())):
                workers[worker] = {
                    "online": worker in ping,
                    "stats": stats.get(worker, {}),
                    "active_tasks": len(active.get(worker, [])),
                    "scheduled_tasks": len(scheduled.get(worker, [])),
                    "reserved_tasks": len(reserved.get(worker, [])),
                }

            return {
                "total_workers": len(workers),
                "online_workers": sum(1 for w in workers.values() if w["online"]),
                "workers": workers,
            }
        except Exception as e:
            logger.error(f"Failed to get worker status: {e}")
            return {"error": str(e)}

    def repair_task_issue(self, task_id: str, action: str) -> Dict:
        """
        Attempt to repair issues with a specific task.

        Actions:
            - reset_status: Reset the task status to "queued"
            - reset_processing: Reset a task in "processing" state back to "queued"
            - clear_redis: Clear Redis entries for this task
            - requeue: Try to requeue the task
            - force_complete: Force the task status to "completed"
            - delete: Delete the task
        """
        if not self.redis_client:
            if not self.connect_to_redis():
                return {"status": "error", "message": "Failed to connect to Redis"}

        metadata = self.get_task_metadata(task_id)
        if not metadata:
            return {"status": "error", "message": "Task not found"}

        try:
            if action == "reset_status":
                # Reset the task status to "queued"
                metadata["status"] = "queued"
                metadata["progress"] = 0
                metadata["updated"] = datetime.now().isoformat()
                if "error" in metadata:
                    del metadata["error"]

                # Save updated metadata
                self._save_task_metadata(task_id, metadata)
                return {"status": "success", "message": "Task status reset to queued"}

            elif action == "reset_processing":
                # Only reset if it's in processing state
                if metadata.get("status") == "processing":
                    metadata["status"] = "queued"
                    metadata["progress"] = 0
                    metadata["updated"] = datetime.now().isoformat()
                    self._save_task_metadata(task_id, metadata)
                    return {
                        "status": "success",
                        "message": "Processing task reset to queued",
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Task is not in processing state",
                    }

            elif action == "clear_redis":
                # Clear Redis entries related to this task
                keys = self.redis_client.keys(f"*{task_id}*")
                if keys:
                    self.redis_client.delete(*keys)
                    return {
                        "status": "success",
                        "message": f"Cleared {len(keys)} Redis keys",
                    }
                else:
                    return {
                        "status": "info",
                        "message": "No keys found in Redis for this task",
                    }

            elif action == "requeue":
                # Try to requeue the task by importing task_queue and recreating
                from src.pixeletica.api.services.task_queue import process_image_task

                # Get the input image path
                input_image_path = metadata.get("inputImagePath")
                if not input_image_path:
                    return {"status": "error", "message": "Input image path not found"}

                # Reset status to queued
                metadata["status"] = "queued"
                metadata["progress"] = 0
                metadata["updated"] = datetime.now().isoformat()
                self._save_task_metadata(task_id, metadata)

                # Apply the task (this would normally be done via task_queue.create_task)
                result = process_image_task.apply_async(
                    args=[task_id],
                    task_id=str(task_id),
                    queue="celery",
                )

                return {
                    "status": "success",
                    "message": f"Task requeued with ID {result.id}, state: {result.state}",
                }

            elif action == "force_complete":
                # Force the task status to completed
                metadata["status"] = "completed"
                metadata["progress"] = 100
                metadata["updated"] = datetime.now().isoformat()
                metadata["completedAt"] = datetime.now().isoformat()
                self._save_task_metadata(task_id, metadata)
                return {"status": "success", "message": "Task marked as completed"}

            elif action == "delete":
                # Delete the task directory
                import shutil

                task_dir = self.tasks_dir / task_id
                if task_dir.exists():
                    shutil.rmtree(task_dir)
                    return {"status": "success", "message": "Task deleted"}
                else:
                    return {"status": "error", "message": "Task directory not found"}

            else:
                return {"status": "error", "message": f"Unknown action: {action}"}

        except Exception as e:
            logger.error(f"Failed to repair task {task_id}: {e}")
            return {"status": "error", "message": str(e)}

    def _save_task_metadata(self, task_id: str, metadata: Dict) -> bool:
        """Save task metadata to file."""
        task_dir = self.tasks_dir / task_id
        metadata_file = task_dir / "task.json"  # Use root, not metadata/
        try:
            if not task_dir.exists():
                task_dir.mkdir(parents=True, exist_ok=True)
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save task metadata: {e}")
            return False

    def run_monitor(self, interval: int = 5, max_runs: int = 0) -> None:
        """
        Run the monitor continuously, checking queue health at regular intervals.

        Args:
            interval: Time between checks in seconds
            max_runs: Maximum number of monitor runs (0 for infinite)
        """
        runs = 0
        try:
            while max_runs == 0 or runs < max_runs:
                runs += 1
                logger.info(f"=== Task Queue Monitor Run #{runs} ===")

                # Check Redis health
                redis_health = self.check_redis_health()
                logger.info(f"Redis Status: {redis_health['status']}")
                logger.info(f"Queue Stats: {redis_health.get('queue_stats', {})}")

                # Check for stuck tasks
                stuck_tasks = self.find_stuck_tasks(hours=1)
                if stuck_tasks:
                    logger.warning(f"Found {len(stuck_tasks)} potentially stuck tasks")
                    for task in stuck_tasks:
                        status = task.get("status")
                        task_id = task.get("taskId")
                        updated = task.get("updated")
                        logger.warning(
                            f"  Task {task_id}: {status}, last updated: {updated}"
                        )

                # Check worker status
                worker_status = self.get_worker_status()
                logger.info(
                    f"Workers: {worker_status.get('online_workers', 0)}/{worker_status.get('total_workers', 0)} online"
                )

                if max_runs == 0 or runs < max_runs:
                    logger.info(f"Sleeping for {interval} seconds...")
                    time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")


def main():
    """Command-line interface for the task queue monitor."""
    parser = argparse.ArgumentParser(description="Pixeletica Task Queue Monitor")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Health check command
    health_parser = subparsers.add_parser("health", help="Check Redis and queue health")
    health_parser.add_argument("--redis-url", help="Redis URL")
    health_parser.add_argument("--tasks-dir", help="Path to tasks directory")

    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Run continuous monitoring")
    monitor_parser.add_argument(
        "--interval", type=int, default=5, help="Check interval in seconds"
    )
    monitor_parser.add_argument(
        "--runs", type=int, default=0, help="Maximum number of runs (0 for infinite)"
    )
    monitor_parser.add_argument("--redis-url", help="Redis URL")
    monitor_parser.add_argument("--tasks-dir", help="Path to tasks directory")

    # Find stuck tasks command
    stuck_parser = subparsers.add_parser("find-stuck", help="Find stuck tasks")
    stuck_parser.add_argument(
        "--hours",
        type=int,
        default=1,
        help="Tasks not updated in this many hours are considered stuck",
    )
    stuck_parser.add_argument("--redis-url", help="Redis URL")
    stuck_parser.add_argument("--tasks-dir", help="Path to tasks directory")

    # Inspect task command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a specific task")
    inspect_parser.add_argument("task_id", help="Task ID to inspect")
    inspect_parser.add_argument("--redis-url", help="Redis URL")
    inspect_parser.add_argument("--tasks-dir", help="Path to tasks directory")

    # Repair task command
    repair_parser = subparsers.add_parser("repair", help="Repair issues with a task")
    repair_parser.add_argument("task_id", help="Task ID to repair")
    repair_parser.add_argument(
        "--action",
        choices=[
            "reset_status",
            "reset_processing",
            "clear_redis",
            "requeue",
            "force_complete",
            "delete",
        ],
        required=True,
        help="Repair action to take",
    )
    repair_parser.add_argument("--redis-url", help="Redis URL")
    repair_parser.add_argument("--tasks-dir", help="Path to tasks directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Create monitor with Redis URL from args or environment
    redis_url = (
        args.redis_url if hasattr(args, "redis_url") and args.redis_url else None
    )
    tasks_dir = (
        args.tasks_dir if hasattr(args, "tasks_dir") and args.tasks_dir else None
    )
    monitor = TaskQueueMonitor(redis_url=redis_url, tasks_dir=tasks_dir)

    # Run the appropriate command
    if args.command == "health":
        health = monitor.check_redis_health()
        print(json.dumps(health, indent=2))

    elif args.command == "monitor":
        monitor.run_monitor(interval=args.interval, max_runs=args.runs)

    elif args.command == "find-stuck":
        stuck_tasks = monitor.find_stuck_tasks(hours=args.hours)
        if stuck_tasks:
            print(f"Found {len(stuck_tasks)} stuck tasks:")
            for task in stuck_tasks:
                print(
                    f"Task {task.get('taskId')}: {task.get('status')}, last updated: {task.get('updated')}"
                )
        else:
            print("No stuck tasks found")

    elif args.command == "inspect":
        # Get task metadata from file
        metadata = monitor.get_task_metadata(args.task_id)
        if metadata:
            print("=== Task Metadata ===")
            print(json.dumps(metadata, indent=2))
        else:
            print(f"Task {args.task_id} not found in file storage")

        # Get task status from Redis
        redis_status = monitor.get_task_status_from_redis(args.task_id)
        if redis_status:
            print("\n=== Task Status in Redis ===")
            print(json.dumps(redis_status, indent=2))
        else:
            print(f"Task {args.task_id} not found in Redis")

    elif args.command == "repair":
        result = monitor.repair_task_issue(args.task_id, args.action)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
