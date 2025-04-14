"""
Task monitoring service to check for and handle stuck tasks.

This module contains utilities to find and handle tasks that might be
stuck in processing state for too long.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.pixeletica.api.models import TaskStatus
from src.pixeletica.api.services import storage
from src.pixeletica.api.services.task_queue import update_task_status

# Set up logging
logger = logging.getLogger("pixeletica.api.task_monitor")

# Default configuration
DEFAULT_MAX_PROCESSING_TIME = 60 * 60  # 1 hour
DEFAULT_CHECK_INTERVAL = 15 * 60  # 15 minutes


def iso_to_datetime(date_str: str) -> Optional[datetime]:
    """Convert ISO 8601 string to datetime object."""
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def get_stuck_tasks(
    max_processing_time: int = DEFAULT_MAX_PROCESSING_TIME,
) -> List[Dict]:
    """
    Find tasks that have been in 'processing' state for too long.

    Args:
        max_processing_time: Maximum allowed processing time in seconds

    Returns:
        List of task metadata for stuck tasks
    """
    stuck_tasks = []
    now = datetime.now()
    max_age = timedelta(seconds=max_processing_time)

    # Scan all task directories
    for task_dir in storage.TASKS_DIR.iterdir():
        if not task_dir.is_dir():
            continue

        try:
            # Load task metadata
            task_id = task_dir.name
            metadata = storage.load_task_metadata(task_id, bypass_cache=True)

            if not metadata:
                continue

            # Check if task is in processing state
            if metadata.get("status") == TaskStatus.PROCESSING.value:
                # Check how long it's been processing
                updated_str = metadata.get("updated")
                if not updated_str:
                    continue

                updated = iso_to_datetime(updated_str)
                if not updated:
                    continue

                age = now - updated

                # If it's been processing for too long, mark it as stuck
                if age > max_age:
                    logger.warning(
                        f"Found stuck task {task_id}: processing for {age.total_seconds()} seconds"
                    )
                    stuck_tasks.append(metadata)
        except Exception as e:
            logger.error(f"Error checking task {task_dir.name}: {e}")

    return stuck_tasks


def handle_stuck_tasks(max_processing_time: int = DEFAULT_MAX_PROCESSING_TIME) -> int:
    """
    Find and handle tasks that have been stuck in 'processing' state.

    Args:
        max_processing_time: Maximum allowed processing time in seconds

    Returns:
        Number of stuck tasks that were handled
    """
    stuck_tasks = get_stuck_tasks(max_processing_time)
    handled_count = 0

    for metadata in stuck_tasks:
        task_id = metadata.get("taskId")
        if not task_id:
            continue

        try:
            # Mark the task as failed
            update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=f"Task timed out after {max_processing_time} seconds",
            )

            # Double-check that the status was updated correctly
            updated_metadata = storage.load_task_metadata(task_id, bypass_cache=True)
            if (
                updated_metadata
                and updated_metadata.get("status") == TaskStatus.FAILED.value
            ):
                logger.info(f"Successfully marked stuck task {task_id} as failed")
                handled_count += 1
            else:
                logger.error(f"Failed to update status for stuck task {task_id}")

                # Force update as a last resort
                if updated_metadata:
                    updated_metadata["status"] = TaskStatus.FAILED.value
                    updated_metadata["error"] = (
                        f"Task timed out after {max_processing_time} seconds"
                    )
                    updated_metadata["updated"] = datetime.now().isoformat()
                    storage.save_task_metadata(task_id, updated_metadata, force=True)
                    handled_count += 1
        except Exception as e:
            logger.error(f"Error handling stuck task {task_id}: {e}")

    return handled_count


def monitor_tasks(
    check_interval: int = DEFAULT_CHECK_INTERVAL,
    max_processing_time: int = DEFAULT_MAX_PROCESSING_TIME,
):
    """
    Continuously monitor tasks and handle any that are stuck.

    Args:
        check_interval: Time between checks in seconds
        max_processing_time: Maximum allowed processing time in seconds
    """
    logger.info(
        f"Starting task monitor (check_interval={check_interval}s, "
        f"max_processing_time={max_processing_time}s)"
    )

    while True:
        try:
            handled_count = handle_stuck_tasks(max_processing_time)
            if handled_count > 0:
                logger.info(f"Handled {handled_count} stuck task(s)")
        except Exception as e:
            logger.error(f"Error in task monitoring: {e}")

        # Sleep until next check
        time.sleep(check_interval)


def run_monitor():
    """Run the task monitor with configuration from environment."""
    check_interval = int(
        os.environ.get("TASK_MONITOR_INTERVAL", DEFAULT_CHECK_INTERVAL)
    )
    max_processing_time = int(
        os.environ.get("TASK_MAX_PROCESSING_TIME", DEFAULT_MAX_PROCESSING_TIME)
    )

    monitor_tasks(check_interval, max_processing_time)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    run_monitor()
