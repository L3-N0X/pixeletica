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
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi_limiter.depends import RateLimiter

from pixeletica.api.models import MapInfo, MapListResponse, MapMetadata
from pixeletica.api.services import storage


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

# Initialize router
router = APIRouter(tags=["maps"])


@router.get("/api/maps.json", response_model=MapListResponse)
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

                # Create map info
                map_info = MapInfo(
                    id=task_id,
                    name=metadata.get("name", f"Map {task_id[:6]}"),
                    created=datetime.fromisoformat(metadata.get("updated")),
                    thumbnail=f"/api/map/{task_id}/thumbnail.jpg",
                    description=metadata.get("description"),
                )
                maps.append(map_info)

    return MapListResponse(maps=maps)


@router.get("/api/map/{map_id}/metadata.json")
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

    # Get the task metadata for additional information
    task_metadata = storage.load_task_metadata(map_id)
    if task_metadata:
        metadata["name"] = task_metadata.get("name", f"Map {map_id[:6]}")
        metadata["created"] = task_metadata.get("updated")
        metadata["description"] = task_metadata.get("description")

    return metadata


@router.get("/api/map/{map_id}/full-image.jpg")
async def get_map_full_image(map_id: str):
    """
    Get the full image for a map.

    Args:
        map_id: Map identifier (task ID)

    Returns:
        Full-size JPEG image of the map
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    full_image_path = task_dir / "web" / "full-image.jpg"

    if not full_image_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Full image not found for map: {map_id}"
        )

    return FileResponse(path=full_image_path, media_type="image/jpeg")


@router.get("/api/map/{map_id}/thumbnail.jpg")
async def get_map_thumbnail(map_id: str):
    """
    Get a thumbnail for a map.

    Args:
        map_id: Map identifier (task ID)

    Returns:
        Thumbnail JPEG image of the map
    """
    # Check if map exists
    task_dir = storage.TASKS_DIR / map_id
    full_image_path = task_dir / "web" / "full-image.jpg"

    if not full_image_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Image not found for map: {map_id}"
        )

    # Create a thumbnail if it doesn't exist
    thumbnail_path = task_dir / "web" / "thumbnail.jpg"
    if not thumbnail_path.exists():
        try:
            from PIL import Image

            img = Image.open(full_image_path)
            img.thumbnail((300, 300))
            img.save(thumbnail_path, "JPEG", quality=85)
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            return FileResponse(path=full_image_path, media_type="image/jpeg")

    return FileResponse(path=thumbnail_path, media_type="image/jpeg")


@router.get("/api/map/{map_id}/tiles/{zoom}/{x}/{y}.png")
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

    # Return the file
    return StreamingResponse(BytesIO(tile_data), media_type="image/png")
