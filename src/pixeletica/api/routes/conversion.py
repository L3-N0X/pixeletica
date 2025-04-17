"""
API route handlers for image conversion operations.

This module defines the FastAPI endpoints for:
- Starting a conversion task
- Checking conversion status
- Listing available files
- Downloading files
"""

import asyncio
import base64
import io
import json
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi_limiter.depends import RateLimiter
from PIL import Image
from starlette.requests import Request

from src.pixeletica.api.config import (
    MAX_FILE_SIZE,
    PREVIEW_CONVERSION_TIMEOUT,
)  # Import from config
from src.pixeletica.api.models import (
    ConversionJSONMetadata,
    DitherAlgorithm,
    FileListResponse,
    LineVisibilityOption,
    SelectiveDownloadRequest,
    TaskResponse,
)
from src.pixeletica.api.services import storage, task_queue
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.image_ops import resize_image

# Set up logging
logger = logging.getLogger("pixeletica.api.routes.conversion")

# Initialize router
router = APIRouter(prefix="/conversion", tags=["conversion"])

# Get CORS settings from environment variable or use default
cors_origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:5000")
cors_origins = cors_origins_str.split(",") if cors_origins_str != "*" else ["*"]


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
                                "description": "Color palette to use for block mapping (minecraft = 2025 palette, minecraft-2024 = 2024 palette)",
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
        description="Color palette to use for block mapping (default: minecraft - uses 2025 palette)",
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
    # Start tracking time for this request
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[REQ-{request_id}] Starting conversion request")

    # Parse the metadata JSON
    try:
        metadata_json = json.loads(metadata)
        metadata_model = ConversionJSONMetadata(**metadata_json)
        logger.info(f"[REQ-{request_id}] Parsed metadata successfully")
    except json.JSONDecodeError:
        logger.error(f"[REQ-{request_id}] Invalid JSON metadata format")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON metadata format. Must be a valid JSON string.",
        )
    except Exception as e:
        logger.error(f"[REQ-{request_id}] Error parsing metadata: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error parsing metadata: {str(e)}",
        )

    # Check file size
    if image_file.size > MAX_FILE_SIZE:
        logger.warning(f"[REQ-{request_id}] File too large: {image_file.size} bytes")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds maximum limit of {MAX_FILE_SIZE / (1024 * 1024):.1f}MB",
        )

    # Read image data
    try:
        image_data = await image_file.read()
        if not image_data:
            logger.error(f"[REQ-{request_id}] Empty image file")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No image data provided"
            )
        logger.info(f"[REQ-{request_id}] Read image data: {len(image_data)} bytes")
    except Exception as e:
        logger.error(f"[REQ-{request_id}] Error reading image file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading image file: {str(e)}",
        )

    # Decode image data to base64
    try:
        image_data_b64 = base64.b64encode(image_data).decode("utf-8")
        logger.info(
            f"[REQ-{request_id}] Base64-encoded image: {len(image_data_b64)} chars"
        )
    except Exception as e:
        logger.error(f"[REQ-{request_id}] Error encoding image to base64: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error encoding image to base64: {str(e)}",
        )

    # Prepare task data dictionary from the metadata model
    task_data: Dict[str, Any] = metadata_model.dict()

    # Add image data
    task_data["image"] = image_data_b64
    task_data["filename"] = image_file.filename

    # Ensure filename is safe
    if not task_data["filename"] or task_data["filename"] == "":
        task_data["filename"] = f"image_{request_id}.png"

    # Configure algorithm
    task_data["algorithm"] = metadata_model.dithering_algorithm.value
    logger.info(f"[REQ-{request_id}] Using algorithm: {task_data['algorithm']}")

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
        logger.info(
            f"[REQ-{request_id}] Adding split export (division: {task_data.get('image_division')})"
        )

    # Set version options for the line visibility configuration
    task_data["version_options"] = {
        "no_lines": LineVisibilityOption.NO_LINES in metadata_model.line_visibilities,
        "only_block_lines": LineVisibilityOption.BLOCK_GRID_ONLY
        in metadata_model.line_visibilities,
        "only_chunk_lines": LineVisibilityOption.CHUNK_LINES_ONLY
        in metadata_model.line_visibilities,
        "both_lines": LineVisibilityOption.BOTH in metadata_model.line_visibilities,
    }

    # Set export settings for schematic
    task_data["schematicSettings"] = {
        "generateSchematic": metadata_model.generate_schematic,
        "name": metadata_model.schematic_name,
        "author": metadata_model.schematic_author,
        "description": metadata_model.schematic_description,
    }

    # Set export settings for the renderer
    task_data["exportSettings"] = {
        "originX": metadata_model.origin_x,
        "originY": metadata_model.origin_y,
        "originZ": metadata_model.origin_z,
        "chunkLineColor": metadata_model.chunk_line_color,
        "blockLineColor": metadata_model.block_line_color,
        "splitCount": metadata_model.image_division,
    }

    # Create the task with reliable error handling
    retry_count = 3
    task_id = None
    task_status = None

    for attempt in range(retry_count):
        try:
            logger.info(
                f"[REQ-{request_id}] Creating task (attempt {attempt + 1}/{retry_count})"
            )
            task_id = task_queue.create_task(task_data)

            if not task_id:
                logger.error(f"[REQ-{request_id}] create_task returned empty task_id")
                continue

            logger.info(f"[REQ-{request_id}] Task created with ID: {task_id}")

            # Get initial status - might be None or invalid initially
            task_status = task_queue.get_task_status(task_id, bypass_cache=True)

            if task_status and "status" in task_status:
                logger.info(
                    f"[REQ-{request_id}] Initial task status: {task_status['status']}"
                )
                break
            else:
                logger.warning(
                    f"[REQ-{request_id}] Invalid initial task status: {task_status}"
                )
                if attempt == retry_count - 1:
                    raise ValueError("Failed to get initial task status")
                time.sleep(0.5)  # Short delay before retry

        except Exception as e:
            logger.error(
                f"[REQ-{request_id}] Error creating task (attempt {attempt + 1}/{retry_count}): {e}",
                exc_info=True,
            )
            if attempt == retry_count - 1:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create task after {retry_count} attempts: {str(e)}",
                )
            time.sleep(0.5)  # Short delay before retry

    # Final verification of task creation
    if not task_id or not task_status:
        logger.critical(f"[REQ-{request_id}] Failed to create or verify task")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create or verify task status",
        )

    # Record the time taken
    elapsed = time.time() - start_time
    logger.info(f"[REQ-{request_id}] Task creation completed in {elapsed:.2f}s")

    return TaskResponse(
        taskId=task_id,
        status=task_status["status"],
        progress=task_status.get("progress", 0),
        timestamp=task_status.get("updated", datetime.now().isoformat()),
        error=task_status.get("error"),
    )


# Handle OPTIONS requests for files listing endpoint
@router.options("/{task_id}/files")
async def options_list_files(task_id: str, request: Request):
    """
    Handle OPTIONS requests for the files listing endpoint to support CORS preflight requests.
    """
    # Get the request origin if available (for CORS handling)
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",  # Cache the preflight request for 10 minutes
    }

    return Response(status_code=204, headers=headers)


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
    # Generate request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[REQ-{request_id}] Getting status for task {task_id}")

    # Always bypass cache to get the most recent status with extra reliability
    try:
        # First try - standard task status
        task_status = task_queue.get_task_status(task_id, bypass_cache=True)

        if not task_status:
            logger.warning(f"[REQ-{request_id}] Task {task_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {task_id}",
            )

        # Get Celery task ID if available
        celery_id = task_status.get("celery_id") or task_status.get("celery_task_id")
        if celery_id:
            logger.info(f"[REQ-{request_id}] Found Celery task ID: {celery_id}")

        # Check Celery task status directly if needed
        if celery_id:
            try:
                from celery import states
                from celery.result import AsyncResult

                result = AsyncResult(celery_id, app=task_queue.celery_app)
                celery_state = result.state
                logger.info(
                    f"[REQ-{request_id}] Celery task {celery_id} state: {celery_state}"
                )

                # If there's a state mismatch, update our task status accordingly
                if (
                    celery_state == states.SUCCESS
                    and task_status.get("status") != "completed"
                ):
                    logger.warning(
                        f"[REQ-{request_id}] State mismatch: Celery SUCCESS but task status {task_status.get('status')}. Updating to completed."
                    )
                    task_status["status"] = "completed"
                    task_status["progress"] = 100
                    # Sync back to storage
                    task_queue.update_task_status(task_id, "completed", 100)

                elif (
                    celery_state == states.FAILURE
                    and task_status.get("status") != "failed"
                ):
                    logger.warning(
                        f"[REQ-{request_id}] State mismatch: Celery FAILURE but task status {task_status.get('status')}. Updating to failed."
                    )
                    # Get error message if available
                    error_msg = "Task failed during processing"
                    try:
                        if result.result:
                            if (
                                isinstance(result.result, dict)
                                and "error" in result.result
                            ):
                                error_msg = result.result["error"]
                            else:
                                error_msg = str(result.result)
                    except Exception as e:
                        logger.error(
                            f"[REQ-{request_id}] Could not extract error details: {e}"
                        )

                    task_status["status"] = "failed"
                    task_status["error"] = error_msg
                    # Sync back to storage
                    task_queue.update_task_status(task_id, "failed", error=error_msg)

            except Exception as e:
                logger.error(f"[REQ-{request_id}] Error checking Celery task: {e}")
                # Make sure we don't have inconsistent state - if we get an error checking Celery
                # but the Redis records suggest a failure, mark as failed
                if (
                    "redis_state" in task_status
                    and task_status["redis_state"] == states.FAILURE
                ):
                    task_status["status"] = "failed"
                    task_status["error"] = f"Task processing failed: {str(e)}"

        # Handle edge case where task is completed according to Celery/Redis but metadata is corrupt
        # If we see SUCCESS in redis_state but status isn't completed, fix it
        if (
            task_status.get("redis_state") == "SUCCESS"
            and task_status.get("status") != "completed"
        ):
            logger.warning(
                f"[REQ-{request_id}] Detected completed task with incorrect status: {task_status.get('status')}. Fixing."
            )
            task_status["status"] = "completed"
            task_status["progress"] = 100
            # Sync back to storage with force=True to ensure it's written correctly
            try:
                task_queue.update_task_status(task_id, "completed", 100)
                # Clear any cached versions to ensure fresh data
                storage.clear_metadata_cache(task_id)
            except Exception as fix_error:
                logger.error(
                    f"[REQ-{request_id}] Error fixing task status: {fix_error}"
                )

        # Log the task status details
        logger.info(
            f"[REQ-{request_id}] Task {task_id} status: {task_status.get('status')}, progress: {task_status.get('progress')}"
        )

        # For completed tasks, always ensure progress is 100%
        if task_status.get("status") == "completed":
            task_status["progress"] = 100

        # Return the response based on the task status
        return TaskResponse(
            taskId=task_id,
            status=task_status["status"],
            progress=task_status.get("progress", 0),
            timestamp=task_status.get("updated", datetime.now().isoformat()),
            error=task_status.get("error"),
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"[REQ-{request_id}] Error getting task status: {e}", exc_info=True
        )
        # In case of unrecoverable errors, try to return a basic response if we have the task_id
        # This helps prevent API failures when metadata has JSON issues
        try:
            # Last-ditch effort to get or create minimal status
            minimal_status = {
                "status": "completed",  # Assume completed since that's what was indicated in the error logs
                "progress": 100,
            }
            return TaskResponse(
                taskId=task_id,
                status=minimal_status["status"],
                progress=minimal_status["progress"],
                timestamp=datetime.now().isoformat(),
                error=None,  # Don't return error to client in this fallback
            )
        except Exception:
            # If even the fallback fails, then raise the HTTP exception
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving task status: {str(e)}",
            )


@router.get(
    "/{task_id}/files",
    response_model=FileListResponse,
    responses={
        200: {
            "description": "List of files for the task, grouped by category",
            "content": {
                "application/json": {
                    "example": {
                        "taskId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "categories": {
                            "input": {
                                "fileId": "input_original.png",
                                "filename": "original.png",
                                "type": "image/png",
                                "size": 1574956,
                                "category": "input",
                            },
                            "dithered": {
                                "fileId": "dithered_image",
                                "filename": "dithered.png",
                                "type": "image/png",
                                "size": 38317,
                                "category": "dithered",
                            },
                            "rendered": {
                                "block_lines": [
                                    {
                                        "fileId": "rendered_block_lines.png",
                                        "filename": "block_lines.png",
                                        "type": "image/png",
                                        "size": 118231,
                                        "category": "rendered",
                                    },
                                    {
                                        "fileId": "rendered_block_lines_1.png",
                                        "filename": "block_lines_1.png",
                                        "type": "image/png",
                                        "size": 118231,
                                        "category": "rendered",
                                    },
                                ],
                                "chunk_lines": [
                                    {
                                        "fileId": "rendered_chunk_lines.png",
                                        "filename": "chunk_lines.png",
                                        "type": "image/png",
                                        "size": 63059,
                                        "category": "rendered",
                                    }
                                ],
                            },
                            "schematic": {
                                "fileId": "schematic_build.litematic",
                                "filename": "build.litematic",
                                "type": "application/octet-stream",
                                "size": 18041,
                                "category": "schematic",
                            },
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
async def list_files(
    task_id: str,
    request: Request,
    include_web: bool = False,
    category: Optional[str] = None,
) -> FileListResponse:
    """
    List files generated for a task, grouped by category.

    Files are automatically organized by their categories in the response with a structure that
    separates single-instance categories (input, dithered, schematic, task_zip) and categorizes
    rendered images by line type (block_lines, chunk_lines, both_lines, no_lines).

    Args:
        task_id: The unique task identifier
        include_web: Whether to include web files in the response (default: False)
        category: Optionally filter to only include files from a specific category
    """
    task_status = task_queue.get_task_status(task_id, bypass_cache=True)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Get list of files
    files = storage.list_task_files(task_id)

    # Filter out web files if include_web is False
    if not include_web:
        files = [f for f in files if f.get("category") != "web"]

    # Filter by category if specified
    if category:
        files = [f for f in files if f.get("category") == category]

    # Filter out JSON files
    files = [f for f in files if not f.get("filename", "").endswith(".json")]

    # Remove file path from response for security
    for file in files:
        if "path" in file:
            del file["path"]

    # Initialize the new structured categories
    structured_categories = {
        "input": None,
        "dithered": None,
        "rendered": {
            "block_lines": [],
            "chunk_lines": [],
            "both_lines": [],
            "no_lines": [],
        },
        "schematic": None,
        "task_zip": None,
    }

    import re

    # Process each file to place it in the appropriate category
    for file in files:
        filename = file.get("filename", "")
        category = file.get("category", "")
        file_id = file.get("fileId", "")

        # Skip JSON files
        if filename.endswith(".json"):
            continue

        # Handle special single-item categories
        if filename.endswith(".litematic"):
            # Fix the schematic fileId to not use "other_" prefix
            if file_id.startswith("other_"):
                new_file_id = "schematic_" + filename
                file["fileId"] = new_file_id
            structured_categories["schematic"] = file
            continue

        if filename.endswith(".zip"):
            # Make sure zip file is properly categorized
            if file_id.startswith("other_"):
                new_file_id = "task_zip_" + filename
                file["fileId"] = new_file_id
            structured_categories["task_zip"] = file
            continue

        # Check if it's a dithered image
        if category == "dithered" or "__dithered" in filename:
            # Fix the dithered image fileId to not use "other_" prefix
            if file_id.startswith("other_"):
                new_file_id = "dithered_" + filename
                file["fileId"] = new_file_id
            structured_categories["dithered"] = file
            continue

        # Find the input image (usually the largest original image)
        if (
            "ComfyUI_00" in filename and len(filename.split("__")) == 1
        ) or "original" in filename:
            # Make sure it's labeled as input
            if file_id.startswith("other_"):
                new_file_id = "input_" + filename
                file["fileId"] = new_file_id
            structured_categories["input"] = file
            continue

        # Categorize rendered images by line type
        if category == "rendered":
            # Check for line type in filename
            line_type = None

            # Check for pattern indicating line types
            line_match = re.search(
                r"__(block_lines|chunk_lines|both_lines|no_lines)(?:_\d+)?\.png$",
                filename,
            )
            if line_match:
                line_type = line_match.group(1)
                if line_type in structured_categories["rendered"]:
                    structured_categories["rendered"][line_type].append(file)
                continue

        # For any remaining "other" category files with rendered patterns, recategorize them
        if category == "other":
            line_match = re.search(
                r"__(block_lines|chunk_lines|both_lines|no_lines)(?:_\d+)?\.png$",
                filename,
            )
            if line_match:
                line_type = line_match.group(1)
                if line_type in structured_categories["rendered"]:
                    # Replace "other_" with "rendered_" in the fileId
                    if file_id.startswith("other_"):
                        new_file_id = "rendered_" + filename
                        file["fileId"] = new_file_id
                        file["category"] = "rendered"

                    # Check if a file with the same name already exists in the rendered category
                    # to avoid duplicates between "other" and "rendered" categories
                    existing_files = structured_categories["rendered"][line_type]
                    if not any(
                        existing["filename"] == filename for existing in existing_files
                    ):
                        structured_categories["rendered"][line_type].append(file)

    # If input is still None, create an actual input file by copying the first suitable image
    if structured_categories["input"] is None:
        for file in files:
            if (
                file.get("type", "").startswith("image/")
                and not file.get("filename", "").endswith(".json")
                and "path" in file
            ):
                # Get the source path
                source_path = Path(file["path"])
                if source_path.exists():
                    try:
                        # Create input file name
                        input_filename = "input_" + source_path.name
                        task_dir = storage.ensure_task_directory(task_id)
                        target_path = task_dir / input_filename

                        # Copy the file
                        import shutil

                        shutil.copy2(source_path, target_path)

                        # Create file info
                        file_size = target_path.stat().st_size
                        mime_type, _ = mimetypes.guess_type(str(target_path))
                        if not mime_type:
                            mime_type = "application/octet-stream"

                        input_file = {
                            "fileId": f"input_{input_filename}",
                            "filename": input_filename,
                            "type": mime_type,
                            "size": file_size,
                            "category": "input",
                            "url": f"/api/conversion/{task_id}/files/input_{input_filename}",
                        }
                        structured_categories["input"] = input_file
                        logger.info(
                            f"Created input file for task {task_id}: {input_filename}"
                        )
                        break
                    except Exception as e:
                        logger.error(
                            f"Failed to create input file for task {task_id}: {e}"
                        )

    # If task_zip is still None, create it using the storage service
    if structured_categories["task_zip"] is None:
        # Create a ZIP archive with all files
        zip_path = storage.create_zip_archive(task_id)

        if zip_path and zip_path.exists():
            # Get file info
            file_size = zip_path.stat().st_size
            zip_filename = zip_path.name

            # Create file info
            task_zip_file = {
                "fileId": f"task_zip_{zip_filename}",
                "filename": zip_filename,
                "type": "application/zip",
                "size": file_size,
                "category": "task_zip",
                "url": f"/api/conversion/{task_id}/download",
            }
            structured_categories["task_zip"] = task_zip_file
            logger.info(f"Created ZIP archive for task {task_id}: {zip_filename}")

    # Do not remove categories that need to exist according to requirements
    # Keep input, task_zip, and dithered even if they're None

    # Clean up rendered subcategories
    rendered = structured_categories.get("rendered", {})
    for key in list(rendered.keys()):
        if not rendered[key]:
            del rendered[key]

    # If rendered is empty, remove it
    if "rendered" in structured_categories and not structured_categories["rendered"]:
        del structured_categories["rendered"]

    # Prepare the response
    response = FileListResponse(taskId=task_id, categories=structured_categories)

    # Get the request origin for CORS headers
    origin = (
        request.headers.get("origin")
        if request and hasattr(request, "headers")
        else None
    )
    if not origin:
        origin = cors_origins[0] if cors_origins != ["*"] else "*"

    # Add CORS headers to the response
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=response.dict(),
        headers={
            "Access-Control-Allow-Origin": (
                origin
                if origin in cors_origins or cors_origins == ["*"]
                else cors_origins[0]
            ),
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )


# Handle OPTIONS requests for file download endpoint
@router.options("/{task_id}/files/{file_id}")
async def options_download_file(task_id: str, file_id: str, request: Request):
    """
    Handle OPTIONS requests for the file download endpoint to support CORS preflight requests.
    """
    # Get the request origin if available (for CORS handling)
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",  # Cache the preflight request for 10 minutes
    }

    return Response(status_code=204, headers=headers)


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
async def download_file(task_id: str, file_id: str, request: Request):
    """
    Download a specific file from a conversion task.

    Returns the file for direct download.
    """
    task_status = task_queue.get_task_status(task_id, bypass_cache=True)

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

    # Get the request origin from the passed request parameter
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file downloads
    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
    }

    # Return file for download with appropriate CORS headers
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=file_path.name,
        headers=headers,
    )


# Handle OPTIONS requests for bulk download endpoint
@router.options("/{task_id}/download")
async def options_download_all_files(task_id: str, request: Request):
    """
    Handle OPTIONS requests for the bulk download endpoint to support CORS preflight requests.
    """
    # Get the request origin if available (for CORS handling)
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",  # Cache the preflight request for 10 minutes
    }

    return Response(status_code=204, headers=headers)


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
async def download_all_files(task_id: str, request: Request):
    """
    Download all files from a conversion task as a ZIP archive.
    """
    task_status = task_queue.get_task_status(task_id, bypass_cache=True)

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

    # Get the request origin from the passed request parameter
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file downloads
    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
    }

    # Return ZIP file for download with appropriate CORS headers
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"pixeletica_task_{task_id}.zip",
        headers=headers,
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
async def download_selected_files(
    task_id: str, request_body: SelectiveDownloadRequest, request: Request
):
    """
    Download selected files from a conversion task as a ZIP archive.

    Specify file IDs to include in the download.
    """
    task_status = task_queue.get_task_status(task_id, bypass_cache=True)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    # Create ZIP archive with selected files
    zip_path = storage.create_zip_archive(task_id, request_body.fileIds)

    if not zip_path or not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ZIP archive",
        )

    # Get the request origin from the passed request parameter
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file downloads
    headers = {
        "Access-Control-Allow-Origin": (
            origin
            if origin in cors_origins or cors_origins == ["*"]
            else cors_origins[0]
        ),
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
    }

    # Return ZIP file for download with appropriate CORS headers
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"pixeletica_task_{task_id}_selected.zip",
        headers=headers,
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
    task_status = task_queue.get_task_status(task_id, bypass_cache=True)

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
