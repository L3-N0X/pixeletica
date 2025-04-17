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
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union
import time as time

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

    # Only create the root task directory; subfolders are created as needed by export logic
    task_dir.mkdir(parents=True, exist_ok=True)

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
    metadata_file = task_dir / "task.json"  # Save at root

    # Update timestamp
    metadata["updated"] = datetime.now().isoformat()

    # Ensure taskId is set correctly
    if "taskId" not in metadata:
        metadata["taskId"] = task_id

    retry_count = 3
    for attempt in range(retry_count):
        try:
            # Ensure the parent directory exists
            metadata_file.parent.mkdir(parents=True, exist_ok=True)

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
                    # Read the file content first to perform cleanup if needed
                    file_content = f.read()

                    # Try to load the JSON content
                    try:
                        verification_data = json.loads(file_content)
                    except json.JSONDecodeError as jde:
                        logger.warning(f"JSON decode error during verification: {jde}")

                        # Attempt to fix common JSON issues - trailing commas, etc.
                        if "Extra data" in str(jde):
                            # Get position info from the error
                            error_parts = str(jde).split("char ")
                            if len(error_parts) > 1:
                                try:
                                    error_pos = int(error_parts[1])
                                    # Truncate the content at the error position
                                    fixed_content = file_content[:error_pos]

                                    # Find the last closing brace
                                    last_brace_pos = fixed_content.rfind("}")
                                    if last_brace_pos > 0:
                                        clean_content = fixed_content[
                                            : last_brace_pos + 1
                                        ]

                                        # Write the cleaned content back
                                        with open(metadata_file, "w") as fw:
                                            fw.write(clean_content)

                                        # Try to verify again with the cleaned content
                                        verification_data = json.loads(clean_content)
                                        logger.info(
                                            "Successfully fixed and verified metadata JSON"
                                        )
                                except Exception as fix_error:
                                    logger.error(f"Failed to fix JSON: {fix_error}")
                                    return metadata_file
                        else:
                            # For other JSON errors, just return without verification
                            return metadata_file

                    # Check the status matches
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
                f"Error saving task metadata (attempt {attempt + 1}/{retry_count}): {e}"
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

    metadata_file = TASKS_DIR / task_id / "task.json"  # Load from root

    if not metadata_file.exists():
        return None

    retry_count = 3
    for attempt in range(retry_count):
        try:
            with open(metadata_file, "r") as f:
                # Read the file content first
                file_content = f.read()

                try:
                    # Try to parse the JSON normally
                    data = json.loads(file_content)
                except json.JSONDecodeError as jde:
                    logger.error(
                        f"JSON decode error in metadata for task {task_id} (attempt {attempt + 1}/{retry_count}): {jde}"
                    )

                    # Try to fix the JSON if we encounter common issues
                    if "Extra data" in str(jde):
                        # Get position info from the error
                        error_parts = str(jde).split("char ")
                        if len(error_parts) > 1:
                            try:
                                error_pos = int(error_parts[1])
                                # Truncate the content at the error position
                                fixed_content = file_content[:error_pos]

                                # Find the last closing brace
                                last_brace_pos = fixed_content.rfind("}")
                                if last_brace_pos > 0:
                                    clean_content = fixed_content[: last_brace_pos + 1]

                                    # Try to parse the cleaned content
                                    data = json.loads(clean_content)

                                    # Write the cleaned content back
                                    with open(metadata_file, "w") as fw:
                                        fw.write(clean_content)

                                    logger.info(
                                        f"Successfully fixed JSON for task {task_id}"
                                    )
                            except Exception as fix_error:
                                logger.error(
                                    f"Failed to fix JSON for task {task_id}: {fix_error}"
                                )
                                if attempt == retry_count - 1:
                                    return None
                                time.sleep(0.5)
                                continue
                    else:
                        # For other JSON errors, try again next attempt
                        if attempt == retry_count - 1:
                            logger.critical(
                                f"Failed to decode task metadata JSON after {retry_count} attempts"
                            )
                            return None
                        import time

                        time.sleep(0.5)  # Short delay before retry
                        continue

                # Ensure taskId is set correctly
                if "taskId" not in data:
                    data["taskId"] = task_id

                return data
        except Exception as e:
            logger.error(f"Failed to load metadata for task {task_id}: {e}")
            if attempt == retry_count - 1:
                return None
            import time

            time.sleep(0.5)  # Short delay before retry


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

    # Create input directory
    input_dir = task_dir / "input"
    input_dir.mkdir(exist_ok=True)

    # Handle data URI scheme if present
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    # Decode base64 data
    try:
        image_bytes = base64.b64decode(image_data)
    except Exception as e:
        logger.error(f"Failed to decode base64 image for task {task_id}: {e}")
        raise ValueError(f"Invalid base64 image data: {str(e)}")

    # Ensure filename starts with input_ prefix for consistency
    if not filename.startswith("input_"):
        filename = f"input_{filename}"

    # Define the image path within the input directory
    image_path = input_dir / filename

    # Save the image
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

    # Create subdirectories for all valid categories
    if category in [
        "rendered",
        "web",
        "dithered",
        "schematic",
        "input",
        "task_zip",
        "split",
    ]:
        output_dir = task_dir / category
        output_dir.mkdir(exist_ok=True)
        file_path = output_dir / filename
    else:
        # Assign a valid category if an invalid one was passed
        logger.warning(
            f"Invalid category '{category}' for file {filename}, defaulting to 'input'"
        )
        category = "input"
        output_dir = task_dir / category
        output_dir.mkdir(exist_ok=True)
        file_path = output_dir / filename

    # Ensure split files use the _split<num> pattern consistently
    if category == "rendered" and "_1" in filename and "_split" not in filename:
        import re

        split_match = re.search(r"_(\d+)\.png$", filename)
        if split_match:
            split_num = split_match.group(1)
            new_filename = filename.replace(
                f"_{split_num}.png", f"_split{split_num}.png"
            )
            file_path = output_dir / new_filename
            filename = new_filename

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
    # Make sure we use the right prefix for the file ID based on category
    if category == "rendered":
        file_id = f"rendered_{filename}"
    elif category == "schematic":
        file_id = f"schematic_{filename}"
    elif category == "dithered":
        file_id = f"dithered_{filename}"
    elif category == "input":
        file_id = f"input_{filename}"
    elif category == "task_zip":
        file_id = f"task_zip_{filename}"
    else:
        file_id = f"{category}_{filename}"

    return {
        "fileId": file_id,
        "filename": filename,
        "path": str(file_path),
        "type": mime_type,
        "size": file_size,
        "category": category,  # Keep category for internal use, will be removed in API response
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
        rel_parts = root_path.relative_to(task_dir).parts

        # Determine initial category based on directory location
        if len(rel_parts) == 0:
            # Files in root directory - need to be categorized by filename/type
            base_category = None  # Will be determined based on filename
        elif rel_parts[0] in [
            "rendered",
            "web",
            "dithered",
            "schematic",
            "input",
            "task_zip",
            "split",
        ]:
            base_category = rel_parts[0]
        else:
            # Skip forbidden subfolders
            continue

        for filename in filenames:
            # Skip hidden files and temporary files
            if filename.startswith(".") or filename.endswith(".tmp"):
                continue

            # Skip the generated ZIP files used for downloads to avoid duplicates in the listing
            if filename == f"pixeletica_task_{task_id}.zip":
                continue

            file_path = root_path / filename

            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "application/octet-stream"

            file_size = file_path.stat().st_size

            # Determine the appropriate category for the file
            if base_category:
                # Use the directory-based category if available
                category = base_category
            else:
                # Categorize root-level files based on filename and type
                if filename.endswith(".litematic"):
                    category = "schematic"
                elif filename.endswith(".zip"):
                    category = "task_zip"
                elif "__dithered" in filename or "_dithered" in filename:
                    category = "dithered"
                elif "original" in filename or filename.startswith("input_"):
                    category = "input"
                elif any(pattern in filename for pattern in ["__split", "part_"]):
                    category = "split"
                elif "rendered" in filename:
                    category = "rendered"
                elif "web" in filename or filename == "tile-data.json":
                    category = "web"
                else:
                    # Default to input for any remaining files
                    # This ensures all files have a valid category
                    category = "input"

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
    import re

    # Try to parse file_id to get category and filename
    if "_" in file_id:
        try:
            # Handle special case of split files that might have different naming patterns
            split_pattern = re.compile(r"(rendered_.+?)(_split\d+|_\d+)(\.png)$")
            split_match = split_pattern.match(file_id)

            if split_match:
                # Extract components from the split pattern
                base_part = split_match.group(1).replace("rendered_", "")
                split_part = split_match.group(2)
                extension = split_match.group(3)

                # Check if we need to convert old split pattern (_1, _2) to new (_split1, _split2)
                if split_part.startswith("_") and split_part[1:].isdigit():
                    new_split = f"_split{split_part[1:]}"
                    new_filename = f"{base_part}{new_split}{extension}"
                    legacy_filename = f"{base_part}{split_part}{extension}"

                    # Try the new pattern first
                    task_dir = TASKS_DIR / task_id
                    file_path = task_dir / "rendered" / new_filename
                    if file_path.exists():
                        return file_path

                    # Then try the legacy pattern
                    file_path = task_dir / "rendered" / legacy_filename
                    if file_path.exists():
                        return file_path
                else:
                    # Standard split pattern
                    category = "rendered"
                    filename = file_id.replace("rendered_", "")
                    task_dir = TASKS_DIR / task_id
                    file_path = task_dir / category / filename
                    if file_path.exists():
                        return file_path
            else:
                # Standard category and filename extraction
                category, filename = file_id.split("_", 1)
                task_dir = TASKS_DIR / task_id

                # Check subdirectory first
                if category in [
                    "rendered",
                    "web",
                    "dithered",
                    "schematic",
                    "input",
                    "task_zip",
                    "split",
                ]:
                    file_path = task_dir / category / filename
                    if file_path.exists():
                        return file_path

                # Then check root directory as fallback
                file_path = task_dir / filename
                if file_path.exists():
                    return file_path
        except Exception as e:
            logger.warning(f"Error parsing file_id {file_id}: {e}")

    # Fall back to scanning all files
    files = list_task_files(task_id)
    for file_info in files:
        if file_info["fileId"] == file_id:
            return Path(file_info["path"])
        # Try alternate file ID format for backward compatibility
        elif file_id.startswith("rendered_"):
            # Check if this is a split file with old naming format
            old_split_pattern = re.compile(r"rendered_(.+?)_(\d+)\.png$")
            old_match = old_split_pattern.match(file_id)
            new_split_pattern = re.compile(r"rendered_(.+?)_split(\d+)\.png$")
            new_match = new_split_pattern.match(file_info["fileId"])

            # Compare the base part and split number regardless of naming format
            if (
                old_match
                and new_match
                and old_match.group(1) == new_match.group(1)
                and old_match.group(2) == new_match.group(2)
            ):
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

    # Move ZIP to the root of the task directory
    try:
        zip_filename = f"pixeletica_task_{task_id}.zip"
        final_zip_path = task_dir / zip_filename
        shutil.move(zip_path, final_zip_path)

        # Log that the ZIP is now in the root directory
        logger.info(f"Created ZIP archive at {final_zip_path} (root of task dir)")
        return final_zip_path
    except Exception as e:
        logger.error(f"Failed to move ZIP archive to task directory: {e}")
        if zip_path.exists():
            zip_path.unlink()
        return None
