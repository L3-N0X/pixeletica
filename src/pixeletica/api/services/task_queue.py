"""
Task queue service for handling background processing of image conversion tasks.

This module provides a robust implementation of Celery-based task queuing with reliable
state management between Redis and filesystem storage.
"""

import logging
import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from celery import Celery, states
from celery.result import AsyncResult

from src.pixeletica.api.models import TaskStatus

# Imports are already correct from the reverted state, no change needed here.
# Keeping this block for structure, but the content is identical.
from src.pixeletica.api.services import storage
from src.pixeletica.dithering import (
    get_algorithm_by_name,
)  # Keep for algorithm_id lookup
from src.pixeletica.export.export_manager import export_processed_image
from src.pixeletica.image_ops import load_image, resize_image
from src.pixeletica.processing.converter import (
    process_image_to_blocks,
)  # Import the new function
from src.pixeletica.schematic_generator import generate_schematic

# Set up logging immediately to capture all initialization
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pixeletica.api.task_queue")

# Configure Celery with more explicit settings
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
logger.info(f"Initializing Celery with broker URL: {redis_url}")

celery_app = Celery("pixeletica")
celery_app.conf.update(
    broker_url=redis_url,
    result_backend=redis_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    worker_prefetch_multiplier=1,  # Process one task at a time
    broker_connection_retry_on_startup=True,  # Retry connecting to broker on startup
    broker_connection_max_retries=10,  # Max retries for broker connection
    task_publish_retry=True,  # Retry publishing tasks
    task_publish_retry_policy={
        "max_retries": 5,
        "interval_start": 0.2,
        "interval_step": 0.5,
        "interval_max": 5,
    },
)

# Configure task routes - ensure consistent routing
celery_app.conf.task_routes = {
    "pixeletica.api.services.task_queue.*": {"queue": "celery"}
}


# Synchronize task states - critical for consistent operation
def sync_task_state(task_id: str, celery_id: Optional[str] = None) -> Dict:
    """
    Synchronize task state between Redis and file storage.

    Args:
        task_id: The task ID in the filesystem
        celery_id: The Celery task ID (if different)

    Returns:
        Updated task metadata
    """
    # Load task metadata from filesystem
    metadata = storage.load_task_metadata(task_id, bypass_cache=True)
    if not metadata:
        logger.error(f"Task {task_id} not found in storage during sync")
        return {}

    # If we have a Celery ID, store it and check Redis
    if celery_id:
        metadata["celery_id"] = celery_id

        # Check if this task exists in Celery/Redis
        try:
            result = AsyncResult(celery_id, app=celery_app)
            if result.state:
                redis_state = result.state
                redis_result = result.result
                redis_traceback = result.traceback

                logger.info(
                    f"Redis task state for {task_id} (celery_id={celery_id}): {redis_state}"
                )

                # Map Celery states to our task states
                if redis_state == states.SUCCESS:
                    metadata["status"] = TaskStatus.COMPLETED.value
                    metadata["progress"] = 100
                    # Use completion time from Redis if available and valid
                    completion_time_redis = result.date_done
                    if completion_time_redis and isinstance(
                        completion_time_redis, datetime
                    ):
                        metadata["completedAt"] = completion_time_redis.isoformat()
                    elif "completedAt" not in metadata:  # Set only if not already set
                        metadata["completedAt"] = datetime.now().isoformat()

                elif redis_state == states.FAILURE:
                    metadata["status"] = TaskStatus.FAILED.value
                    metadata["error"] = (
                        str(redis_result) if redis_result else "Unknown error"
                    )
                    metadata["traceback"] = redis_traceback
                elif redis_state == states.STARTED:
                    # Only update to PROCESSING if not already finished
                    if metadata["status"] not in [
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                    ]:
                        metadata["status"] = TaskStatus.PROCESSING.value
                elif redis_state == states.PENDING:
                    # Only update to QUEUED if not already started or finished
                    if metadata["status"] not in [
                        TaskStatus.PROCESSING.value,
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                    ]:
                        metadata["status"] = TaskStatus.QUEUED.value

                # Always update the timestamp
                metadata["updated"] = datetime.now().isoformat()

                # Store the Redis state for debugging
                metadata["redis_state"] = redis_state
        except Exception as e:
            logger.error(f"Error checking Redis for task {task_id}: {e}")

    # Save metadata back to storage
    storage.save_task_metadata(task_id, metadata, force=True)

    # Verify we can read it back
    verification = storage.load_task_metadata(task_id, bypass_cache=True)
    if verification and verification.get("status") == metadata.get("status"):
        logger.info(
            f"Successfully synchronized task {task_id} state to: {metadata.get('status')}"
        )
    else:
        logger.error(f"Failed to verify task {task_id} state after sync!")

    return metadata


def create_task(request_data: Dict) -> str:
    """
    Create a new conversion task.

    Args:
        request_data: Dictionary containing task configuration data

    Returns:
        Task ID as a string
    """
    # Generate a unique task ID that will be used consistently
    task_id = str(uuid.uuid4())
    logger.info(f"Creating new task with ID: {task_id}")

    # Initialize task metadata
    task_metadata = {
        "taskId": task_id,
        "status": TaskStatus.QUEUED.value,
        "progress": 0,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "config": {
            "filename": request_data.get("filename", "image.png"),
            "width": request_data.get("width"),
            "height": request_data.get("height"),
            "algorithm": request_data.get("algorithm", "floyd_steinberg"),
            "color_palette": request_data.get("color_palette", "minecraft"),
            "export_types": request_data.get("export_types", []),
            "exportSettings": request_data.get("exportSettings", {}),
            "schematicSettings": request_data.get("schematicSettings", {}),
            "version_options": request_data.get("version_options", {}),
        },
    }

    # Save the image if provided
    image_data = request_data.get("image", "")
    if image_data:
        try:
            image_path = storage.save_base64_image(
                task_id, image_data, request_data.get("filename", "image.png")
            )
            task_metadata["inputImagePath"] = str(image_path)
            logger.info(f"Saved input image for task {task_id} to {image_path}")
        except Exception as e:
            logger.error(f"Failed to save input image for task {task_id}: {e}")
            task_metadata["status"] = TaskStatus.FAILED.value
            task_metadata["error"] = f"Failed to save input image: {str(e)}"

    # Save initial task metadata
    storage.save_task_metadata(task_id, task_metadata, force=True)

    # Start processing task if image was saved successfully
    if task_metadata["status"] != TaskStatus.FAILED.value:
        # Test Redis connection before proceeding
        try:
            import redis

            r = redis.Redis.from_url(redis_url)
            r.ping()
            redis_ok = True
            logger.info("Redis connection verified for task creation")
        except Exception as e:
            redis_ok = False
            logger.error(f"Redis connection failed! Task queuing may fail: {e}")

        # Attempt to queue the task in Celery
        try:
            # Use synchronously generated Celery task ID
            celery_task_id = str(uuid.uuid4())

            # Manually create unique task ID first to avoid Celery auto-generation
            result = process_image_task.apply_async(
                args=[task_id],
                task_id=celery_task_id,
                queue="celery",
                retry=True,
                retry_policy={
                    "max_retries": 3,
                    "interval_start": 0,
                    "interval_step": 5,
                    "interval_max": 30,
                },
            )

            # Update metadata with Celery task ID
            task_metadata["celery_id"] = celery_task_id
            task_metadata["celery_task_id"] = result.id  # Should match celery_task_id
            storage.save_task_metadata(task_id, task_metadata, force=True)

            logger.info(
                f"Task {task_id} queued with celery_id={celery_task_id}, state={result.state}"
            )

            # Manually add task to Redis if not already there (as extra safeguard)
            if redis_ok:
                try:
                    r = redis.Redis.from_url(redis_url)
                    task_key = f"celery-task-meta-{celery_task_id}"
                    if not r.exists(task_key):
                        task_data = {
                            "status": "PENDING",
                            "result": None,
                            "children": [],
                            "date_done": None,
                        }
                        r.set(task_key, json.dumps(task_data))
                        logger.info(f"Manually added task {celery_task_id} to Redis")
                except Exception as e:
                    logger.error(f"Failed to add task manually to Redis: {e}")

        except Exception as e:
            logger.error(f"Failed to queue task {task_id}: {e}")
            # Update task status to failed
            task_metadata["status"] = TaskStatus.FAILED.value
            task_metadata["error"] = f"Failed to queue task: {str(e)}"
            storage.save_task_metadata(task_id, task_metadata)

    return task_id


def get_task_status(task_id: str, bypass_cache: bool = False) -> Optional[Dict]:
    """
    Get the current status of a task.

    Args:
        task_id: Task identifier
        bypass_cache: If True, bypass the metadata cache and load directly from disk

    Returns:
        Dictionary with task status information or None if task not found
    """
    # Always use bypass_cache=True for status checks to get latest data
    metadata = storage.load_task_metadata(task_id, bypass_cache=True)

    if not metadata:
        logger.warning(f"Task metadata not found for {task_id}")
        return None

    # If we have a celery_id, sync with Redis to ensure latest status
    celery_id = metadata.get("celery_id") or metadata.get("celery_task_id")
    if celery_id:
        metadata = sync_task_state(task_id, celery_id)

    # Check for stuck tasks (only if not already completed or failed)
    current_status = metadata.get("status")
    if current_status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
        now = datetime.now()
        try:
            if current_status == TaskStatus.QUEUED.value:
                created_time = datetime.fromisoformat(metadata.get("created", ""))
                queue_time = (now - created_time).total_seconds()
                if queue_time > 300:  # 5 minutes
                    logger.warning(
                        f"Task {task_id} timed out in queue ({queue_time:.1f}s)"
                    )
                    metadata["status"] = TaskStatus.FAILED.value
                    metadata["error"] = "Task timed out in queue"
                    metadata["updated"] = now.isoformat()
                    storage.save_task_metadata(task_id, metadata, force=True)

            elif current_status == TaskStatus.PROCESSING.value:
                updated_time = datetime.fromisoformat(metadata.get("updated", ""))
                processing_time = (now - updated_time).total_seconds()
                if processing_time > 600:  # 10 minutes without update
                    logger.warning(
                        f"Task {task_id} timed out during processing ({processing_time:.1f}s)"
                    )
                    metadata["status"] = TaskStatus.FAILED.value
                    metadata["error"] = "Task processing timed out"
                    metadata["updated"] = now.isoformat()
                    storage.save_task_metadata(task_id, metadata, force=True)
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking task timeout for {task_id}: {e}")

    return metadata


def update_task_status(
    task_id: str,
    status: Union[str, TaskStatus],
    progress: Optional[int] = None,
    error: Optional[str] = None,
    traceback: Optional[str] = None,  # Added traceback
    current_step: Optional[str] = None,  # Added current_step
) -> Dict:
    """
    Update the status of a task, saving to storage and potentially Redis.

    Args:
        task_id: Task identifier
        status: New task status (TaskStatus enum or string)
        progress: Optional progress percentage (0-100)
        error: Optional error message if task failed
        traceback: Optional traceback string if task failed
        current_step: Optional name of the current processing step

    Returns:
        Updated task metadata dictionary
    """
    status_value = status.value if isinstance(status, TaskStatus) else status
    logger.info(
        f"Updating task {task_id} status to {status_value} (Progress: {progress}, Step: {current_step})"
    )
    metadata = storage.load_task_metadata(task_id, bypass_cache=True)

    if metadata is None:
        logger.warning(
            f"Metadata not found for task {task_id} during update. Creating."
        )
        metadata = {
            "taskId": task_id,
            "created": datetime.now().isoformat(),
        }

    # Update fields
    metadata["status"] = status_value
    metadata["updated"] = datetime.now().isoformat()
    if progress is not None:
        metadata["progress"] = progress
    if current_step is not None:
        metadata["currentStep"] = current_step  # Store the current step name
    if error is not None:
        metadata["error"] = error
    if traceback is not None:
        metadata["traceback"] = traceback
    if status_value == TaskStatus.COMPLETED.value and "completedAt" not in metadata:
        metadata["completedAt"] = metadata["updated"]  # Set completion time

    # Save updated metadata to storage (always force write for updates)
    storage.save_task_metadata(task_id, metadata, force=True)

    # --- Update Redis State (Best Effort) ---
    celery_id = metadata.get("celery_id") or metadata.get("celery_task_id")
    if celery_id:
        try:
            celery_state = states.PENDING  # Default
            celery_result = None

            if status_value == TaskStatus.COMPLETED.value:
                celery_state = states.SUCCESS
                celery_result = {
                    "taskId": task_id,
                    "status": "completed",
                    "message": "Task completed successfully",
                    "results": metadata.get("results"),  # Include results if available
                }
            elif status_value == TaskStatus.FAILED.value:
                celery_state = states.FAILURE
                celery_result = Exception(
                    metadata.get("error", "Unknown error")
                )  # Store error as exception for Celery
            elif status_value == TaskStatus.PROCESSING.value:
                celery_state = states.STARTED
                celery_result = {  # Use meta field for progress/step
                    "taskId": task_id,
                    "status": "processing",
                    "progress": metadata.get("progress", 0),
                    "currentStep": metadata.get("currentStep", None),
                }

            # Use Celery's update_state for better integration
            task = celery_app.AsyncResult(celery_id)
            task.backend.store_result(
                celery_id,
                result=celery_result,
                state=celery_state,
                traceback=metadata.get("traceback")
                if celery_state == states.FAILURE
                else None,
                request=task.request,  # Pass request context if available
                # meta=celery_result if celery_state == states.STARTED else None # Store progress in meta
            )

            logger.info(
                f"Updated Celery backend state for task {task_id} (celery_id={celery_id}) to {celery_state}"
            )
        except Exception as e:
            logger.error(f"Failed to update Celery backend for task {task_id}: {e}")

    return metadata


@celery_app.task(
    name="pixeletica.api.services.task_queue.process_image_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=3000,
    time_limit=3600,
    queue="celery",
)
def process_image_task(self, task_id: str) -> Dict[str, Any]:
    """
    Process an image conversion task in the background.

    Args:
        task_id: Task identifier

    Returns:
        Dictionary with task results
    """
    start_time = datetime.now()
    logger.info(f"⭐ WORKER RECEIVED TASK: {task_id} at {start_time}")
    logger.info(f"Task request details: {self.request!r}")
    logger.info(f"Worker process ID: {os.getpid()}")

    # Store the celery task ID (which should match)
    celery_id = self.request.id

    # Ensure the task directory exists
    storage.ensure_task_directory(task_id)

    # Synchronize task state at the beginning
    sync_result = sync_task_state(task_id, celery_id)
    if not sync_result:
        logger.error(f"Failed to synchronize task {task_id} at start")
        # Attempt to mark as failed even if sync failed initially
        update_task_status(
            task_id, TaskStatus.FAILED, error="Task synchronization failed at start"
        )
        return {
            "taskId": task_id,
            "status": TaskStatus.FAILED.value,
            "error": "Task synchronization failed at start",
        }

    # Check if task was already completed or failed during sync
    if sync_result.get("status") in [
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
    ]:
        logger.warning(
            f"Task {task_id} already in terminal state ({sync_result.get('status')}). Skipping processing."
        )
        return {
            "taskId": task_id,
            "status": sync_result.get("status"),
            "message": "Task already completed or failed.",
            "error": sync_result.get("error"),
        }

    metadata = sync_result  # Use the synchronized metadata

    try:
        # Define the total number of steps in the process for accurate progress tracking
        steps = {
            "initialization": {"weight": 5, "completed": False},
            "loading_image": {"weight": 5, "completed": False},
            "resizing_image": {"weight": 10, "completed": False},
            "processing_image": {
                "weight": 50,
                "completed": False,
            },  # Combined dither+render
            "saving_outputs": {
                "weight": 10,
                "completed": False,
            },  # Saving dithered/rendered
            "exporting": {"weight": 15, "completed": False},
            "generating_schematic": {"weight": 10, "completed": False},
            "creating_archive": {"weight": 5, "completed": False},
        }

        # Function to calculate and update current progress
        def update_progress(step_name, sub_progress=100):
            nonlocal metadata  # Allow modification of the outer metadata dict
            if step_name not in steps:
                logger.warning(f"Unknown progress step: {step_name}")
                return

            # Mark step as completed only when sub_progress is 100 or more
            if sub_progress >= 100:
                steps[step_name]["completed"] = True

            # Calculate total progress based on completed steps and current sub-progress
            completed_weight = sum(
                step["weight"] for name, step in steps.items() if step["completed"]
            )

            # Calculate contribution from the current step's sub-progress, only if not yet completed
            current_step_contribution = 0
            if not steps[step_name]["completed"]:
                current_step_weight = steps[step_name]["weight"]
                current_step_contribution = current_step_weight * (
                    min(sub_progress, 100) / 100.0
                )
                # Find weights of *other* completed steps
                other_completed_weight = sum(
                    step["weight"]
                    for name, step in steps.items()
                    if step["completed"] and name != step_name
                )
                total_progress = other_completed_weight + current_step_contribution
            else:
                # If step is marked complete, use the sum of weights of all completed steps
                total_progress = completed_weight

            total_progress = int(round(total_progress))  # Round to nearest int
            total_progress = max(0, min(100, total_progress))  # Clamp to 0-100

            # Update task status via the dedicated function
            metadata = update_task_status(  # Update the outer metadata variable
                task_id,
                TaskStatus.PROCESSING,
                progress=total_progress,
                current_step=step_name,
            )
            logger.info(
                f"Task {task_id} progress: {total_progress}% (Step: {step_name}, Sub: {sub_progress}%)"
            )

        # --- Start Processing ---
        update_progress("initialization")  # Progress: 5%

        logger.info(f"Task {task_id} metadata keys: {list(metadata.keys())}")
        config = metadata.get("config", metadata)  # Ensure consistent config access

        input_image_path = metadata.get("inputImagePath")
        if not input_image_path:
            raise ValueError("Input image path not found in task metadata")

        # Load the image
        update_progress("loading_image")  # Progress: 10%
        original_img = load_image(input_image_path)
        if not original_img:
            raise ValueError(f"Failed to load image from {input_image_path}")

        # Resize image
        target_width = config.get("width")
        target_height = config.get("height")
        if target_width or target_height:
            update_progress("resizing_image", 50)  # Start resize
            resized_img = resize_image(original_img, target_width, target_height)
            update_progress("resizing_image")  # Resize complete (Progress: 20%)
        else:
            resized_img = original_img
            update_progress("resizing_image")  # Skip resize (Progress: 20%)

        # --- Process Image using Shared Converter ---
        update_progress("processing_image", 0)  # Mark start (Progress: 20%)
        algorithm_name = config.get("algorithm", "floyd_steinberg")
        color_palette = config.get("color_palette", "minecraft")
        _, algorithm_id = get_algorithm_by_name(algorithm_name)

        def processing_progress_callback(sub_progress, step_name):
            # Scale sub-progress (0-100) to fit within the processing step's weight (50%)
            # Base progress is 20% (init+load+resize)
            # Use min(sub_progress, 100) to prevent exceeding 100% for the sub-step
            current_step_progress = min(sub_progress, 100)
            # Pass the scaled progress directly to update_progress
            update_progress("processing_image", current_step_progress)
            logger.info(f"Task {task_id} sub-step: {step_name} ({sub_progress}%)")

        processing_results = process_image_to_blocks(
            resized_img,
            algorithm_name,
            color_palette=color_palette,
            progress_callback=processing_progress_callback,
        )
        # Ensure processing step is marked fully complete
        update_progress("processing_image", 100)  # Mark complete (Progress: 70%)

        dithered_img = processing_results.get("dithered_image")  # Use .get for safety
        block_image = processing_results.get("rendered_image")
        block_ids = processing_results.get("block_ids")

        # --- Save Dithered and Rendered Images ---
        update_progress("saving_outputs", 0)  # Start saving (Progress: 70%)
        filename = config.get("filename", "image.png")
        base_name = Path(filename).stem

        if dithered_img:
            dithered_filename = f"{base_name}_dithered.png"
            dithered_file_info = storage.save_output_file(
                task_id, dithered_img, dithered_filename, "dithered"
            )
            metadata["ditheredImage"] = dithered_file_info
        else:
            logger.warning(f"Dithered image not generated for task {task_id}")
        update_progress("saving_outputs", 50)  # Dithered saved (Progress: 75%)

        if block_image:
            rendered_filename = f"{base_name}_rendered.png"
            rendered_file_info = storage.save_output_file(
                task_id, block_image, rendered_filename, "rendered"
            )
            metadata["renderedImage"] = rendered_file_info
            logger.info(f"Saved rendered block image for task {task_id}")
        else:
            logger.error(f"Rendered block image not generated for task {task_id}")
        # Save metadata potentially updated with image paths
        storage.save_task_metadata(task_id, metadata, force=True)
        update_progress("saving_outputs")  # Saving complete (Progress: 80%)

        # --- Exporting ---
        update_progress("exporting", 0)  # Start exporting (Progress: 80%)
        export_settings = {}
        origin_x, origin_y, origin_z = 0, 0, 0  # Default origins

        if block_image:
            try:
                export_settings = config.get(
                    "exportSettings", metadata.get("exportSettings", {})
                )
                version_options = config.get(
                    "version_options", metadata.get("version_options", {})
                )
                export_types = config.get("export_types", ["web"]) or ["web"]

                origin_x = export_settings.get("originX", config.get("origin_x", 0))
                origin_y = export_settings.get("originY", config.get("origin_y", 0))
                origin_z = export_settings.get("originZ", config.get("origin_z", 0))
                draw_chunk_lines = export_settings.get("drawChunkLines", True)
                chunk_line_color = export_settings.get("chunkLineColor", "#FF0000")
                draw_block_lines = export_settings.get("drawBlockLines", True)
                block_line_color = export_settings.get("blockLineColor", "#000000")
                split_count = export_settings.get(
                    "splitCount", config.get("image_division", 1)
                )

                # Define the root output directory for the task
                task_output_dir = storage.TASKS_DIR / task_id
                logger.info(f"Exporting files to task directory: {task_output_dir}")

                export_results = export_processed_image(
                    block_image,
                    base_name,
                    export_types=export_types,
                    origin_x=origin_x,
                    origin_z=origin_z,  # Note: origin_y not used by export_processed_image
                    draw_chunk_lines=draw_chunk_lines,
                    chunk_line_color=chunk_line_color,
                    draw_block_lines=draw_block_lines,
                    block_line_color=block_line_color,
                    split_count=split_count,
                    version_options=version_options,
                    algorithm_name=algorithm_id,
                    output_dir=str(task_output_dir),  # Pass the root task directory
                )
                logger.info(f"Export results: {export_results}")
                metadata["exports"] = export_results
                storage.save_task_metadata(
                    task_id, metadata, force=True
                )  # Save after export results

                if "export_files" in export_results:
                    for file_info in export_results["export_files"]:
                        try:
                            file_path = Path(file_info["path"])
                            category = file_info.get("category", "web")
                            if file_path.exists():
                                with open(file_path, "rb") as f:
                                    file_data = f.read()
                                storage.save_output_file(
                                    task_id, file_data, file_path.name, category
                                )
                        except Exception as e_import:
                            logger.error(
                                f"Failed to import export file {file_info.get('path')}: {e_import}"
                            )

            except Exception as e_export:
                logger.error(
                    f"Error during export for task {task_id}: {e_export}", exc_info=True
                )
                metadata["exportError"] = str(e_export)
                storage.save_task_metadata(
                    task_id, metadata, force=True
                )  # Save error to metadata
        else:
            logger.warning(
                f"Skipping export for task {task_id} as rendered image was not generated."
            )
        update_progress("exporting")  # Export complete or skipped (Progress: 95%)

        # --- Generate Schematic ---
        update_progress(
            "generating_schematic", 0
        )  # Start schematic gen (Progress: 95%)
        schematic_settings = config.get(
            "schematicSettings", metadata.get("schematicSettings", {})
        )
        # Use origins defined/extracted during the export step (or defaults if export skipped)
        origin_y_schem = schematic_settings.get(
            "originY", origin_y
        )  # Use export's origin_y as fallback

        generate_schematic_flag = schematic_settings.get(
            "generateSchematic", config.get("generate_schematic", False)
        )

        if generate_schematic_flag and block_ids:
            try:
                update_progress("generating_schematic", 20)  # Indicate start
                schematic_metadata = {
                    "author": schematic_settings.get(
                        "author", config.get("schematic_author", "Pixeletica API")
                    ),
                    "name": schematic_settings.get(
                        "name", config.get("schematic_name", base_name)
                    ),
                    "description": schematic_settings.get(
                        "description",
                        config.get(
                            "schematic_description", f"Generated from {base_name}"
                        ),
                    ),
                }

                schematic_path = generate_schematic(
                    block_ids,
                    filename,
                    algorithm_id,
                    schematic_metadata,
                    origin_x=origin_x,
                    origin_y=origin_y_schem,
                    origin_z=origin_z,
                )
                update_progress("generating_schematic", 80)  # Indicate progress

                if schematic_path and Path(schematic_path).exists():
                    with open(schematic_path, "rb") as f:
                        schematic_data = f.read()
                    schematic_filename = Path(schematic_path).name
                    schematic_file_info = storage.save_output_file(
                        task_id, schematic_data, schematic_filename, "schematic"
                    )
                    metadata["schematicFile"] = schematic_file_info
                    storage.save_task_metadata(
                        task_id, metadata, force=True
                    )  # Save after schematic info
                else:
                    logger.warning(
                        f"Schematic file not found or not generated: {schematic_path}"
                    )

            except Exception as e_schem:
                logger.error(
                    f"Error generating schematic for task {task_id}: {e_schem}",
                    exc_info=True,
                )
                metadata["schematicError"] = str(e_schem)
                storage.save_task_metadata(
                    task_id, metadata, force=True
                )  # Save error to metadata
        else:
            logger.info(
                f"Skipping schematic generation for task {task_id} (Flag: {generate_schematic_flag}, Block IDs: {'Yes' if block_ids else 'No'})"
            )

        update_progress(
            "generating_schematic"
        )  # Schematic complete or skipped (Progress: 100%)

        # --- Create ZIP Archive ---
        # This step's weight (5) is effectively ignored as progress is already 100%
        update_progress("creating_archive", 0)
        try:
            zip_path = storage.create_zip_archive(task_id)
            if zip_path:
                with open(zip_path, "rb") as f:
                    zip_data = f.read()
                zip_file_info = storage.save_output_file(
                    task_id, zip_data, f"pixeletica_task_{task_id}.zip", "output"
                )
                metadata["zipFile"] = zip_file_info
                storage.save_task_metadata(
                    task_id, metadata, force=True
                )  # Save after zip info
        except Exception as e_zip:
            logger.error(
                f"Error creating ZIP archive for task {task_id}: {e_zip}", exc_info=True
            )
            metadata["zipError"] = str(e_zip)  # Add zip error to metadata
            storage.save_task_metadata(
                task_id, metadata, force=True
            )  # Save error to metadata

        update_progress(
            "creating_archive"
        )  # Archive complete or failed (Progress still 100%)

        # --- Finalize Task ---
        logger.info(f"Task {task_id} finished processing steps, marking as COMPLETED")
        completion_time = datetime.now().isoformat()
        # Update status to COMPLETED and include any non-critical errors from optional steps
        final_metadata = update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            error=metadata.get(
                "error"
            ),  # Keep existing error if any? Or clear? Let's clear for success.
            traceback=metadata.get(
                "traceback"
            ),  # Keep existing traceback? Or clear? Let's clear.
        )
        final_metadata["completedAt"] = completion_time
        # Add specific errors from optional steps if they occurred
        if "exportError" in metadata:
            final_metadata["exportError"] = metadata["exportError"]
        if "schematicError" in metadata:
            final_metadata["schematicError"] = metadata["schematicError"]
        if "zipError" in metadata:
            final_metadata["zipError"] = metadata["zipError"]

        # Save the final metadata state
        storage.save_task_metadata(task_id, final_metadata, force=True)
        logger.info(
            f"✅ Task {task_id} successfully marked as COMPLETED at {completion_time}"
        )

        storage.clear_metadata_cache(task_id)
        logger.info(f"✅ Cleared Redis cache for task {task_id}")

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        logger.info(f"Task {task_id} completed in {processing_time:.1f} seconds")

        # Prepare final result dictionary for Celery
        task_result = {
            "taskId": task_id,
            "status": TaskStatus.COMPLETED.value,
            "message": f"Image processing completed successfully in {processing_time:.1f} seconds",
            "results": {
                "ditheredImage": final_metadata.get("ditheredImage"),
                "renderedImage": final_metadata.get("renderedImage"),
                "schematicFile": final_metadata.get("schematicFile"),
                "zipFile": final_metadata.get("zipFile"),
                "exports": final_metadata.get("exports"),
            },
        }
        # Include non-critical errors in the result message if they occurred
        non_critical_errors = []
        if "exportError" in final_metadata:
            non_critical_errors.append(
                f"Export failed: {final_metadata['exportError']}"
            )
        if "schematicError" in final_metadata:
            non_critical_errors.append(
                f"Schematic generation failed: {final_metadata['schematicError']}"
            )
        if "zipError" in final_metadata:
            non_critical_errors.append(
                f"ZIP archive creation failed: {final_metadata['zipError']}"
            )
        if non_critical_errors:
            task_result["message"] += " with errors: " + "; ".join(non_critical_errors)
            task_result["warnings"] = (
                non_critical_errors  # Add a specific warnings field
            )

        return task_result

    except Exception as e:
        # --- Handle Critical Errors ---
        logger.error(f"CRITICAL ERROR processing task {task_id}: {e}", exc_info=True)
        try:
            import traceback

            tb_str = traceback.format_exc()
            # Update status to FAILED with error and traceback
            update_task_status(
                task_id, TaskStatus.FAILED, error=str(e), traceback=tb_str
            )
            logger.info(f"Marked task {task_id} as FAILED due to critical error")
        except Exception as e2:
            logger.critical(
                f"Failed to mark task {task_id} as failed after critical error: {e2}"
            )

        # Return failure result for Celery
        return {"taskId": task_id, "status": TaskStatus.FAILED.value, "error": str(e)}
