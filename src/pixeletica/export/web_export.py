"""
Web export functionality.

This module provides functionality for exporting Minecraft images as web-optimized tiles
for use in external web viewers.
"""

import os
import json
import math
from PIL import Image
from pathlib import Path


def export_web_tiles(image, output_dir, tile_size=512, origin_x=0, origin_z=0):
    """
    Export an image as a set of web-optimized tiles using a simplified structure.

    Args:
        image: PIL Image to export
        output_dir: Directory to output the tiles to
        tile_size: Size of each tile (default: 512×512)
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin

    Returns:
        Dictionary containing information about the exported tiles
    """
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    width, height = image.size

    # Create metadata structure for a single zoom level
    metadata = {
        "width": width,
        "height": height,
        "origin_x": origin_x,
        "origin_z": origin_z,
        "tile_size": tile_size,
        "tiles_x": math.ceil(width / tile_size),
        "tiles_z": math.ceil(height / tile_size),
        "tiles": [],
    }

    # Create tiles directory
    tiles_dir = os.path.join(output_dir, "tiles")
    os.makedirs(tiles_dir, exist_ok=True)

    # Calculate tiles
    tiles_x = metadata["tiles_x"]
    tiles_z = metadata["tiles_z"]

    # Generate tiles
    for z in range(tiles_z):
        for x in range(tiles_x):
            # Calculate tile boundaries
            left = x * tile_size
            top = z * tile_size
            right = min((x + 1) * tile_size, width)
            bottom = min((z + 1) * tile_size, height)

            # Crop the tile
            tile = image.crop((left, top, right, bottom))

            # Calculate in-world coordinates
            world_x = left + origin_x
            world_z = top + origin_z

            # Create tile filename and path
            tile_filename = f"{x}_{z}.png"
            tile_path = os.path.join(tiles_dir, tile_filename)

            # Save the tile
            tile.save(tile_path, "PNG", optimize=True)

            # Add tile info to metadata
            tile_info = {
                "x": x,
                "z": z,
                "world_x": world_x,
                "world_z": world_z,
                "width": right - left,
                "height": bottom - top,
                "filename": f"tiles/{tile_filename}",
            }
            metadata["tiles"].append(tile_info)

    # Save metadata as JSON
    metadata_path = os.path.join(output_dir, "tile-data.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


# HTML viewer generation removed as per new requirements
