#!/usr/bin/env python
"""
CLI tool for managing Pixeletica tasks.

This script provides commands to check task status, list tasks,
and manage stuck tasks from the command line.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add the parent directory to the path for imports
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.pixeletica.api.models import TaskStatus
from src.pixeletica.api.services import storage
from src.pixeletica.api.services.task_monitor import get_stuck_tasks, handle_stuck_tasks
from src.pixeletica.api.services.task_queue import update_task_status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pixeletica.cli_task")


def format_timestamp(timestamp_str: Optional[str]) -> str:
    """Format ISO timestamp string for display."""
    if not timestamp_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp_str


def print_task_info(task_id: str) -> bool:
    """
    Print detailed information about a task.

    Args:
        task_id: The task ID to display

    Returns:
        True if task was found, False otherwise
    """
    # Load task metadata
    metadata = storage.load_task_metadata(task_id, bypass_cache=True)

    if not metadata:
        print(f"Task {task_id} not found")
        return False

    # Print basic information
    print(f"Task ID: {task_id}")
    print(f"Status: {metadata.get('status', 'unknown')}")
    print(f"Progress: {metadata.get('progress', 'N/A')}%")
    print(f"Created: {format_timestamp(metadata.get('created'))}")
    print(f"Last Updated: {format_timestamp(metadata.get('updated'))}")

    if "error" in metadata and metadata["error"]:
        print(f"Error: {metadata['error']}")

    # Print file information
    try:
        files = storage.list_task_files(task_id)
        if files:
            print("\nFiles:")
            for file in files:
                size_kb = file.get("size", 0) / 1024
                print(
                    f"  {file.get('category', 'unknown')}/{file.get('filename', 'unknown')} ({size_kb:.1f} KB)"
                )
    except Exception as e:
        print(f"Error listing files: {e}")

    return True


def list_tasks(status_filter: Optional[str] = None, limit: int = 10) -> None:
    """
    List tasks, optionally filtered by status.

    Args:
        status_filter: Optional status to filter tasks by
        limit: Maximum number of tasks to show
    """
    try:
        tasks_dir = storage.TASKS_DIR
        if not tasks_dir.exists():
            print(f"Tasks directory not found at {tasks_dir}")
            return

        tasks = []
        for task_dir in tasks_dir.iterdir():
            if not task_dir.is_dir():
                continue

            task_id = task_dir.name
            metadata = storage.load_task_metadata(task_id)

            if not metadata:
                continue

            # Apply status filter if specified
            if status_filter and metadata.get("status") != status_filter:
                continue

            tasks.append((task_id, metadata))

        # Sort tasks by updated timestamp (newest first)
        tasks.sort(key=lambda x: x[1].get("updated", ""), reverse=True)

        # Limit the number of tasks shown
        tasks = tasks[:limit]

        if not tasks:
            print("No tasks found matching the criteria")
            return

        # Print task list
        print(f"{'Task ID':<36} {'Status':<10} {'Progress':>8} {'Last Updated':<20}")
        print("-" * 80)

        for task_id, metadata in tasks:
            status = metadata.get("status", "unknown")
            progress = (
                f"{metadata.get('progress', 0)}%"
                if metadata.get("progress") is not None
                else "N/A"
            )
            updated = format_timestamp(metadata.get("updated"))

            print(f"{task_id:<36} {status:<10} {progress:>8} {updated:<20}")

    except Exception as e:
        print(f"Error listing tasks: {e}")


def update_task(
    task_id: str,
    status: str,
    progress: Optional[int] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Update a task's status manually.

    Args:
        task_id: The task ID to update
        status: New status value
        progress: Optional progress value (0-100)
        error: Optional error message

    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate the status
        try:
            status_enum = TaskStatus(status)
        except ValueError:
            valid_statuses = [s.value for s in TaskStatus]
            print(
                f"Invalid status: {status}. Valid status values: {', '.join(valid_statuses)}"
            )
            return False

        # Update the task
        metadata = update_task_status(
            task_id, status_enum, progress=progress, error=error
        )

        if metadata:
            print(f"Task {task_id} updated successfully:")
            print(f"  Status: {metadata.get('status')}")
            print(f"  Progress: {metadata.get('progress', 'N/A')}%")
            if error:
                print(f"  Error: {metadata.get('error')}")
            return True
        else:
            print(f"Failed to update task {task_id}")
            return False

    except Exception as e:
        print(f"Error updating task: {e}")
        return False


def find_stuck_tasks(max_time: int = 3600) -> None:
    """
    Find tasks that have been stuck in processing state.

    Args:
        max_time: Maximum processing time in seconds
    """
    try:
        stuck_tasks = get_stuck_tasks(max_processing_time=max_time)

        if not stuck_tasks:
            print("No stuck tasks found")
            return

        print(f"Found {len(stuck_tasks)} stuck task(s):")
        for metadata in stuck_tasks:
            task_id = metadata.get("taskId", "unknown")
            updated = format_timestamp(metadata.get("updated"))
            print(f"  {task_id} (last updated: {updated})")

    except Exception as e:
        print(f"Error finding stuck tasks: {e}")


def reset_stuck_tasks(max_time: int = 3600) -> None:
    """
    Mark stuck tasks as failed.

    Args:
        max_time: Maximum processing time in seconds
    """
    try:
        count = handle_stuck_tasks(max_processing_time=max_time)

        if count > 0:
            print(f"Reset {count} stuck task(s)")
        else:
            print("No stuck tasks were found to reset")

    except Exception as e:
        print(f"Error resetting stuck tasks: {e}")


def main():
    """Main function to parse arguments and run commands."""
    parser = argparse.ArgumentParser(description="Pixeletica Task CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Info command
    info_parser = subparsers.add_parser("info", help="Show task information")
    info_parser.add_argument("task_id", help="Task ID to show")

    # List command
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument(
        "--status", choices=[s.value for s in TaskStatus], help="Filter by status"
    )
    list_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum number of tasks to show"
    )

    # Update command
    update_parser = subparsers.add_parser("update", help="Update task status")
    update_parser.add_argument("task_id", help="Task ID to update")
    update_parser.add_argument(
        "--status",
        choices=[s.value for s in TaskStatus],
        required=True,
        help="New status",
    )
    update_parser.add_argument(
        "--progress", type=int, help="Progress percentage (0-100)"
    )
    update_parser.add_argument("--error", help="Error message")

    # Find stuck tasks command
    stuck_parser = subparsers.add_parser("find-stuck", help="Find stuck tasks")
    stuck_parser.add_argument(
        "--max-time",
        type=int,
        default=3600,
        help="Maximum processing time in seconds (default: 3600)",
    )

    # Reset stuck tasks command
    reset_parser = subparsers.add_parser("reset-stuck", help="Reset stuck tasks")
    reset_parser.add_argument(
        "--max-time",
        type=int,
        default=3600,
        help="Maximum processing time in seconds (default: 3600)",
    )

    args = parser.parse_args()

    # Handle commands
    if args.command == "info":
        if not print_task_info(args.task_id):
            sys.exit(1)
    elif args.command == "list":
        list_tasks(status_filter=args.status, limit=args.limit)
    elif args.command == "update":
        if not update_task(args.task_id, args.status, args.progress, args.error):
            sys.exit(1)
    elif args.command == "find-stuck":
        find_stuck_tasks(max_time=args.max_time)
    elif args.command == "reset-stuck":
        reset_stuck_tasks(max_time=args.max_time)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
