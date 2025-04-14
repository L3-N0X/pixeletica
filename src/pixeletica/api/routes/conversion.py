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
from typing import Optional, Dict, Any, List
import json

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
    Body,
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
    LineVisibilityOption,
    ConversionJSONMetadata,
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
    image: Image.Image,
    algorithm: DitherAlgorithm,
    color_palette: str = "minecraft",
):
    """
    Apply dithering to the input image with timeout.

    Args:
        image: PIL Image object to process
        algorithm: Dithering algorithm to use
        color_palette: Color palette to use for block mapping (default: "minecraft")

    Returns:
        PIL Image with dithering applied

    Raises:
        asyncio.TimeoutError: If processing exceeds the timeout
        ValueError: If algorithm is not found
    """
    start_time = time.time()

    # Check if dimensions are reasonable
    width, height = image.size
    pixel_count = width * height
    if pixel_count > 1000000:  # 1 million pixels (e.g., 1000x1000)
        logger.warning(
            f"Large preview image requested: {width}x{height} = {pixel_count} pixels"
        )

    # Load block colors based on the selected palette
    from src.pixeletica.block_utils.block_loader import load_block_colors

    # Determine the CSV path based on color palette
    if color_palette == "minecraft-2024":
        csv_path = "./src/minecraft/block-colors-2024.csv"
    else:
        # Default to the standard minecraft palette
        csv_path = "./src/minecraft/block-colors-2025.csv"

    # Load the block colors
    if not load_block_colors(csv_path):
        raise ValueError(f"Failed to load block colors from {csv_path}")

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
@router.post(
    "/preview",
    summary="Generate Quick Preview Image",
    description="Creates a preview of an image with the specified dimensions and dithering algorithm. "
    "Accepts an image file upload via multipart form. "
    "Returns the result directly as a PNG image. Has a built-in timeout mechanism for large images.",
    response_description="PNG image with the dithering algorithm applied",
    responses={
        200: {
            "description": "Converted image with dithering applied",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}}
            },
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
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "image_file": {
                                "type": "string",
                                "format": "binary",
                                "description": "Image file to preview (optional - if not provided, a blank image will be used)",
                            },
                            "width": {
                                "type": "integer",
                                "description": "Image width in pixels",
                            },
                            "height": {
                                "type": "integer",
                                "description": "Image height in pixels",
                            },
                            "algorithm": {
                                "type": "string",
                                "enum": ["floyd_steinberg", "ordered", "random"],
                                "description": "Dithering algorithm to apply",
                            },
                            "color_palette": {
                                "type": "string",
                                "enum": ["minecraft", "minecraft-2024"],
                                "description": "Color palette to use for block mapping",
                            },
                        },
                        "required": ["width", "height"],
                    }
                }
            }
        }
    },
)
async def get_preview_conversion(
    width: int = Form(..., gt=0, description="Image width in pixels"),
    height: int = Form(..., gt=0, description="Image height in pixels (minimum: 1)"),
    algorithm: DitherAlgorithm = Form(
        DitherAlgorithm.FLOYD_STEINBERG,
        description="Dithering algorithm to apply (floyd_steinberg, ordered, or random)",
    ),
    color_palette: str = Form(
        "minecraft",
        description="Color palette to use for block mapping (default: minecraft)",
    ),
    image_file: Optional[UploadFile] = File(
        None, description="Image file to preview (optional)"
    ),
):
    """
    Generate a quick preview of a converted image with specified dimensions and dithering.

    This endpoint accepts an image file via multipart form along with conversion parameters.
    If no image is provided, it creates a blank white image with the specified dimensions.
    It applies the selected dithering algorithm and returns the result directly.
    For large images, there's a timeout to abort processing if it takes too long.

    - Required: width, height
    - Optional: image_file, algorithm (default: floyd_steinberg)

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

        # Create the base image (blank or from uploaded file)
        if image_file:
            # Read the uploaded image
            image_data = await image_file.read()
            try:
                image = Image.open(io.BytesIO(image_data))
                # Resize to requested dimensions
                image = resize_image(image, width, height)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid image file: {str(e)}",
                )
        else:
            # Create a blank white image
            image = Image.new("RGB", (width, height), color="white")

        # Apply dithering with timeout
        try:
            result_img = await apply_dithering_with_timeout(
                image, algorithm, color_palette
            )
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
    responses={
        202: {
            "description": "Task created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "status": "queued",
                        "progress": 0,
                        "timestamp": "2024-04-13T21:30:00.000Z",
                        "error": None,
                    }
                }
            },
        },
        400: {
            "description": "Bad Request - Invalid JSON metadata",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid JSON metadata format"}
                }
            },
        },
        413: {
            "description": "File too large",
            "content": {
                "application/json": {
                    "example": {"detail": "Image size exceeds maximum limit of 10MB"}
                }
            },
        },
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "image_file": {
                                "type": "string",
                                "format": "binary",
                                "description": "Image file to convert",
                            },
                            "metadata": {
                                "type": "string",
                                "example": json.dumps(
                                    {
                                        "width": 128,
                                        "height": 128,
                                        "dithering_algorithm": "floyd_steinberg",
                                        "color_palette": "minecraft",
                                        "origin_x": 0,
                                        "origin_y": 100,
                                        "origin_z": 0,
                                        "chunk_line_color": "#FF0000FF",
                                        "block_line_color": "#000000FF",
                                        "line_visibilities": ["chunk_lines_only"],
                                        "image_division": 2,
                                        "generate_schematic": True,
                                        "schematic_name": "my_schematic",
                                        "schematic_author": "Pixeletica API",
                                        "schematic_description": "An awesome schematic",
                                        "generate_web_files": True,
                                    },
                                    indent=2,
                                ),
                                "description": "JSON string containing all metadata for the conversion task",
                            },
                        },
                        "required": ["image_file", "metadata"],
                    }
                }
            }
        }
    },
)
async def start_conversion(
    image_file: UploadFile = File(..., description="Image file to convert"),
    metadata: str = Form(
        ..., description="JSON string containing all metadata for the conversion task"
    ),
) -> TaskResponse:
    """
    Start a new image conversion task using REST-standard multipart form data.

    This endpoint accepts:
    - An image file in the 'image_file' field
    - A JSON string in the 'metadata' field containing all configuration parameters

    The metadata JSON should follow the schema of the ConversionJSONMetadata model.

    Example metadata JSON:
    ```json
    {
      "width": 128,
      "height": 128,
      "dithering_algorithm": "floyd_steinberg",
      "color_palette": "minecraft",
      "origin_x": 0,
      "origin_y": 100,
      "origin_z": 0,
      "chunk_line_color": "#FF0000FF",
      "block_line_color": "#000000FF",
      "line_visibilities": ["chunk_lines_only"],
      "image_division": 2,
      "generate_schematic": true,
      "schematic_name": "my_schematic",
      "schematic_author": "Pixeletica API",
      "schematic_description": "An awesome schematic",
      "generate_web_files": true
    }
    ```

    Returns a task ID for status tracking.
    """
    # Parse the metadata JSON
    try:
        metadata_json = json.loads(metadata)
        metadata_model = ConversionJSONMetadata(**metadata_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON metadata format. Must be a valid JSON string.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error parsing metadata: {str(e)}",
        )
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

    # Prepare task data dictionary from the metadata model
    task_data: Dict[str, Any] = metadata_model.dict()

    # Add image data
    task_data["image"] = image_data_b64
    task_data["filename"] = image_file.filename

    # Ensure enum values are strings for task queue
    task_data["dithering_algorithm"] = metadata_model.dithering_algorithm.value

    # Convert line visibility options to string values
    task_data["line_visibilities"] = [
        option.value for option in metadata_model.line_visibilities
    ]

    # Define export types constants
    EXPORT_TYPE_WEB = "web"
    EXPORT_TYPE_LARGE = "large"
    EXPORT_TYPE_SPLIT = "split"

    # Set export types with web files always included
    task_data["export_types"] = [EXPORT_TYPE_WEB]
    # We always want large exports for different line visibilities
    task_data["export_types"].append(EXPORT_TYPE_LARGE)
    # Add split export if requested
    if task_data.get("image_division", 1) > 1:
        task_data["export_types"].append(EXPORT_TYPE_SPLIT)

    # Set version options for the line visibility configuration
    task_data["version_options"] = {
        "no_lines": LineVisibilityOption.NO_LINES in metadata_model.line_visibilities,
        "only_block_lines": LineVisibilityOption.BLOCK_GRID_ONLY
        in metadata_model.line_visibilities,
        "only_chunk_lines": LineVisibilityOption.CHUNK_LINES_ONLY
        in metadata_model.line_visibilities,
        "both_lines": LineVisibilityOption.BOTH in metadata_model.line_visibilities,
    }

    # Remove fields not directly needed by the worker task if any,
    # or map them as required by the task processing logic.
    # For now, we pass the whole model dump plus image/filename.

    # Log the task data for debugging purposes
    logger.info(f"Creating task with the following parameters:")
    for key, value in task_data.items():
        if key != "image":  # Skip logging the image data as it's too large
            logger.info(f"  {key}: {value}")

    # Create the task
    try:
        task_id = task_queue.create_task(task_data)  # Pass the prepared dict
        logger.info(f"Task created with ID: {task_id}")
        task_status = task_queue.get_task_status(task_id)
        logger.info(f"Initial task status: {task_status}")
    except Exception as e:
        logger.error(f"Error creating conversion task: {e}", exc_info=True)
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


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        200: {
            "description": "Task status retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "processing": {
                            "value": {
                                "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "status": "processing",
                                "progress": 45,
                                "timestamp": "2024-04-13T21:30:00.000Z",
                                "error": None,
                            }
                        },
                        "completed": {
                            "value": {
                                "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "status": "completed",
                                "progress": 100,
                                "timestamp": "2024-04-13T21:31:00.000Z",
                                "error": None,
                            }
                        },
                        "failed": {
                            "value": {
                                "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "status": "failed",
                                "progress": None,
                                "timestamp": "2024-04-13T21:30:30.000Z",
                                "error": "Failed to process image: Invalid format",
                            }
                        },
                    }
                }
            },
        },
        404: {
            "description": "Task not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
    },
)
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


@router.get(
    "/{task_id}/files",
    response_model=FileListResponse,
    responses={
        200: {
            "description": "List of files for the task",
            "content": {
                "application/json": {
                    "example": {
                        "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "files": [
                            {
                                "fileId": "dithered_image",
                                "filename": "dithered.png",
                                "type": "image/png",
                                "size": 1024567,
                                "category": "dithered",
                            },
                            {
                                "fileId": "rendered_image",
                                "filename": "rendered.png",
                                "type": "image/png",
                                "size": 2048123,
                                "category": "rendered",
                            },
                            {
                                "fileId": "schematic",
                                "filename": "build.litematic",
                                "type": "application/octet-stream",
                                "size": 512789,
                                "category": "schematic",
                            },
                        ],
                    }
                }
            },
        },
        404: {
            "description": "Task not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
    },
)
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


@router.get(
    "/{task_id}/files/{file_id}",
    responses={
        200: {
            "description": "File downloaded successfully",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        404: {
            "description": "Task or file not found",
            "content": {
                "application/json": {
                    "example": {"detail": "File not found: example_file_id"}
                }
            },
        },
    },
    summary="Download a specific file",
    operation_id="downloadFile",
)
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


@router.get(
    "/{task_id}/download",
    responses={
        200: {
            "description": "ZIP file with all task files",
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            },
        },
        404: {
            "description": "Task not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
        500: {
            "description": "Failed to create ZIP archive",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to create ZIP archive"}
                }
            },
        },
    },
    summary="Download all task files",
    operation_id="downloadAllFiles",
)
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


@router.post(
    "/{task_id}/download",
    responses={
        200: {
            "description": "ZIP file with selected task files",
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            },
        },
        404: {
            "description": "Task not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
        500: {
            "description": "Failed to create ZIP archive",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to create ZIP archive"}
                }
            },
        },
    },
    summary="Download selected task files",
    operation_id="downloadSelectedFiles",
)
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


@router.delete(
    "/{task_id}",
    responses={
        200: {
            "description": "Task deletion initiated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Task d290f1ee-6c54-4b01-90e6-d701748f0851 deletion initiated",
                        "success": True,
                    }
                }
            },
        },
        404: {
            "description": "Task not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
    },
)
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
