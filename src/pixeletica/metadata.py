"""
Metadata handling for processed images.
"""

import os
import json
import time
import datetime
from PIL import Image
import numpy as np


def create_metadata(
    original_image_path,
    output_image_path,
    width,
    height,
    algorithm_name,
    processing_time,
    block_data,
    palette_name="Gomme r/place color map",
    origin_x=0,
    origin_z=0,
    export_settings=None,
    exported_files=None,
):
    """
    Create metadata for a processed image.

    Args:
        original_image_path: Path to the original image
        output_image_path: Path to the output image
        width: Width of the image
        height: Height of the image
        algorithm_name: Name of the dithering algorithm used
        processing_time: Time taken to process in seconds
        block_data: Array of block IDs used for each pixel
        palette_name: Name of the block palette used
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin
        export_settings: Dictionary of export settings (optional)
        exported_files: Dictionary of exported file paths (optional)

    Returns:
        Dictionary containing the metadata
    """
    original_filename = os.path.basename(original_image_path)
    output_filename = os.path.basename(output_image_path)

    # Calculate coordinate information
    from pixeletica.coordinates.chunk_calculator import calculate_image_offset

    coordinates = calculate_image_offset(origin_x, origin_z)

    # Compress block data
    # Convert 2D array to run-length encoding for space efficiency with indexed blocks
    compressed_blocks = compress_block_data(block_data)

    # Create metadata dict with blocks at the end
    metadata = {
        "original_image": original_filename,
        "output_image": output_filename,
        "dimensions": {"width": width, "height": height},
        "algorithm": algorithm_name,
        "processing_time_seconds": processing_time,
        "timestamp": datetime.datetime.now().isoformat(),
        "block_palette": {"name": palette_name, "source": "minecraft/block-colors.csv"},
        "coordinates": coordinates,
    }

    # Add export settings if provided
    if export_settings:
        metadata["export_settings"] = export_settings

    # Add exported files if provided
    if exported_files:
        metadata["exported_files"] = exported_files

    # Add blocks as the last item in the metadata
    metadata["blocks"] = compressed_blocks

    return metadata


def compress_block_data(block_data):
    """
    Prepare a 2D array of block IDs for storage in metadata.

    This function creates a 2D matrix representation of blocks and
    only includes blocks that are actually used in the image.

    Args:
        block_data: 2D array of block IDs

    Returns:
        Dictionary with block data as a 2D matrix and used block definitions
    """
    if len(block_data) == 0:
        return {"format": "matrix", "data": [], "block_definitions": []}

    # Create a set of unique block IDs used in the image
    unique_blocks = set()
    for row in block_data:
        for block_id in row:
            unique_blocks.add(block_id)

    # Create an ordered list of unique block IDs
    used_block_definitions = sorted(list(unique_blocks))

    # Create a mapping from block ID to index in our definitions array
    block_index_map = {
        block_id: idx for idx, block_id in enumerate(used_block_definitions)
    }

    # Create a 2D matrix of block indices
    matrix_data = []
    for row in block_data:
        matrix_row = [block_index_map.get(block_id, -1) for block_id in row]
        matrix_data.append(matrix_row)

    return {
        "format": "matrix",
        "data": matrix_data,
        "block_definitions": used_block_definitions,
    }


def decompress_block_data(compressed_data, width=None, height=None):
    """
    Convert block data from metadata back to a 2D array of actual block IDs.

    Args:
        compressed_data: Dictionary with block data
        width: Width of the image (optional, only needed for RLE formats)
        height: Height of the image (optional, only needed for RLE formats)

    Returns:
        2D array of block IDs
    """
    if compressed_data["format"] == "rle":
        # Handle original RLE format (legacy support)
        if width is None or height is None:
            raise ValueError("Width and height are required for RLE format")
        flat_data = []
        for item in compressed_data["data"]:
            block_id, count = item
            flat_data.extend([block_id] * count)
        return np.array(flat_data).reshape(height, width)

    elif compressed_data["format"] == "indexed-rle":
        # Handle indexed RLE format (legacy support)
        if width is None or height is None:
            raise ValueError("Width and height are required for indexed-RLE format")
        block_definitions = compressed_data.get("block_definitions", [])
        flat_data = []

        for item in compressed_data["data"]:
            block_index, count = item
            # Convert index back to block ID
            if 0 <= block_index < len(block_definitions):
                block_id = block_definitions[block_index]
            else:
                block_id = f"unknown_block_{block_index}"
            flat_data.extend([block_id] * count)
        return np.array(flat_data).reshape(height, width)

    elif compressed_data["format"] == "matrix":
        # Handle matrix format (new format)
        block_definitions = compressed_data["block_definitions"]
        block_data = []
        for row in compressed_data["data"]:
            block_row = []
            for block_index in row:
                if 0 <= block_index < len(block_definitions):
                    block_id = block_definitions[block_index]
                else:
                    block_id = f"unknown_block_{block_index}"
                block_row.append(block_id)
            block_data.append(block_row)
        return np.array(block_data)
    else:
        raise ValueError(f"Unsupported format: {compressed_data['format']}")


def save_metadata_json(metadata, output_path):
    """
    Save metadata to a JSON file.

    Args:
        metadata: Dictionary containing metadata
        output_path: Path to save the JSON file

    Returns:
        Path to the saved JSON file
    """
    # Create metadata filename based on output image path
    base_path, _ = os.path.splitext(output_path)
    json_path = f"{base_path}.json"

    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return json_path


def load_metadata_json(json_path):
    """
    Load metadata from a JSON file.

    Args:
        json_path: Path to the JSON file

    Returns:
        Dictionary containing the metadata
    """
    with open(json_path, "r") as f:
        metadata = json.load(f)

    return metadata
