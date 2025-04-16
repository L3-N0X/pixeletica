"""
Image splitting functionality.

This module provides functionality for splitting images into multiple equal-sized parts.
"""

import os
import math
from PIL import Image


def split_image(
    image,
    output_dir,
    base_name,
    split_count=4,
    texture_manager=None,
    use_simplified_naming=False,
):
    """
    Split an image into a specified number of equal parts.

    Args:
        image: PIL Image to split
        output_dir: Directory to output the split parts
        base_name: Base name for the output files
        split_count: Number of parts to split the image into (default: 4)
        texture_manager: Optional TextureManager instance for consistent texture rendering
        use_simplified_naming: Use simpler naming scheme (_1, _2 instead of _part1_of_N)

    Returns:
        List of paths to the split image files
    """
    import logging

    logger = logging.getLogger("pixeletica.export.image_splitter")

    # Log if texture manager was provided
    if texture_manager:
        logger.info(f"Using provided texture manager for image splitting")
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    width, height = image.size

    # Calculate grid dimensions (try to make it as square as possible)
    grid_size = math.ceil(math.sqrt(split_count))
    grid_width = min(grid_size, split_count)
    grid_height = math.ceil(split_count / grid_width)

    # Calculate part dimensions
    part_width = width / grid_width
    part_height = height / grid_height

    # List to store paths to split images
    output_paths = []

    part_number = 1
    for y in range(grid_height):
        for x in range(grid_width):
            # Stop if we've created the requested number of parts
            if part_number > split_count:
                break

            # Calculate the boundaries for this part
            left = int(x * part_width)
            top = int(y * part_height)
            right = int(min((x + 1) * part_width, width))
            bottom = int(min((y + 1) * part_height, height))

            # Crop the part from the main image
            part = image.crop((left, top, right, bottom))

            # Save the part with appropriate naming scheme
            if use_simplified_naming:
                # Use simplified naming: base_name_1.png, base_name_2.png, etc.
                output_path = os.path.join(output_dir, f"{base_name}_{part_number}.png")
            else:
                # Use original naming: base_name_part1_of_4.png
                output_path = os.path.join(
                    output_dir, f"{base_name}_part{part_number}_of_{split_count}.png"
                )

            part.save(output_path)
            output_paths.append(output_path)

            part_number += 1

    return output_paths


def split_image_equal_size(image, output_dir, base_name, tile_width, tile_height):
    """
    Split an image into parts of equal pixel dimensions.

    Args:
        image: PIL Image to split
        output_dir: Directory to output the split parts
        base_name: Base name for the output files
        tile_width: Width of each tile in pixels
        tile_height: Height of each tile in pixels

    Returns:
        Dictionary containing information about the tiles
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    width, height = image.size

    # Calculate number of tiles
    tiles_x = math.ceil(width / tile_width)
    tiles_z = math.ceil(height / tile_height)

    # Information about the split
    split_info = {
        "width": width,
        "height": height,
        "tile_width": tile_width,
        "tile_height": tile_height,
        "tiles_x": tiles_x,
        "tiles_z": tiles_z,
        "tiles": [],
    }

    # Generate tiles
    for z in range(tiles_z):
        for x in range(tiles_x):
            # Calculate tile boundaries
            left = x * tile_width
            top = z * tile_height
            right = min((x + 1) * tile_width, width)
            bottom = min((z + 1) * tile_height, height)

            # Crop the tile from the image
            tile = image.crop((left, top, right, bottom))

            # Create tile filename
            tile_filename = f"{base_name}_x{x}_z{z}.png"
            tile_path = os.path.join(output_dir, tile_filename)

            # Save the tile
            tile.save(tile_path)

            # Add tile info to the export metadata
            tile_info = {
                "filename": tile_filename,
                "path": tile_path,
                "x": x,
                "z": z,
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            }
            split_info["tiles"].append(tile_info)

    return split_info
