"""
Web export functionality.

This module provides functionality for exporting Minecraft images as web-optimized tiles
for use in external web viewers.
"""

import os
import json
import math


def export_web_tiles(image, output_dir, tile_size=512, origin_x=0, origin_z=0, progress_callback=None):
    """
    Export an image as a set of web-optimized tiles for multiple zoom levels.

    Args:
        image: PIL Image to export
        output_dir: Directory to output the tiles to
        tile_size: Size of each tile (default: 512×512)
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin
        progress_callback: Optional function(progress: float, info: dict) to report progress

    Returns:
        Dictionary containing information about the exported tiles
    """
    import copy
    from PIL import Image

    os.makedirs(output_dir, exist_ok=True)

    width, height = image.size

    # Set zoom boundaries
    min_zoom = 0
    max_zoom = 5
    base_zoom = 3  # old zoom 0 is now zoomLevel 5

    # Metadata for all zoom levels
    metadata = {
        "width": width,
        "height": height,
        "origin_x": origin_x,
        "origin_z": origin_z,
        "tile_size": tile_size,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "zoom_levels": [],
    }

    # Count total tiles for all zoom levels for progress calculation
    total_tiles = 0
    tiles_per_zoom = []
    for zoom in range(min_zoom, max_zoom + 1):
        scale = 2 ** (zoom - base_zoom)
        if scale < 1:
            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))
        else:
            new_width = int(width * scale)
            new_height = int(height * scale)
        tiles_x = math.ceil(new_width / tile_size)
        tiles_z = math.ceil(new_height / tile_size)
        tiles_per_zoom.append((tiles_x, tiles_z))
        total_tiles += tiles_x * tiles_z

    tile_counter = 0

    for zoom_idx, zoom in enumerate(range(min_zoom, max_zoom + 1)):
        scale = 2 ** (zoom - base_zoom)
        if scale < 1:
            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))
        else:
            new_width = int(width * scale)
            new_height = int(height * scale)

        resized_image = image.resize((new_width, new_height), resample=Image.NEAREST)

        tiles_x, tiles_z = tiles_per_zoom[zoom_idx]

        zoom_tiles = []

        # Directory for this zoom level
        tiles_dir = os.path.join(output_dir, "tiles", str(zoom))
        os.makedirs(tiles_dir, exist_ok=True)

        for z in range(tiles_z):
            for x in range(tiles_x):
                left = x * tile_size
                top = z * tile_size
                right = min((x + 1) * tile_size, new_width)
                bottom = min((z + 1) * tile_size, new_height)

                tile = resized_image.crop((left, top, right, bottom))

                tile_full = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
                tile_full.paste(tile, (0, 0))

                # Calculate world coordinates relative to original image
                # For zoom 5, 1:1 mapping; for others, scale accordingly
                world_x = int(left / scale) + origin_x if scale != 0 else origin_x
                world_z = int(top / scale) + origin_z if scale != 0 else origin_z

                tile_filename = f"{x}_{z}.png"
                tile_path = os.path.join(tiles_dir, tile_filename)
                tile_full.save(tile_path, "PNG", optimize=True)

                tile_info = {
                    "x": x,
                    "z": z,
                    "zoomLevel": zoom,
                    "world_x": world_x,
                    "world_z": world_z,
                    "width": tile_size,
                    "height": tile_size,
                    "filename": f"tiles/{zoom}/{tile_filename}",
                }
                zoom_tiles.append(tile_info)

                tile_counter += 1
                if progress_callback and total_tiles > 0:
                    percent = (tile_counter / total_tiles) * 100
                    # Call every 5% or on last tile
                    if tile_counter == total_tiles or percent % 5 < (100 / total_tiles):
                        progress_callback(percent, {
                            "zoom": zoom,
                            "x": x,
                            "z": z,
                            "tile_counter": tile_counter,
                            "total_tiles": total_tiles,
                        })

        metadata["zoom_levels"].append({
            "zoomLevel": zoom,
            "tiles_x": tiles_x,
            "tiles_z": tiles_z,
            "tiles": zoom_tiles,
        })

    # Save metadata as JSON
    metadata_path = os.path.join(output_dir, "tile-data.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    if progress_callback:
        progress_callback(100.0, {"done": True})

    return metadata


# HTML viewer generation removed as per new requirements
