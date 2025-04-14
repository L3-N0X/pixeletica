"""
Storage service for managing files related to conversion tasks.

This module handles:
- Creating task directories
- Saving uploaded images
- Managing output files
- Providing file information
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
from typing import Dict, List, Optional, Union

from PIL import Image

# Set up logging
logger = logging.getLogger("pixeletica.api.storage")

# Base directory for all task files
TASKS_DIR = Path("/app/out/api_tasks")


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


def save_task_metadata(task_id: str, metadata: Dict, force: bool = False) -> Path:
    """
    Save task metadata to a JSON file.

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
                load_task_metadata.cache_clear()
                logger.info(f"Forced cache clear for task {task_id} metadata")

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
        bypass_cache: If True, bypass the cache and load from disk

    Returns:
        Dictionary containing metadata or None if file doesn't exist
    """
    # If bypass_cache is True, clear this entry from cache before loading
    if bypass_cache:
        # Create a new function that only accepts task_id to match the cache signature
        def clear_single_entry(key):
            load_task_metadata.cache_clear()
            logger.info(f"Cache cleared for task {key} metadata")

        # Clear this specific entry
        clear_single_entry(task_id)

    metadata_file = TASKS_DIR / task_id / "metadata" / "task.json"

    if not metadata_file.exists():
        return None

    retry_count = 3
    for attempt in range(retry_count):
        try:
            with open(metadata_file, "r") as f:
                data = json.load(f)
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
    image_bytes = base64.b64decode(image_data)

    # Save the image to the input directory
    image_path = task_dir / "input" / filename
    with open(image_path, "wb") as f:
        f.write(image_bytes)

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
    if category not in ["dithered", "rendered", "schematic", "web", "input"]:
        category = "output"  # Default category

    output_dir = task_dir / category
    output_dir.mkdir(exist_ok=True)

    file_path = output_dir / filename

    # Save the file based on its type
    if isinstance(file_data, Image.Image):
        file_data.save(file_path)
    else:
        with open(file_path, "wb") as f:
            f.write(file_data)

    # Generate file info
    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    file_id = str(uuid.uuid4())[:8]  # Short UUID for file ID

    return {
        "fileId": file_id,
        "filename": filename,
        "path": str(file_path),
        "type": mime_type,
        "size": file_size,
        "category": category,
    }


@lru_cache(maxsize=128)
def list_task_files(task_id: str) -> List[Dict]:
    """
    List all files associated with a task.

    Args:
        task_id: Task identifier

    Returns:
        List of file info dictionaries
    """
    task_dir = TASKS_DIR / task_id

    if not task_dir.exists():
        return []

    files = []
    file_id_counter = 1

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
            file_path = root_path / filename

            # Skip hidden files
            if filename.startswith("."):
                continue

            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"

            file_size = file_path.stat().st_size

            files.append(
                {
                    "fileId": str(file_id_counter),  # Simple incremental ID
                    "filename": filename,
                    "path": str(file_path),
                    "type": mime_type,
                    "size": file_size,
                    "category": category,
                }
            )

            file_id_counter += 1

    return files


@lru_cache(maxsize=128)
def get_file_path(task_id: str, file_id: str) -> Optional[Path]:
    """
    Get the file path for a specific file ID.

    Args:
        task_id: Task identifier
        file_id: File identifier

    Returns:
        Path to the file or None if not found
    """
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

    # Get list of files
    all_files = list_task_files(task_id)

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

    # Move ZIP to task directory
    zip_filename = f"pixeletica_task_{task_id}.zip"
    final_zip_path = task_dir / zip_filename
    shutil.move(zip_path, final_zip_path)

    return final_zip_path
