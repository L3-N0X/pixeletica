"""
Module for generating Litematica schematics from dithered images.
"""

from litemapy import Schematic, Region, BlockState
import os
import time
import numpy as np


def generate_schematic(block_ids, image_name, algorithm_name, metadata=None):
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

    # Create a new schematic
    # The x,y,z parameters define the dimensions of the schematic
    # For a flat image, y=1 (height is always 1 block)
    schematic = Schematic(width, 1, height)

    # Set schematic metadata
    schematic.author = author
    schematic.name = name
    schematic.description = description

    # Add a region to the schematic (required by Litematica)
    region = schematic.addRegion(name, (0, 0, 0))  # Start at origin

    # Place blocks in the schematic
    for z in range(height):
        for x in range(width):
            block_id = block_ids[z][x]
            if block_id is not None:  # Skip transparent pixels
                # Convert block ID to BlockState
                # Using default orientation as specified
                block_state = BlockState(block_id)
                region.setBlock(x, 0, z, block_state)  # Y is always 0 (one layer high)

    # Generate filename for schematic
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    schematic_path = (
        f"./out/schematics/{base_name}_{algorithm_name}_{timestamp}.litematic"
    )

    # Save schematic
    schematic.save(schematic_path)

    return schematic_path
