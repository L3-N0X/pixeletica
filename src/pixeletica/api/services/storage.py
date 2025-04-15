"""
Storage service for managing files related to conversion tasks.

This module handles:
- Creating task directories
- Saving uploaded images
- Managing output files
- Providing file information
- Reliable metadata storage and retrieval
"""

import base64
import json
import logging
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from PIL import Image

# Set up logging
logger = logging.getLogger("pixeletica.api.storage")

# Base directory for all task files
# Use /app/tasks which is mounted as a volume in both API and worker containers
TASKS_DIR = Path("/app/tasks")


def ensure_task_directory(task_id: str) -> Path:
    """
    Ensure the directory structure for a task exists.

    Args:
        task_id: Unique task identifier

    Returns:
        Path to the task directory
    """
    task_dir = TASKS_DIR / task_id

    # Create task directory if it doesn't exist
    task_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories for different types of files
    (task_dir / "input").mkdir(exist_ok=True)
    (task_dir / "dithered").mkdir(exist_ok=True)
    (task_dir / "rendered").mkdir(exist_ok=True)
    (task_dir / "schematic").mkdir(exist_ok=True)
    (task_dir / "web").mkdir(exist_ok=True)
    (task_dir / "metadata").mkdir(exist_ok=True)

    return task_dir


def clear_metadata_cache(task_id: str = None):
    """
    Clear the metadata cache for a specific task or all tasks.

    Args:
        task_id: Task identifier (if None, clears all cached metadata)
    """
    if task_id is None:
        # Clear all cached metadata
        load_task_metadata.cache_clear()
        logger.info("Cleared entire task metadata cache")
    else:
        # Try to clear just this entry (this may clear the entire cache due to LRU implementation)
        load_task_metadata.cache_clear()
        logger.info(f"Cleared metadata cache for task {task_id}")

    # Additionally try to clear Redis cache if applicable
    try:
        import redis
        import os

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(redis_url)

        # Clear any keys related to this task if task_id is provided
        if task_id:
            task_key_pattern = f"*{task_id}*"
            keys = r.keys(task_key_pattern)
            if keys:
                r.delete(*keys)
                logger.info(f"Cleared {len(keys)} Redis keys for task {task_id}")
        # Otherwise clear only the cache keys, not task state keys
        else:
            cache_keys = r.keys("*_cache_*")
            if cache_keys:
                r.delete(*cache_keys)
                logger.info(f"Cleared {len(cache_keys)} Redis cache keys")
    except Exception as e:
        logger.error(f"Error clearing Redis cache: {e}")


def save_task_metadata(task_id: str, metadata: Dict, force: bool = False) -> Path:
    """
    Save task metadata to a JSON file with high reliability.

    Args:
        task_id: Task identifier
        metadata: Dictionary containing metadata
        force: If True, flush the cache immediately after saving

    Returns:
        Path to the saved metadata file
    """
    task_dir = ensure_task_directory(task_id)
    metadata_file = task_dir / "metadata" / "task.json"

    # Update timestamp
    metadata["updated"] = datetime.now().isoformat()

    # Ensure taskId is set correctly
    if "taskId" not in metadata:
        metadata["taskId"] = task_id

    retry_count = 3
    for attempt in range(retry_count):
        try:
            # Use atomic write for better reliability
            temp_file = metadata_file.with_suffix(".json.tmp")
            with open(temp_file, "w") as f:
                json.dump(metadata, f, indent=2)

            # Rename for atomic operation
            temp_file.replace(metadata_file)

            # Log successful save
            logger.info(f"Successfully saved metadata for task {task_id}")

            # Clear the cache if requested
            if force:
                clear_metadata_cache(task_id)

            # Verify the file was written correctly by reading it back
            try:
                with open(metadata_file, "r") as f:
                    verification_data = json.load(f)
                    if verification_data.get("status") == metadata.get("status"):
                        logger.info(
                            f"Verified metadata status: {metadata.get('status')}"
                        )
                    else:
                        logger.warning(
                            f"Metadata verification failed: {verification_data.get('status')} != {metadata.get('status')}"
                        )
            except Exception as e:
                logger.warning(f"Failed to verify metadata after save: {e}")

            return metadata_file
        except Exception as e:
            logger.error(
                f"Error saving task metadata (attempt {attempt+1}/{retry_count}): {e}"
            )
            if attempt == retry_count - 1:
                logger.critical(
                    f"Failed to save task metadata after {retry_count} attempts"
                )
                raise
            import time

            time.sleep(0.5)  # Short delay before retry


@lru_cache(maxsize=128)
def load_task_metadata(task_id: str, bypass_cache: bool = False) -> Optional[Dict]:
    """
    Load task metadata from JSON file.

    Args:
        task_id: Task identifier
        bypass_cache: If True, bypass the cache and load directly from disk

    Returns:
        Dictionary containing metadata or None if file doesn't exist
    """
    # If bypass_cache is True, clear this entry from cache before loading
    if bypass_cache:
        clear_metadata_cache(task_id)

    metadata_file = TASKS_DIR / task_id / "metadata" / "task.json"

    if not metadata_file.exists():
        return None

    retry_count = 3
    for attempt in range(retry_count):
        try:
            with open(metadata_file, "r") as f:
                data = json.load(f)

                # Ensure taskId is set correctly
                if "taskId" not in data:
                    data["taskId"] = task_id

                return data
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON decode error in metadata for task {task_id} (attempt {attempt+1}/{retry_count}): {e}"
            )
            if attempt == retry_count - 1:
                logger.critical(
                    f"Failed to decode task metadata JSON after {retry_count} attempts"
                )
                return None
            import time

            time.sleep(0.5)  # Short delay before retry
        except Exception as e:
            logger.error(f"Failed to load metadata for task {task_id}: {e}")
            return None


def save_base64_image(task_id: str, image_data: str, filename: str) -> Path:
    """
    Decode and save a base64-encoded image.

    Args:
        task_id: Task identifier
        image_data: Base64-encoded image string (may include MIME prefix)
        filename: Original filename

    Returns:
        Path to the saved image
    """
    task_dir = ensure_task_directory(task_id)

    # Handle data URI scheme if present
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    # Decode base64 data
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception as e:
        logger.error(f"Failed to decode base64 image for task {task_id}: {e}")
        raise ValueError(f"Invalid base64 image data: {str(e)}")

    # Save the image to the input directory
    image_path = task_dir / "input" / filename
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    logger.info(f"Saved image for task {task_id} to {image_path}")

    return image_path


def save_output_file(
    task_id: str, file_data: Union[bytes, Image.Image], filename: str, category: str
) -> Dict:
    """
    Save an output file for a task.

    Args:
        task_id: Task identifier
        file_data: File data as bytes or PIL Image
        filename: Filename to save as
        category: Category for organizing files (dithered, rendered, schematic, etc.)

    Returns:
        Dictionary with file information
    """
    task_dir = ensure_task_directory(task_id)

    # Determine the appropriate subdirectory
    if category not in ["dithered", "rendered", "schematic", "web", "input", "output"]:
        category = "output"  # Default category

    output_dir = task_dir / category
    output_dir.mkdir(exist_ok=True)

    file_path = output_dir / filename

    # Save the file based on its type
    try:
        if isinstance(file_data, Image.Image):
            file_data.save(file_path)
        else:
            with open(file_path, "wb") as f:
                f.write(file_data)
    except Exception as e:
        logger.error(f"Failed to save output file {filename} for task {task_id}: {e}")
        raise

    # Generate file info
    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Create a stable file ID that can be consistently referenced
    file_id = f"{category}_{filename}"

    return {
        "fileId": file_id,
        "filename": filename,
        "path": str(file_path),
        "type": mime_type,
        "size": file_size,
        "category": category,
        "url": f"/api/conversion/{task_id}/files/{file_id}",
    }


def list_task_files(task_id: str, bypass_cache: bool = False) -> List[Dict]:
    """
    List all files associated with a task.

    Args:
        task_id: Task identifier
        bypass_cache: If True, bypass the cache

    Returns:
        List of file info dictionaries
    """
    if bypass_cache:
        list_task_files.cache_clear()

    task_dir = TASKS_DIR / task_id

    if not task_dir.exists():
        return []

    files = []

    # Walk through the task directory and find all files
    for root, _, filenames in os.walk(task_dir):
        root_path = Path(root)
        category = (
            root_path.relative_to(task_dir).parts[0]
            if len(root_path.relative_to(task_dir).parts) > 0
            else "other"
        )

        # Skip metadata directory from file listings
        if category == "metadata":
            continue

        for filename in filenames:
            # Skip hidden files and temporary files
            if filename.startswith(".") or filename.endswith(".tmp"):
                continue

            file_path = root_path / filename

            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"

            file_size = file_path.stat().st_size

            # Create a stable file ID that can be consistently referenced
            file_id = f"{category}_{filename}"

            files.append(
                {
                    "fileId": file_id,
                    "filename": filename,
                    "path": str(file_path),
                    "type": mime_type,
                    "size": file_size,
                    "category": category,
                    "url": f"/api/conversion/{task_id}/files/{file_id}",
                }
            )

    return files


# Cache list_task_files for performance
list_task_files = lru_cache(maxsize=64)(list_task_files)


def get_file_path(task_id: str, file_id: str) -> Optional[Path]:
    """
    Get the file path for a specific file ID.

    Args:
        task_id: Task identifier
        file_id: File identifier

    Returns:
        Path to the file or None if not found
    """
    # First try to parse the file_id format we generate (category_filename)
    if "_" in file_id:
        try:
            category, filename = file_id.split("_", 1)
            file_path = TASKS_DIR / task_id / category / filename
            if file_path.exists():
                return file_path
        except Exception:
            pass

    # Fall back to scanning all files
    files = list_task_files(task_id)
    for file_info in files:
        if file_info["fileId"] == file_id:
            return Path(file_info["path"])

    return None


def clean_old_tasks(max_age_days: int = 7) -> int:
    """
    Remove task directories older than the specified age.

    Args:
        max_age_days: Maximum age in days before a task is removed

    Returns:
        Number of tasks removed
    """
    if not TASKS_DIR.exists():
        return 0

    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    removed_count = 0

    for task_dir in TASKS_DIR.iterdir():
        if not task_dir.is_dir():
            continue

        # Check the metadata for last updated time
        metadata = load_task_metadata(task_dir.name)

        if metadata and "updated" in metadata:
            try:
                updated_time = datetime.fromisoformat(metadata["updated"])
                if updated_time < cutoff_date:
                    shutil.rmtree(task_dir)
                    removed_count += 1
            except (ValueError, TypeError):
                # If we can't parse the date, use file modification time
                mod_time = datetime.fromtimestamp(task_dir.stat().st_mtime)
                if mod_time < cutoff_date:
                    shutil.rmtree(task_dir)
                    removed_count += 1
        else:
            # No metadata or no update time, use file modification time
            mod_time = datetime.fromtimestamp(task_dir.stat().st_mtime)
            if mod_time < cutoff_date:
                shutil.rmtree(task_dir)
                removed_count += 1

    return removed_count


def create_zip_archive(
    task_id: str, file_ids: Optional[List[str]] = None
) -> Optional[Path]:
    """
    Create a ZIP archive of task files.

    Args:
        task_id: Task identifier
        file_ids: List of file IDs to include (None for all files)

    Returns:
        Path to the ZIP file or None if creation failed
    """
    import zipfile
    from tempfile import NamedTemporaryFile

    task_dir = TASKS_DIR / task_id
    if not task_dir.exists():
        return None

    # Get list of files (bypass cache to ensure we get latest files)
    all_files = list_task_files(task_id, bypass_cache=True)

    # Filter files if file_ids is provided
    if file_ids:
        files_to_include = [f for f in all_files if f["fileId"] in file_ids]
    else:
        files_to_include = all_files

    if not files_to_include:
        return None

    # Create temporary file for ZIP
    with NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        zip_path = Path(tmp_file.name)

    # Create ZIP archive
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Group files by category
            files_by_category = {}
            for file_info in files_to_include:
                category = file_info["category"]
                if category not in files_by_category:
                    files_by_category[category] = []
                files_by_category[category].append(file_info)

            # Add files to ZIP with category-based directory structure
            for category, files in files_by_category.items():
                for file_info in files:
                    file_path = Path(file_info["path"])
                    if file_path.exists():
                        # Use category as subdirectory in ZIP
                        archive_path = f"{category}/{file_info['filename']}"
                        zip_file.write(file_path, arcname=archive_path)
    except Exception as e:
        logger.error(f"Failed to create ZIP archive for task {task_id}: {e}")
        if zip_path.exists():
            zip_path.unlink()
        return None

    # Move ZIP to task directory
    try:
        zip_filename = f"pixeletica_task_{task_id}.zip"
        final_zip_path = task_dir / zip_filename
        shutil.move(zip_path, final_zip_path)
        return final_zip_path
    except Exception as e:
        logger.error(f"Failed to move ZIP archive to task directory: {e}")
        if zip_path.exists():
            zip_path.unlink()
        return None
