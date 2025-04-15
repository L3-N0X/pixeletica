"""
API route handlers for map-related operations.

This module defines the FastAPI endpoints for:
- Listing available maps
- Getting map metadata
- Fetching map images and tiles
"""

import json
import logging
import os
from datetime import datetime
from io import BytesIO

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from src.pixeletica.api.models import MapInfo, MapListResponse
from src.pixeletica.api.services import storage


async def get_redis() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_instance = redis.from_url(redis_url)
        await redis_instance.ping()
        return redis_instance
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


# Set up logging
logger = logging.getLogger("pixeletica.api.routes.maps")

# Get CORS settings from environment variable or use default
cors_origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:5000")
cors_origins = cors_origins_str.split(",") if cors_origins_str != "*" else ["*"]

# Initialize router with appropriate prefix
router = APIRouter(prefix="/api", tags=["maps"])


@router.get(
    "/maps.json",
    response_model=MapListResponse,
    responses={
        200: {
            "description": "List of available maps",
            "content": {
                "application/json": {
                    "example": {
                        "maps": [
                            {
                                "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "name": "Castle Blueprint",
                                "created": "2024-04-13T21:30:00.000Z",
                                "thumbnail": "/api/map/d290f1ee-6c54-4b01-90e6-d701748f0851/thumbnail.png",
                                "description": "Medieval castle design converted to blocks",
                            },
                            {
                                "id": "7289d334-9a01-45cf-b5cc-8d887c4e9cc2",
                                "name": "Pixel Art Logo",
                                "created": "2024-04-13T20:15:00.000Z",
                                "thumbnail": "/api/map/7289d334-9a01-45cf-b5cc-8d887c4e9cc2/thumbnail.png",
                                "description": "Company logo converted to minecraft blocks",
                            },
                        ]
                    }
                }
            },
        }
    },
)
async def list_maps() -> MapListResponse:
    """
    List all available maps (completed conversion tasks).

    Returns:
        List of all maps that have completed processing and have web exports
    """
    # Get list of tasks that are completed and have web exports
    tasks_dir = storage.TASKS_DIR
    maps = []

    if tasks_dir.exists():
        for task_id in os.listdir(tasks_dir):
            task_dir = tasks_dir / task_id
            if not task_dir.is_dir():
                continue

            # Check if task is completed and has web exports
            metadata = storage.load_task_metadata(task_id)
            web_dir = task_dir / "web"

            if (
                metadata
                and metadata.get("status") == "completed"
                and web_dir.exists()
                and (web_dir / "metadata.json").exists()
            ):

                # Get dimensions from web metadata.json if available
                width = None
                height = None
                web_metadata_path = web_dir / "metadata.json"
                if web_metadata_path.exists():
                    try:
                        with open(web_metadata_path, "r") as f:
                            web_metadata = json.load(f)
                            width = web_metadata.get("width")
                            height = web_metadata.get("height")
                    except Exception as e:
                        logger.error(
                            f"Failed to read web metadata for task {task_id}: {e}"
                        )

                # Create map info
                map_info = MapInfo(
                    id=task_id,
                    name=metadata.get("name", f"Map {task_id[:6]}"),
                    created=datetime.fromisoformat(metadata.get("updated")),
                    thumbnail=f"/api/map/{task_id}/thumbnail.png",
                    description=metadata.get("description"),
                    width=width,
                    height=height,
                )
                maps.append(map_info)

    return MapListResponse(maps=maps)


@router.get(
    "/map/{map_id}/metadata.json",
    responses={
        200: {
            "description": "Map metadata",
            "content": {
                "application/json": {
                    "example": {
                        "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "name": "Castle Blueprint",
                        "width": 1920,
                        "height": 1080,
                        "origin_x": 0,
                        "origin_z": 0,
                        "created": "2024-04-13T21:30:00.000Z",
                        "tileSize": 256,
                        "maxZoom": 4,
                        "minZoom": 0,
                        "tileFormat": "png",
                        "description": "Medieval castle design converted to blocks",
                    }
                }
            },
        },
        404: {
            "description": "Map not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Map not found: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
    },
)
async def get_map_metadata(map_id: str):
    """
    Get detailed metadata for a specific map.

    Args:
        map_id: Map identifier (task ID)

    Returns:
        JSON metadata for the map including tile information
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    metadata_path = task_dir / "web" / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail=f"Map not found: {map_id}")

    # Read the metadata file
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Add the map ID to the metadata
    metadata["id"] = map_id

    # Update tile size to 512 as tiles are always 512x512
    metadata["tileSize"] = 512

    # Get the task metadata for additional information
    task_metadata = storage.load_task_metadata(map_id)
    if task_metadata:
        # Basic map information
        metadata["name"] = task_metadata.get("name", f"Map {map_id[:6]}")
        metadata["created"] = task_metadata.get("updated")
        metadata["description"] = task_metadata.get("description")

        # Add additional metadata from the conversion request
        if "origin_y" not in metadata and "exportSettings" in task_metadata:
            metadata["origin_y"] = task_metadata.get("exportSettings", {}).get(
                "originY", 100
            )

        # Include dithering algorithm and color palette
        metadata["dithering_algorithm"] = task_metadata.get("algorithm")
        metadata["color_palette"] = task_metadata.get("color_palette", "minecraft")

        # Include additional conversion settings that might be useful for the user
        if "line_visibilities" in task_metadata:
            metadata["line_visibilities"] = task_metadata.get("line_visibilities")

        if "image_division" in task_metadata:
            metadata["image_division"] = task_metadata.get("image_division")

        # Include schematic information if available
        if task_metadata.get("schematicSettings", {}).get("generateSchematic", False):
            metadata["schematic"] = {
                "name": task_metadata.get("schematicSettings", {}).get("name"),
                "author": task_metadata.get("schematicSettings", {}).get("author"),
                "description": task_metadata.get("schematicSettings", {}).get(
                    "description"
                ),
            }

    return metadata


# Handle OPTIONS requests for map endpoints
@router.options("/map/{map_id}/metadata.json")
@router.options("/map/{map_id}/full-image.png")
@router.options("/map/{map_id}/thumbnail.png")
@router.options("/map/{map_id}/tiles/{zoom}/{x}/{y}.png")
async def options_map_endpoints():
    """
    Handle OPTIONS requests for map endpoints to support CORS preflight requests.
    """
    from starlette.requests import Request
    from fastapi.responses import Response

    # Get the request origin if available (for CORS handling)
    request = Request(scope={"type": "http"})
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


@router.get("/map/{map_id}/full-image.png")
async def get_map_full_image(map_id: str):
    """
    Get the full image for a map.

    Args:
        map_id: Map identifier (task ID)

    Returns:
        Full-size PNG image of the map
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    full_image_path = task_dir / "web" / "full-image.png"

    if not full_image_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Full image not found for map: {map_id}"
        )

    # Add CORS headers for file responses
    from starlette.requests import Request
    from fastapi import Response

    # Get the request origin if available (for CORS handling)
    request = Request(scope={"type": "http"})
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file responses
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

    return FileResponse(path=full_image_path, media_type="image/png", headers=headers)


@router.get(
    "/map/{map_id}/thumbnail.png",
    responses={
        200: {"description": "Thumbnail image", "content": {"image/png": {}}},
        404: {
            "description": "Map not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Image not found for map: d290f1ee-6c54-4b01-90e6-d701748f0851"
                    }
                }
            },
        },
    },
)
async def get_map_thumbnail(map_id: str):
    """
    Get a thumbnail for a map.

    Args:
        map_id: Map identifier (task ID)

    Returns:
        Thumbnail PNG image of the map
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    full_image_path = task_dir / "web" / "full-image.png"

    if not full_image_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Image not found for map: {map_id}"
        )

    # Create a thumbnail if it doesn't exist
    thumbnail_path = task_dir / "web" / "thumbnail.png"
    if not thumbnail_path.exists():
        try:
            from PIL import Image

            img = Image.open(full_image_path)
            img.thumbnail((300, 300))
            img.save(thumbnail_path, "PNG")
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            return FileResponse(path=full_image_path, media_type="image/png")

    # Add CORS headers for file responses
    from starlette.requests import Request

    # Get the request origin if available (for CORS handling)
    request = Request(scope={"type": "http"})
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file responses
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

    return FileResponse(path=thumbnail_path, media_type="image/png", headers=headers)


@router.get(
    "/map/{map_id}/tiles/{zoom}/{x}/{y}.png",
    responses={
        200: {"description": "Map tile image", "content": {"image/png": {}}},
        404: {
            "description": "Tile not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Tile not found: zoom=2, x=3, y=4"}
                }
            },
        },
    },
)
async def get_map_tile(
    map_id: str,
    zoom: int,
    x: int,
    y: int,
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get a specific tile for a map.

    Args:
        map_id: Map identifier (task ID)
        zoom: Zoom level
        x: X-coordinate of the tile
        y: Y-coordinate of the tile

    Returns:
        PNG image of the requested tile
    """
    tile_key = f"map:{map_id}:tile:{zoom}:{x}:{y}"
    cached_tile = await redis_client.get(tile_key)

    if cached_tile:
        # Return cached tile
        return StreamingResponse(BytesIO(cached_tile), media_type="image/png")

    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    tile_path = task_dir / "web" / "tiles" / str(zoom) / str(x) / f"{y}.png"

    if not tile_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Tile not found: zoom={zoom}, x={x}, y={y}"
        )

    # Read the file
    with open(tile_path, "rb") as f:
        tile_data = f.read()

    # Cache the tile
    await redis_client.set(tile_key, tile_data, ex=60 * 60)  # Cache for 1 hour

    # Add CORS headers for file responses
    from starlette.requests import Request

    # Get the request origin if available (for CORS handling)
    request = Request(scope={"type": "http"})
    origin = request.headers.get(
        "origin", cors_origins[0] if cors_origins != ["*"] else "*"
    )

    # Add CORS headers for file responses
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

    # Return the file with CORS headers
    return StreamingResponse(
        BytesIO(tile_data), media_type="image/png", headers=headers
    )
