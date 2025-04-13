"""
API route handlers for image conversion operations.

This module defines the FastAPI endpoints for:
- Starting a conversion task
- Checking conversion status
- Listing available files
- Downloading files
"""

import base64
import mimetypes
import asyncio
import io
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
    Query,
)
from fastapi.responses import FileResponse, StreamingResponse
from fastapi_limiter.depends import RateLimiter

from src.pixeletica.api.config import (
    MAX_FILE_SIZE,
    PREVIEW_CONVERSION_TIMEOUT,
)  # Import from config
from src.pixeletica.api.models import (
    FileListResponse,
    SelectiveDownloadRequest,
    TaskResponse,
    DitherAlgorithm,
)
from src.pixeletica.api.services import storage, task_queue
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.image_ops import resize_image
from PIL import Image
import numpy as np
import time
import logging

# Set up logging
logger = logging.getLogger("pixeletica.api.routes.conversion")

# Initialize router
router = APIRouter(prefix="/conversion", tags=["conversion"])


async def validate_file_size(file: UploadFile = File(...)):
    # Ensure the file size check uses the imported constant
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size {file.size} bytes exceeds limit of {MAX_FILE_SIZE} bytes.",
        )
    # Reset stream position after size check if needed, depending on subsequent reads
    await file.seek(0)
    return file


async def apply_dithering_with_timeout(
    width: int, height: int, algorithm: DitherAlgorithm
):
    """
    Create a blank image and apply dithering with timeout.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        algorithm: Dithering algorithm to use

    Returns:
        PIL Image with dithering applied

    Raises:
        asyncio.TimeoutError: If processing exceeds the timeout
        ValueError: If algorithm is not found
    """
    start_time = time.time()

    # Check if dimensions are reasonable
    pixel_count = width * height
    if pixel_count > 1000000:  # 1 million pixels (e.g., 1000x1000)
        logger.warning(
            f"Large preview image requested: {width}x{height} = {pixel_count} pixels"
        )

    # Create a blank white image
    image = Image.new("RGB", (width, height), color="white")

    # Get the dithering algorithm function
    dither_func, _ = get_algorithm_by_name(algorithm.value)
    if not dither_func:
        raise ValueError(f"Unknown dithering algorithm: {algorithm}")

    # Apply dithering with timeout
    result_img = None
    block_ids = None

    # Define the processing function
    async def process_image():
        nonlocal result_img, block_ids
        # Run dithering in a separate thread to not block the event loop
        loop = asyncio.get_event_loop()
        result_img, block_ids = await loop.run_in_executor(None, dither_func, image)

    # Run with timeout
    await asyncio.wait_for(process_image(), timeout=PREVIEW_CONVERSION_TIMEOUT)

    processing_time = time.time() - start_time
    logger.info(
        f"Preview generation took {processing_time:.2f} seconds for {width}x{height} image"
    )

    return result_img


# Note: The /preview endpoint must be defined BEFORE any /{param} routes
# to avoid routing conflicts in FastAPI
@router.get(
    "/preview",
    summary="Generate Quick Preview Image",
    description="Creates a preview of an image with the specified dimensions and dithering algorithm. "
    "Returns the result directly as a PNG image. Has a built-in timeout mechanism for large images.",
    response_description="PNG image with the dithering algorithm applied",
    responses={
        200: {
            "description": "Converted image with dithering applied",
            "content": {"image/png": {}},
        },
        400: {
            "description": "Bad Request - Invalid dimensions or algorithm",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Image dimensions too large for preview. Please reduce width and/or height."
                    }
                }
            },
        },
        408: {
            "description": "Request Timeout - Processing took too long (large image)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Preview generation timed out after 3 seconds. Image may be too large for preview."
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {"example": {"detail": "Error generating preview"}}
            },
        },
    },
    tags=["conversion"],
)
async def get_preview_conversion(
    width: int = Query(..., gt=0, description="Image width in pixels"),
    height: int = Query(..., gt=0, description="Image height in pixels (minimum: 1)"),
    algorithm: DitherAlgorithm = Query(
        DitherAlgorithm.FLOYD_STEINBERG,
        description="Dithering algorithm to apply (floyd_steinberg, ordered, or random)",
    ),
):
    """
    Generate a quick preview of a converted image with specified dimensions and dithering.

    This endpoint creates a blank image with the specified dimensions, applies the selected
    dithering algorithm, and returns the result directly. For large images, there's a timeout
    to abort processing if it takes too long.

    - Required: width, height
    - Optional: algorithm (default: floyd_steinberg)

    Returns the converted image directly as PNG.

    Raises:
        HTTPException(400): If the dimensions are too large or algorithm is invalid
        HTTPException(408): If the conversion process times out
        HTTPException(500): If there's an internal server error
    """
    try:
        # Check if dimensions are reasonable (additional to the validation in the helper function)
        pixel_count = width * height
        if pixel_count > 10000000:  # 10 million pixels (e.g., 3162x3162)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image dimensions too large for preview. Please reduce width and/or height.",
            )

        # Apply dithering with timeout
        try:
            result_img = await apply_dithering_with_timeout(width, height, algorithm)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail=f"Preview generation timed out after {PREVIEW_CONVERSION_TIMEOUT} seconds. Image may be too large for preview.",
            )

        # Convert the image to bytes
        img_byte_arr = io.BytesIO()
        result_img.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        # Return the image
        return StreamingResponse(
            content=img_byte_arr,
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=preview.png"},
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error generating preview: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating preview: {str(e)}",
        )


@router.post(
    "/start",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=5, minutes=1))],
)
async def start_conversion(
    image_file: UploadFile = File(...),
    dithering_algorithm: str = Form("floyd-steinberg"),
    color_palette: str = Form("minecraft"),
    output_format: str = Form("png"),
    x_orientation: str = Form("x"),
    z_orientation: str = Form("z"),
    y_is_height: bool = Form(True),
    scale: int = Form(1),
    split_x: int = Form(1),
    split_z: int = Form(1),
) -> TaskResponse:
    """
    Start a new image conversion task.

    This endpoint accepts an image and configuration parameters,
    creates a new task, and returns a task ID for status tracking.
    """
    # Check file size
    if image_file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds maximum limit of {MAX_FILE_SIZE / (1024 * 1024)}MB",
        )

    # Read image data
    image_data = await image_file.read()
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No image data provided"
        )

    # Decode image data
    try:
        image_data_b64 = base64.b64encode(image_data).decode("utf-8")
        # Basic check to ensure the decoded data is valid base64
        base64.b64decode(image_data_b64)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image data: {str(e)}",
        )

    # Prepare request data
    request_data = {
        "dithering_algorithm": dithering_algorithm,
        "color_palette": color_palette,
        "output_format": output_format,
        "x_orientation": x_orientation,
        "z_orientation": z_orientation,
        "y_is_height": y_is_height,
        "scale": scale,
        "split_x": split_x,
        "split_z": split_z,
        "image": image_data_b64,
        "filename": image_file.filename,
    }

    # Create the task
    try:
        task_id = task_queue.create_task(request_data)
        task_status = task_queue.get_task_status(task_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating conversion task: {str(e)}",
        )

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversion task",
        )

    return TaskResponse(
        taskId=task_id,
        status=task_status["status"],
        progress=task_status.get("progress"),
        timestamp=task_status.get("updated"),
        error=task_status.get("error"),
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_conversion_status(task_id: str) -> TaskResponse:
    """
    Check the status of a conversion task.

    Returns the current status, progress, and any error information.
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    return TaskResponse(
        taskId=task_id,
        status=task_status["status"],
        progress=task_status.get("progress"),
        timestamp=task_status.get("updated"),
        error=task_status.get("error"),
    )


@router.get("/{task_id}/files", response_model=FileListResponse)
async def list_files(task_id: str, category: Optional[str] = None) -> FileListResponse:
    """
    List files generated for a task.

    Optionally filter by category (dithered, rendered, schematic, web).
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Get list of files
    files = storage.list_task_files(task_id)

    # Filter by category if specified
    if category:
        files = [f for f in files if f["category"] == category]

    # Remove file path from response for security
    for file in files:
        if "path" in file:
            del file["path"]

    return FileListResponse(taskId=task_id, files=files)


@router.get("/{task_id}/files/{file_id}")
async def download_file(task_id: str, file_id: str):
    """
    Download a specific file from a conversion task.

    Returns the file for direct download.
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Get file path
    file_path = storage.get_file_path(task_id, file_id)

    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_id}"
        )

    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = "application/octet-stream"

    # Return file for download
    return FileResponse(
        path=file_path, media_type=content_type, filename=file_path.name
    )


@router.get("/{task_id}/download")
async def download_all_files(task_id: str):
    """
    Download all files from a conversion task as a ZIP archive.
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Create ZIP archive
    zip_path = storage.create_zip_archive(task_id)

    if not zip_path or not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ZIP archive",
        )

    # Return ZIP file for download
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"pixeletica_task_{task_id}.zip",
    )


@router.post("/{task_id}/download")
async def download_selected_files(task_id: str, request: SelectiveDownloadRequest):
    """
    Download selected files from a conversion task as a ZIP archive.

    Specify file IDs to include in the download.
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Create ZIP archive with selected files
    zip_path = storage.create_zip_archive(task_id, request.fileIds)

    if not zip_path or not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ZIP archive",
        )

    # Return ZIP file for download
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"pixeletica_task_{task_id}_selected.zip",
    )


@router.delete("/{task_id}")
async def delete_task(task_id: str, background_tasks: BackgroundTasks):
    """
    Delete a conversion task and all associated files.
    """
    task_status = task_queue.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Delete task files in background to avoid blocking the response
    def delete_task_files(task_id: str):
        import shutil

        task_dir = storage.TASKS_DIR / task_id
        if task_dir.exists():
            try:
                shutil.rmtree(task_dir)
            except Exception:
                # Log but don't fail if deletion fails
                pass

    background_tasks.add_task(delete_task_files, task_id)

    return {"message": f"Task {task_id} deletion initiated", "success": True}
