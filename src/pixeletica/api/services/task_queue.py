"""
Task queue service for handling background processing of image conversion tasks.

This module uses Celery to manage background tasks for image processing operations.
"""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from celery import Celery

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

# Enable more verbose Celery logging
logging.getLogger("celery").setLevel(logging.DEBUG)

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
    task_acks_late=False,  # Acknowledge tasks before execution to avoid re-queuing on failure
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_cancel_long_running_tasks_on_connection_loss=False,  # Don't cancel tasks if connection lost
    worker_max_tasks_per_child=50,  # Restart worker after processing 50 tasks to prevent memory leaks
    broker_connection_retry_on_startup=True,  # Retry connecting to broker on startup
    broker_connection_max_retries=10,  # Max retries for broker connection
)

# Register the module that contains the task to ensure proper discovery
celery_app.autodiscover_tasks(["src.pixeletica.api.services"])

# Configure Celery task routes - ensure tasks are sent to the 'celery' queue
# which is where the worker is listening by default
celery_app.conf.task_routes = {
    "pixeletica.api.services.task_queue.*": {"queue": "celery"},
    "src.pixeletica.api.services.task_queue.*": {
        "queue": "celery"
    },  # Add full path as alternate
}

# Import all modules that define tasks so they're properly registered
logger.info("Registering Celery tasks...")
logger.info("Current Celery app: %s", celery_app)


def create_task(request_data: Dict) -> str:
    """
    Create a new conversion task.

    Args:
        request_data: Dictionary containing task configuration data

    Returns:
        Task ID as a string
    """
    # Log function entry for debugging
    logger.info(
        f"Creating new task with request data keys: {list(request_data.keys())}"
    )

    # Verify Redis connection at task creation time
    try:
        from redis import Redis

        r = Redis.from_url(redis_url)
        ping_result = r.ping()
        logger.info(f"Redis connection verified for task creation: ping={ping_result}")

        # Additional Redis check
        r.set("pixeletica_test_key", "test_value")
        test_value = r.get("pixeletica_test_key")
        if test_value == b"test_value":
            logger.info("Redis read/write test successful")
        else:
            logger.warning(f"Redis read/write test failed: got {test_value}")
    except Exception as e:
        logger.error(
            f"Redis connection failed during task creation: {e}", exc_info=True
        )

    # Generate a unique task ID
    task_id = str(uuid.uuid4())
    logger.info(f"Creating new task with ID: {task_id}")

    # Initialize task metadata
    task_metadata = {
        "taskId": task_id,
        "status": TaskStatus.QUEUED,
        "progress": 0,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "config": {
            "filename": request_data.get("filename", "image.png"),
            "width": request_data.get("width"),
            "height": request_data.get("height"),
            "algorithm": request_data.get("algorithm", "floyd_steinberg"),
            "exportSettings": request_data.get("exportSettings", {}),
            "schematicSettings": request_data.get("schematicSettings", {}),
        },
    }

    # Save the image
    image_data = request_data.get("image", "")
    if image_data:
        try:
            image_path = storage.save_base64_image(
                task_id, image_data, request_data.get("filename", "image.png")
            )
            task_metadata["inputImagePath"] = str(image_path)
        except Exception as e:
            logger.error(f"Failed to save input image for task {task_id}: {e}")
            task_metadata["status"] = TaskStatus.FAILED
            task_metadata["error"] = f"Failed to save input image: {str(e)}"

    # Save task metadata
    storage.save_task_metadata(task_id, task_metadata)

    # Start processing task if image was saved successfully
    if task_metadata["status"] != TaskStatus.FAILED:
        try:
            # Get the actual task function to avoid string reference issues
            task_function = process_image_task
            logger.info(f"Sending task using function: {task_function.name}")

            # Apply the task directly which gives us more control
            result = task_function.apply_async(
                args=[task_id],
                task_id=str(uuid.uuid4()),  # Generate a new unique task ID
                queue="celery",  # Explicitly specify the queue
                retry=True,  # Enable retries
                retry_policy={  # Configure retry policy
                    "max_retries": 3,
                    "interval_start": 0,
                    "interval_step": 60,
                    "interval_max": 180,
                },
            )

            logger.info(
                f"Task {task_id} queued for processing with task_id: {result.id}"
            )
            logger.info(f"Task state: {result.state}")
            logger.info(f"Task result backend: {result.backend}")

            # More thorough task verification in Redis
            try:
                from redis import Redis

                r = Redis.from_url(redis_url)
                # Check for various possible task keys in Redis
                task_key_patterns = [
                    f"celery-task-meta-{result.id}",
                    f"_celery_task_meta-{result.id}",
                    f"celery-task-{result.id}",
                ]

                found = False
                for task_key in task_key_patterns:
                    if r.exists(task_key):
                        logger.info(
                            f"Task {result.id} found in Redis under key: {task_key}"
                        )
                        found = True
                        break

                if not found:
                    # Check if the task is in the queue
                    queue_key = "celery"
                    queue_length = r.llen(queue_key)
                    logger.warning(
                        f"Task {result.id} not found in Redis - checking queue '{queue_key}' (length: {queue_length})"
                    )

                    # Add a task directly to Redis as a test
                    test_task_id = str(uuid.uuid4())
                    test_key = f"celery-task-meta-{test_task_id}"
                    r.set(test_key, "test")
                    if r.exists(test_key):
                        logger.info(
                            f"Test key {test_key} successfully created in Redis"
                        )
                        r.delete(test_key)
                    else:
                        logger.error(f"Failed to create test key {test_key} in Redis")
            except Exception as e:
                logger.error(
                    f"Failed to check Redis for task {result.id}: {e}", exc_info=True
                )
        except Exception as e:
            logger.error(f"Failed to queue task {task_id}: {e}", exc_info=True)
            # Update task status to failed since queueing failed
            update_task_status(
                task_id, TaskStatus.FAILED, error=f"Failed to queue task: {str(e)}"
            )

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
    # Log this function call for debugging
    logger.info(f"Getting status for task {task_id} (bypass_cache={bypass_cache})")

    # Get the metadata from storage
    metadata = storage.load_task_metadata(task_id, bypass_cache=bypass_cache)

    if metadata:
        logger.info(
            f"Task {task_id} status: {metadata.get('status')}, progress: {metadata.get('progress')}"
        )
    else:
        logger.warning(f"No metadata found for task {task_id}")

    # If the task is in processing status for too long, it might be stuck
    if metadata and metadata.get("status") == TaskStatus.PROCESSING:
        try:
            # Check if the task has been processing for more than 10 minutes
            updated_time = datetime.fromisoformat(metadata.get("updated", ""))
            now = datetime.now()
            processing_time = (now - updated_time).total_seconds()

            if processing_time > 600:  # 10 minutes
                logger.warning(
                    f"Task {task_id} has been processing for {processing_time} seconds, this may indicate a stuck task"
                )

                # Try to check if the task is still in Celery
                try:
                    from redis import Redis

                    r = Redis.from_url(redis_url)
                    celery_task_id = metadata.get("celery_task_id")
                    if celery_task_id:
                        task_key = f"celery-task-meta-{celery_task_id}"
                        if r.exists(task_key):
                            logger.info(
                                f"Celery task {celery_task_id} still exists in Redis"
                            )
                        else:
                            logger.warning(
                                f"Celery task {celery_task_id} not found in Redis, but status is still PROCESSING"
                            )
                except Exception as e:
                    logger.error(f"Failed to check Redis for stuck task {task_id}: {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"Error checking task processing time: {e}")

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
    metadata = storage.load_task_metadata(task_id)

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

    # Save updated metadata
    storage.save_task_metadata(task_id, metadata)

    return metadata


@celery_app.task(
    name="pixeletica.api.services.task_queue.process_image_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=3000,
    time_limit=3600,
    queue="celery",  # Explicitly specify the queue
    track_started=True,  # Track when task is started
    ignore_result=False,  # Don't ignore results
    acks_late=False,  # Acknowledge task before execution
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

    # Update task metadata with celery task ID for tracking
    try:
        metadata = storage.load_task_metadata(task_id, bypass_cache=True)
        if metadata:
            metadata["celery_task_id"] = self.request.id
            storage.save_task_metadata(task_id, metadata, force=True)
            logger.info(f"Updated task metadata with celery_task_id: {self.request.id}")
    except Exception as e:
        logger.error(
            f"Failed to update metadata with celery task ID: {e}", exc_info=True
        )

    try:
        # Verify Redis connection before starting
        try:
            from redis import Redis

            r = Redis.from_url(redis_url)
            r.ping()
            logger.info(f"Redis connection verified for task {task_id}")
        except Exception as e:
            logger.error(f"Redis connection failed for task {task_id}: {e}")
            # Continue anyway, as we're using local file storage for task state

        # Update task status to processing
        update_task_status(task_id, TaskStatus.PROCESSING, progress=5)

        # Load task metadata
        metadata = storage.load_task_metadata(task_id)
        if not metadata:
            raise ValueError(f"Task metadata not found for task {task_id}")

        # Log metadata keys to debug
        logger.info(f"Task {task_id} metadata keys: {list(metadata.keys())}")

        # Try to load exportSettings from various possible locations in the metadata
        export_settings = metadata.get("exportSettings", {})
        if not export_settings and "config" in metadata:
            export_settings = metadata.get("config", {}).get("exportSettings", {})
            logger.info(f"Found exportSettings in config: {bool(export_settings)}")

        # Try to find the input image path
        input_image_path = metadata.get("inputImagePath")
        if not input_image_path and "config" in metadata:
            config = metadata.get("config", {})
        else:
            config = metadata

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
                export_settings = config.get("exportSettings", {})

                export_types = export_settings.get("exportTypes", ["png"])
                origin_x = export_settings.get("originX", 0)
                origin_y = export_settings.get("originY", 0)
                origin_z = export_settings.get("originZ", 0)
                draw_chunk_lines = export_settings.get("drawChunkLines", True)
                chunk_line_color = export_settings.get("chunkLineColor", "#FF0000")
                draw_block_lines = export_settings.get("drawBlockLines", True)
                block_line_color = export_settings.get("blockLineColor", "#000000")
                split_count = export_settings.get("splitCount", 1)
                version_options = export_settings.get("versionOptions", {})

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
        schematic_settings = config.get("schematicSettings", {})
        if schematic_settings.get("generateSchematic", False) and block_ids:
            try:
                # Prepare schematic metadata
                schematic_metadata = {
                    "author": schematic_settings.get("author", "Pixeletica API"),
                    "name": schematic_settings.get("name", base_name),
                    "description": schematic_settings.get(
                        "description", f"Generated from {base_name}"
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

        # Force bypass cache and update status directly
        metadata = storage.load_task_metadata(task_id, bypass_cache=True)
        if metadata:
            metadata["status"] = TaskStatus.COMPLETED.value
            metadata["progress"] = 100
            metadata["updated"] = completion_time
            metadata["completedAt"] = completion_time

            # Make sure task result is saved in Redis
            try:
                from redis import Redis

                r = Redis.from_url(redis_url)
                result_key = f"celery-task-meta-{self.request.id}"
                result_data = {
                    "status": "SUCCESS",
                    "result": {
                        "taskId": task_id,
                        "status": TaskStatus.COMPLETED.value,
                        "message": f"Image processing completed successfully",
                    },
                    "traceback": None,
                    "children": [],
                    "date_done": completion_time,
                }
                r.set(result_key, json.dumps(result_data))
                logger.info(f"Set result in Redis at key {result_key}")
            except Exception as e:
                logger.error(
                    f"Failed to manually set task result in Redis: {e}", exc_info=True
                )

            # Save final metadata
            storage.save_task_metadata(task_id, metadata, force=True)
            logger.info(f"✅ Task metadata updated with COMPLETED status: {metadata}")

            # Clear Redis cache for this task's metadata to ensure fresh reads
            storage.clear_metadata_cache(task_id)
            logger.info(f"✅ Cleared Redis cache for task {task_id}")
        else:
            # Create new metadata if it doesn't exist
            new_metadata = {
                "taskId": task_id,
                "status": TaskStatus.COMPLETED.value,
                "progress": 100,
                "created": datetime.now().isoformat(),
                "updated": completion_time,
                "completedAt": completion_time,
            }
            storage.save_task_metadata(task_id, new_metadata, force=True)
            logger.info(f"✅ Created new COMPLETED metadata: {new_metadata}")

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        logger.info(
            f"Task {task_id} completed successfully in {processing_time} seconds"
        )

        return {
            "taskId": task_id,
            "status": TaskStatus.COMPLETED.value,
            "message": f"Image processing completed successfully in {processing_time} seconds",
        }

    except (KeyboardInterrupt, SystemExit):
        logger.critical(f"Task {task_id} was interrupted by system, marking as failed")
        update_task_status(
            task_id, TaskStatus.FAILED, error="Task was interrupted by system"
        )
        raise

    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
        update_task_status(task_id, TaskStatus.FAILED, error=str(e))

        # Verify error status was saved
        error_status = get_task_status(task_id)
        if error_status and error_status.get("status") != TaskStatus.FAILED.value:
            logger.error(
                f"Failed to update task {task_id} to FAILED status, forcing update"
            )
            # Force another update attempt
            metadata = storage.load_task_metadata(task_id, bypass_cache=True)
            if metadata:
                metadata["status"] = TaskStatus.FAILED.value
                metadata["error"] = str(e)
                metadata["updated"] = datetime.now().isoformat()
                storage.save_task_metadata(task_id, metadata, force=True)

        return {"taskId": task_id, "status": TaskStatus.FAILED.value, "error": str(e)}
