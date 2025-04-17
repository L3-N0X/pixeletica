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

            # Check if task is completed
            metadata = storage.load_task_metadata(task_id)

            if metadata and metadata.get("status") == "completed":
                # Check for dithered image which is required for thumbnails
                dithered_dir = task_dir / "dithered"
                has_dithered = dithered_dir.exists() and any(dithered_dir.iterdir())

                # Check for existence of web files
                web_dir = task_dir / "web"
                has_web = web_dir.exists()

                # Check for tiles directory
                tiles_dir = web_dir / "tiles"
                has_tiles = tiles_dir.exists() if has_web else False

                # Only include tasks with dithered images or web exports
                if has_dithered or (has_web and has_tiles):
                    # Get dimensions from web metadata or tile-data.json if available
                    width = None
                    height = None

                    # First, try the metadata.json file (previous format)
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

                    # If not found, try tile-data.json (new format)
                    if width is None or height is None:
                        tile_data_path = web_dir / "tile-data.json"
                        if tile_data_path.exists():
                            try:
                                with open(tile_data_path, "r") as f:
                                    tile_data = json.load(f)
                                    width = tile_data.get("width")
                                    height = tile_data.get("height")
                            except Exception as e:
                                logger.error(
                                    f"Failed to read tile-data for task {task_id}: {e}"
                                )

                    # Get the task configuration for additional info
                    config = metadata.get("config", {})
                    if not config and "config" not in metadata:
                        # Old format might store configuration at root level
                        config = metadata

                    # Get or create a name for the map
                    name = metadata.get("name", None)
                    if not name:
                        # Try to get the name from the filename
                        filename = config.get("filename", "")
                        if filename:
                            from pathlib import Path

                            name = Path(filename).stem

                        # Fallback to task ID if no name is found
                        if not name:
                            name = f"Map {task_id[:6]}"

                    # Find first dithered image for thumbnail
                    thumbnail_path = None
                    if has_dithered:
                        for file_path in dithered_dir.glob("*.png"):
                            thumbnail_path = (
                                f"/api/map/{task_id}/dithered/{file_path.name}"
                            )
                            break
                    # Fallback to old thumbnail endpoint if no dithered image
                    if not thumbnail_path:
                        thumbnail_path = f"/api/map/{task_id}/thumbnail.png"

                    # Create map info
                    map_info = MapInfo(
                        id=task_id,
                        name=name,
                        created=datetime.fromisoformat(metadata.get("updated")),
                        thumbnail=thumbnail_path,
                        description=config.get("description", ""),
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

    # Try various metadata file locations
    metadata_path = task_dir / "web" / "metadata.json"
    tile_data_path = task_dir / "web" / "tile-data.json"

    metadata = None

    # First try traditional metadata.json
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
                logger.info(f"Found metadata.json for map {map_id}")
        except Exception as e:
            logger.error(f"Failed to read metadata.json for map {map_id}: {e}")

    # If not found or error, try tile-data.json
    if not metadata and tile_data_path.exists():
        try:
            with open(tile_data_path, "r") as f:
                tile_data = json.load(f)
                logger.info(f"Found tile-data.json for map {map_id}")

                # Convert tile data format to metadata format
                metadata = {
                    "width": tile_data.get("width"),
                    "height": tile_data.get("height"),
                    "origin_x": tile_data.get("origin_x", 0),
                    "origin_z": tile_data.get("origin_z", 0),
                    "tileSize": tile_data.get("tile_size", 512),
                    "tiles_x": tile_data.get("tiles_x", 1),
                    "tiles_z": tile_data.get("tiles_z", 1),
                    "maxZoom": 0,  # Default single zoom level
                    "minZoom": 0,
                    "tileFormat": "png",
                }
        except Exception as e:
            logger.error(f"Failed to read tile-data.json for map {map_id}: {e}")

    # If still no metadata, check if we can generate minimal metadata
    if not metadata:
        # Check for dithered images or web exports
        dithered_dir = task_dir / "dithered"
        web_dir = task_dir / "web"
        tiles_dir = web_dir / "tiles"

        if dithered_dir.exists() and any(dithered_dir.iterdir()):
            # Get dimensions from first dithered image
            try:
                from PIL import Image

                for file_path in dithered_dir.glob("*.png"):
                    with Image.open(file_path) as img:
                        width, height = img.size
                        metadata = {
                            "width": width,
                            "height": height,
                            "origin_x": 0,
                            "origin_z": 0,
                            "tileSize": 512,
                            "maxZoom": 0,
                            "minZoom": 0,
                            "tileFormat": "png",
                        }
                        logger.info(
                            f"Generated metadata from dithered image for map {map_id}"
                        )
                        break
            except Exception as e:
                logger.error(
                    f"Failed to generate metadata from dithered image for map {map_id}: {e}"
                )

        if not metadata and tiles_dir.exists():
            # Try to determine metadata from directory structure
            try:
                zoom_levels = [d for d in tiles_dir.iterdir() if d.is_dir()]
                if zoom_levels:
                    # Use the highest zoom level to determine dimensions
                    zoom_dirs = sorted(
                        [int(d.name) for d in zoom_levels if d.name.isdigit()],
                        reverse=True,
                    )
                    if zoom_dirs:
                        max_zoom = zoom_dirs[0]
                        metadata = {
                            "width": 512 * (2**max_zoom),  # Estimate dimensions
                            "height": 512 * (2**max_zoom),
                            "origin_x": 0,
                            "origin_z": 0,
                            "tileSize": 512,
                            "maxZoom": max_zoom,
                            "minZoom": 0,
                            "tileFormat": "png",
                        }
                        logger.info(
                            f"Generated metadata from tile directory structure for map {map_id}"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to generate metadata from tile directory structure for map {map_id}: {e}"
                )

    # If still no metadata found, return 404
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Map not found: {map_id}")

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
    Get a thumbnail for a map (returns the first dithered image).

    Args:
        map_id: Map identifier (task ID)

    Returns:
        Thumbnail PNG image of the map (actually the dithered image)
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id

    # Find the first dithered image to use as thumbnail
    dithered_dir = task_dir / "dithered"
    dithered_image = None

    if dithered_dir.exists():
        for file_path in dithered_dir.glob("*.png"):
            dithered_image = file_path
            break

    # Fallback to full-image in web dir if no dithered image
    if not dithered_image or not dithered_image.exists():
        dithered_image = task_dir / "web" / "full-image.png"

    # If still not found, try any PNG in web directory
    if not dithered_image.exists():
        for file_path in (task_dir / "web").glob("*.png"):
            if file_path.name != "thumbnail.png":
                dithered_image = file_path
                break

    # If still no image found, raise 404
    if not dithered_image or not dithered_image.exists():
        raise HTTPException(
            status_code=404, detail=f"Image not found for map: {map_id}"
        )

    # Add CORS headers for file responses
    from starlette.requests import Request

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
    }

    return FileResponse(path=dithered_image, media_type="image/png", headers=headers)


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
    # Try to get from Redis cache first
    tile_key = f"map:{map_id}:tile:{zoom}:{x}:{y}"
    cached_tile = await redis_client.get(tile_key)

    if cached_tile:
        # Return cached tile
        logger.debug(f"Using cached tile for {map_id}: zoom={zoom}, x={x}, y={y}")
        return StreamingResponse(BytesIO(cached_tile), media_type="image/png")

    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id

    # Look for tiles in various possible locations

    # Check standard path first
    tile_path = task_dir / "web" / "tiles" / str(zoom) / str(x) / f"{y}.png"

    # If not found, try alternate structure (flat tiles directory)
    if not tile_path.exists():
        alt_tile_path = task_dir / "web" / "tiles" / f"{x}_{y}.png"
        if alt_tile_path.exists():
            tile_path = alt_tile_path

    # If still not found, try checking for possible single-zoom exports
    if not tile_path.exists() and zoom == 0:
        # Some exports might not use zoom levels but just x/y coordinates
        flat_tile_path = task_dir / "web" / "tiles" / f"{x}_{y}.png"
        if flat_tile_path.exists():
            tile_path = flat_tile_path

    # If still not found, try a potential legacy structure
    if not tile_path.exists():
        legacy_tile_path = task_dir / "web" / f"tile_{x}_{y}.png"
        if legacy_tile_path.exists():
            tile_path = legacy_tile_path

    # If no tile found in any location, return 404
    if not tile_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Tile not found: zoom={zoom}, x={x}, y={y}"
        )

    # Read the file
    with open(tile_path, "rb") as f:
        tile_data = f.read()

    # Cache the tile
    try:
        await redis_client.set(tile_key, tile_data, ex=60 * 60)  # Cache for 1 hour
        logger.debug(f"Cached tile for {map_id}: zoom={zoom}, x={x}, y={y}")
    except Exception as e:
        # Log error but continue - Redis caching is not critical
        logger.warning(f"Failed to cache tile in Redis: {e}")

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
