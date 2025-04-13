"""
Module for generating Litematica schematics from dithered images.
"""

from litemapy import Schematic, Region, BlockState
import os
import time
import numpy as np


def generate_schematic(
    block_ids,
    image_name,
    algorithm_name,
    metadata=None,
    origin_x=0,
    origin_y=0,
    origin_z=0,
):
    """
    Generate a Litematica schematic from block IDs.

    Args:
        block_ids: 2D array of block IDs from dithering
        image_name: Name of the original image
        algorithm_name: Name of the dithering algorithm used
        metadata: Dictionary containing schematic metadata (optional)
            - author: Name of the author
            - description: Description of the schematic
            - name: Name of the schematic
        origin_x: X-coordinate in the Minecraft world to position the schematic
        origin_y: Y-coordinate in the Minecraft world to position the schematic
        origin_z: Z-coordinate in the Minecraft world to position the schematic

    Returns:
        Path to the saved schematic file
    """
    # Create output directory if it doesn't exist
    os.makedirs("./out/schematics", exist_ok=True)

    # Get dimensions from the block IDs array
    height, width = np.array(block_ids).shape

    # Extract filename without extension
    base_name = os.path.splitext(os.path.basename(image_name))[0]

    # Default metadata if not provided
    if metadata is None:
        metadata = {}

    author = metadata.get("author", "L3-N0X - pixeletica")
    name = metadata.get("name", base_name)
    description = metadata.get(
        "description", f"Generated from {base_name} using {algorithm_name}"
    )

    # Create a region with dimensions
    # For a flat image, y=1 (height is always 1 block)
    # Setting the region's position based on user-specified origin
    # When the schematic is placed at (0,0,0), this will position the blocks at the correct coordinates
    region = Region(origin_x, origin_y, origin_z, width, 1, height)

    # Create schematic from the region
    schematic = region.as_schematic(name=name, author=author, description=description)

    # Place blocks in the region
    for z in range(height):
        for x in range(width):
            block_id = block_ids[z][x]
            if block_id is not None:  # Skip transparent pixels
                # Convert block ID to BlockState
                # Using default orientation as specified
                block_state = BlockState(block_id)
                # Position blocks correctly based on the region's origin
                region[x, 0, z] = block_state

    # Generate filename for schematic
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    schematic_path = (
        f"./out/schematics/{base_name}_{algorithm_name}_{timestamp}.litematic"
    )

    # Save schematic
    schematic.save(schematic_path)

    return schematic_path
