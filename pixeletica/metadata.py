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

    Returns:
        Dictionary containing the metadata
    """
    original_filename = os.path.basename(original_image_path)
    output_filename = os.path.basename(output_image_path)

    # Compress block data
    # Convert 2D array to run-length encoding for space efficiency
    compressed_blocks = compress_block_data(block_data)

    metadata = {
        "original_image": original_filename,
        "output_image": output_filename,
        "dimensions": {"width": width, "height": height},
        "algorithm": algorithm_name,
        "processing_time_seconds": processing_time,
        "timestamp": datetime.datetime.now().isoformat(),
        "block_palette": {"name": palette_name, "source": "minecraft/block-colors.csv"},
        "blocks": compressed_blocks,
    }

    return metadata


def compress_block_data(block_data):
    """
    Compress a 2D array of block IDs using run-length encoding.

    Args:
        block_data: 2D array of block IDs

    Returns:
        Dictionary with compressed block data
    """
    if len(block_data) == 0:
        return {"format": "rle", "data": []}

    # Flatten the 2D array
    flat_data = np.array(block_data).flatten()

    # Initialize variables for RLE
    rle_data = []
    current_id = flat_data[0]
    count = 1

    # Perform run-length encoding
    for i in range(1, len(flat_data)):
        if flat_data[i] == current_id:
            count += 1
        else:
            rle_data.append([current_id, count])
            current_id = flat_data[i]
            count = 1

    # Add the last run
    rle_data.append([current_id, count])

    return {"format": "rle", "data": rle_data}


def decompress_block_data(compressed_data, width, height):
    """
    Decompress run-length encoded block data back to a 2D array.

    Args:
        compressed_data: Dictionary with compressed block data
        width: Width of the image
        height: Height of the image

    Returns:
        2D array of block IDs
    """
    if compressed_data["format"] != "rle":
        raise ValueError("Unsupported compression format")

    # Initialize flat array
    flat_data = []

    # Decompress RLE data
    for item in compressed_data["data"]:
        block_id, count = item
        flat_data.extend([block_id] * count)

    # Reshape to 2D array
    return np.array(flat_data).reshape(height, width)


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
