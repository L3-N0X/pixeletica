"""
Task queue service for handling background processing of image conversion tasks.

This module provides a robust implementation of Celery-based task queuing with reliable
state management between Redis and filesystem storage.
"""

import logging
import os
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union, List, Tuple

from celery import Celery, states
from celery.result import AsyncResult

from src.pixeletica.api.models import TaskStatus
from src.pixeletica.api.services import storage
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.export.export_manager import export_processed_image
from src.pixeletica.image_ops import load_image, resize_image
from src.pixeletica.rendering.block_renderer import render_blocks_from_block_ids
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
                    metadata["completedAt"] = datetime.now().isoformat()
                elif redis_state == states.FAILURE:
                    metadata["status"] = TaskStatus.FAILED.value
                    metadata["error"] = (
                        str(redis_result) if redis_result else "Unknown error"
                    )
                    metadata["traceback"] = redis_traceback
                elif redis_state == states.STARTED:
                    metadata["status"] = TaskStatus.PROCESSING.value
                elif redis_state == states.PENDING:
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
    success = storage.save_task_metadata(task_id, metadata, force=True)

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
            logger.info(f"Redis connection verified for task creation")
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

    # Check for stuck tasks
    if metadata.get("status") == TaskStatus.QUEUED.value:
        try:
            created_time = datetime.fromisoformat(metadata.get("created", ""))
            now = datetime.now()
            queue_time = (now - created_time).total_seconds()

            # If task has been queued for over 5 minutes, mark as failed
            if queue_time > 300:  # 5 minutes
                logger.warning(
                    f"Task {task_id} has been queued for {queue_time:.1f} seconds, marking as failed"
                )
                metadata["status"] = TaskStatus.FAILED.value
                metadata["error"] = "Task timed out in queue"
                metadata["updated"] = datetime.now().isoformat()
                storage.save_task_metadata(task_id, metadata, force=True)
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking queued time: {e}")

    elif metadata.get("status") == TaskStatus.PROCESSING.value:
        try:
            updated_time = datetime.fromisoformat(metadata.get("updated", ""))
            now = datetime.now()
            processing_time = (now - updated_time).total_seconds()

            # If no update in 10 minutes while processing, mark as failed
            if processing_time > 600:  # 10 minutes
                logger.warning(
                    f"Task {task_id} has been processing without updates for {processing_time:.1f} seconds, marking as failed"
                )
                metadata["status"] = TaskStatus.FAILED.value
                metadata["error"] = "Task processing timed out"
                metadata["updated"] = datetime.now().isoformat()
                storage.save_task_metadata(task_id, metadata, force=True)
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking processing time: {e}")

    return metadata


def update_task_status(
    task_id: str,
    status: Union[str, TaskStatus],
    progress: Optional[int] = None,
    error: Optional[str] = None,
) -> Dict:
    """
    Update the status of a task.

    Args:
        task_id: Task identifier
        status: New task status
        progress: Optional progress percentage (0-100)
        error: Optional error message if task failed

    Returns:
        Updated task metadata
    """
    logger.info(f"Updating task {task_id} status to {status} (progress: {progress})")
    metadata = storage.load_task_metadata(task_id, bypass_cache=True)

    if metadata is None:
        # Create new metadata if it doesn't exist
        metadata = {
            "taskId": task_id,
            "status": status if isinstance(status, str) else status.value,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        }
    else:
        # Update existing metadata
        metadata["status"] = status if isinstance(status, str) else status.value
        metadata["updated"] = datetime.now().isoformat()

    if progress is not None:
        metadata["progress"] = progress

    if error is not None:
        metadata["error"] = error

    # Save updated metadata with force=True to ensure it's written
    storage.save_task_metadata(task_id, metadata, force=True)

    # If we have a celery_id, update the Redis state too
    celery_id = metadata.get("celery_id") or metadata.get("celery_task_id")
    if celery_id:
        try:
            # Map our task states to Celery states
            status_str = metadata["status"]
            if status_str == TaskStatus.COMPLETED.value:
                celery_state = states.SUCCESS
                celery_result = {
                    "taskId": task_id,
                    "status": "completed",
                    "message": "Task completed successfully",
                }
            elif status_str == TaskStatus.FAILED.value:
                celery_state = states.FAILURE
                celery_result = {
                    "taskId": task_id,
                    "status": "failed",
                    "error": metadata.get("error", "Unknown error"),
                }
            elif status_str == TaskStatus.PROCESSING.value:
                celery_state = states.STARTED
                celery_result = {
                    "taskId": task_id,
                    "status": "processing",
                    "progress": metadata.get("progress", 0),
                }
            else:
                celery_state = states.PENDING
                celery_result = None

            # Update Redis directly if needed
            import redis

            r = redis.Redis.from_url(redis_url)
            task_key = f"celery-task-meta-{celery_id}"
            task_data = {
                "status": celery_state,
                "result": celery_result,
                "traceback": None,
                "children": [],
                "date_done": (
                    datetime.now().isoformat()
                    if celery_state in [states.SUCCESS, states.FAILURE]
                    else None
                ),
            }
            r.set(task_key, json.dumps(task_data))
            logger.info(
                f"Updated Redis state for task {task_id} (celery_id={celery_id}) to {celery_state}"
            )
        except Exception as e:
            logger.error(f"Failed to update Redis for task {task_id}: {e}")

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

    # Synchronize task state
    sync_result = sync_task_state(task_id, celery_id)
    if not sync_result:
        logger.error(f"Failed to synchronize task {task_id} at start")
        return {
            "taskId": task_id,
            "status": TaskStatus.FAILED.value,
            "error": "Task synchronization failed",
        }

    try:
        # Update task status to processing
        update_task_status(task_id, TaskStatus.PROCESSING, progress=5)

        # Load task metadata
        metadata = storage.load_task_metadata(task_id, bypass_cache=True)
        if not metadata:
            raise ValueError(f"Task metadata not found for task {task_id}")

        # Log metadata keys to help debug
        logger.info(f"Task {task_id} metadata keys: {list(metadata.keys())}")

        # Ensure consistent config access
        if "config" in metadata:
            config = metadata["config"]
        else:
            config = metadata

        # Try to find the input image path
        input_image_path = metadata.get("inputImagePath")
        if not input_image_path:
            raise ValueError("Input image path not found in task metadata")

        # Load the image
        update_task_status(task_id, TaskStatus.PROCESSING, progress=10)
        original_img = load_image(input_image_path)
        if not original_img:
            raise ValueError(f"Failed to load image from {input_image_path}")

        # Resize image if dimensions provided
        target_width = config.get("width")
        target_height = config.get("height")

        if target_width or target_height:
            update_task_status(task_id, TaskStatus.PROCESSING, progress=20)
            resized_img = resize_image(original_img, target_width, target_height)
        else:
            resized_img = original_img

        # Apply dithering algorithm
        update_task_status(task_id, TaskStatus.PROCESSING, progress=30)
        algorithm_name = config.get("algorithm", "floyd_steinberg")
        dither_func, algorithm_id = get_algorithm_by_name(algorithm_name)

        if not dither_func:
            raise ValueError(f"Unknown dithering algorithm: {algorithm_name}")

        # Load block colors before applying dithering
        from src.pixeletica.block_utils.block_loader import load_block_colors

        # Determine color palette - default to minecraft-2025 if not specified
        color_palette = config.get("color_palette", "minecraft")

        # Choose the appropriate CSV file based on color palette
        if color_palette == "minecraft-2024":
            csv_path = "./src/minecraft/block-colors-2024.csv"
        else:
            # Default to the standard minecraft palette
            csv_path = "./src/minecraft/block-colors-2025.csv"

        logger.info(f"Loading block colors from {csv_path}")
        if not load_block_colors(csv_path):
            raise ValueError(f"Failed to load block colors from {csv_path}")

        dithered_img, block_ids = dither_func(resized_img)

        # Save dithered image
        update_task_status(task_id, TaskStatus.PROCESSING, progress=50)
        filename = config.get("filename", "image.png")
        base_name = Path(filename).stem

        # Save dithered image directly
        dithered_filename = f"{base_name}_dithered.png"
        dithered_file_info = storage.save_output_file(
            task_id, dithered_img, dithered_filename, "dithered"
        )

        # Update metadata with dithered image info
        metadata["ditheredImage"] = dithered_file_info
        storage.save_task_metadata(task_id, metadata)

        # Render blocks with textures
        update_task_status(task_id, TaskStatus.PROCESSING, progress=60)
        try:
            block_image = render_blocks_from_block_ids(block_ids)

            if block_image:
                # Save block-rendered image directly
                rendered_filename = f"{base_name}_rendered.png"
                rendered_file_info = storage.save_output_file(
                    task_id, block_image, rendered_filename, "rendered"
                )

                # Update metadata with rendered image info
                metadata["renderedImage"] = rendered_file_info
                storage.save_task_metadata(task_id, metadata)

                # Process export settings
                update_task_status(task_id, TaskStatus.PROCESSING, progress=70)

                # Extract export settings from various possible locations
                export_settings = {}
                if "exportSettings" in config:
                    export_settings = config["exportSettings"]
                elif "exportSettings" in metadata:
                    export_settings = metadata["exportSettings"]

                # Extract version options from config or direct in request_data
                version_options = config.get("version_options", {})
                if not version_options and "version_options" in metadata:
                    version_options = metadata["version_options"]

                # Get export types
                export_types = config.get("export_types", ["web"])
                if not export_types:
                    export_types = ["web"]

                # Export settings from various fields
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

                # Export processed image with export settings - ensure it's using the shared task directory
                web_output_dir = str(storage.TASKS_DIR / task_id / "web")
                logger.info(f"Exporting files to web directory: {web_output_dir}")

                export_results = export_processed_image(
                    block_image,
                    base_name,
                    export_types=export_types,
                    origin_x=origin_x,
                    origin_z=origin_z,
                    draw_chunk_lines=draw_chunk_lines,
                    chunk_line_color=chunk_line_color,
                    draw_block_lines=draw_block_lines,
                    block_line_color=block_line_color,
                    split_count=split_count,
                    version_options=version_options,
                    algorithm_name=algorithm_id,
                    output_dir=web_output_dir,
                )

                logger.info(f"Export results: {export_results}")

                # Update metadata with export results
                metadata["exports"] = export_results
                storage.save_task_metadata(task_id, metadata)

                # Import exported files to task storage
                if "export_files" in export_results:
                    for export_file in export_results["export_files"]:
                        try:
                            file_path = Path(export_file)
                            if file_path.exists():
                                with open(file_path, "rb") as f:
                                    file_data = f.read()

                                storage.save_output_file(
                                    task_id, file_data, file_path.name, "web"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failed to import export file {export_file}: {e}"
                            )
        except Exception as e:
            logger.error(f"Error during rendering or export for task {task_id}: {e}")
            # Continue processing even if rendering fails

        # Generate schematic if requested
        update_task_status(task_id, TaskStatus.PROCESSING, progress=85)

        # Extract schematic settings
        schematic_settings = {}
        if "schematicSettings" in config:
            schematic_settings = config["schematicSettings"]
        elif "schematicSettings" in metadata:
            schematic_settings = metadata["schematicSettings"]

        # Generate schematic if requested and block_ids available
        generate_schematic_flag = schematic_settings.get(
            "generateSchematic", config.get("generate_schematic", False)
        )

        if generate_schematic_flag and block_ids:
            try:
                # Prepare schematic metadata
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

                # Generate schematic
                schematic_path = generate_schematic(
                    block_ids,
                    filename,
                    algorithm_id,
                    schematic_metadata,
                    origin_x=origin_x,
                    origin_y=origin_y,
                    origin_z=origin_z,
                )

                # Import schematic to task storage
                if schematic_path and Path(schematic_path).exists():
                    with open(schematic_path, "rb") as f:
                        schematic_data = f.read()

                    schematic_filename = Path(schematic_path).name
                    schematic_file_info = storage.save_output_file(
                        task_id, schematic_data, schematic_filename, "schematic"
                    )

                    # Update metadata with schematic info
                    metadata["schematicFile"] = schematic_file_info
                    storage.save_task_metadata(task_id, metadata)
            except Exception as e:
                logger.error(f"Error generating schematic for task {task_id}: {e}")
                metadata["schematicError"] = str(e)
                storage.save_task_metadata(task_id, metadata)

        # Generate ZIP archive of all files
        update_task_status(task_id, TaskStatus.PROCESSING, progress=95)
        try:
            zip_path = storage.create_zip_archive(task_id)
            if zip_path:
                with open(zip_path, "rb") as f:
                    zip_data = f.read()

                zip_file_info = storage.save_output_file(
                    task_id, zip_data, f"pixeletica_task_{task_id}.zip", "output"
                )

                metadata["zipFile"] = zip_file_info
                storage.save_task_metadata(task_id, metadata)
        except Exception as e:
            logger.error(f"Error creating ZIP archive for task {task_id}: {e}")

        # Ensure task is marked as completed
        logger.info(f"Task {task_id} finished processing, updating to COMPLETED status")
        completion_time = datetime.now().isoformat()
        logger.info(f"Setting completion timestamp to: {completion_time}")

        # Update the task completion status
        final_metadata = update_task_status(task_id, TaskStatus.COMPLETED, progress=100)

        # Make sure completion time is set
        final_metadata["completedAt"] = completion_time
        storage.save_task_metadata(task_id, final_metadata, force=True)
        logger.info(f"✅ Task {task_id} successfully marked as COMPLETED")

        # Clear Redis cache for this task's metadata
        storage.clear_metadata_cache(task_id)
        logger.info(f"✅ Cleared Redis cache for task {task_id}")

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        logger.info(
            f"Task {task_id} completed successfully in {processing_time:.1f} seconds"
        )

        return {
            "taskId": task_id,
            "status": TaskStatus.COMPLETED.value,
            "message": f"Image processing completed successfully in {processing_time:.1f} seconds",
        }

    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}", exc_info=True)

        # Always update the task status to failed
        try:
            update_task_status(task_id, TaskStatus.FAILED, error=str(e))
            logger.info(f"Marked task {task_id} as FAILED due to error")
        except Exception as e2:
            logger.critical(f"Failed to mark task {task_id} as failed: {e2}")

        return {"taskId": task_id, "status": TaskStatus.FAILED.value, "error": str(e)}
