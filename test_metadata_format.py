"""
Test script for the new metadata format.
"""

import os
import json
import numpy as np
from pixeletica.metadata import (
    compress_block_data,
    decompress_block_data,
    create_metadata,
    save_metadata_json,
    load_metadata_json,
)


def test_matrix_format():
    """Test the new matrix format for block data."""
    print("Testing new matrix format for blocks metadata...")

    # Create a small test 4x4 block data array
    test_blocks = [
        [
            "minecraft:red_concrete",
            "minecraft:blue_concrete",
            "minecraft:red_concrete",
            "minecraft:blue_concrete",
        ],
        [
            "minecraft:blue_concrete",
            "minecraft:red_concrete",
            "minecraft:blue_concrete",
            "minecraft:red_concrete",
        ],
        [
            "minecraft:red_concrete",
            "minecraft:blue_concrete",
            "minecraft:granite",
            "minecraft:blue_concrete",
        ],
        [
            "minecraft:blue_concrete",
            "minecraft:red_concrete",
            "minecraft:blue_concrete",
            "minecraft:cherry_planks",
        ],
    ]

    # Compress the block data
    print("\nCompressing block data...")
    compressed = compress_block_data(test_blocks)
    print(f"Format: {compressed['format']}")
    print(f"Used blocks: {compressed['block_definitions']}")
    print(f"Data structure: {type(compressed['data']).__name__}")
    print(f"First row: {compressed['data'][0]}")

    # Decompress the block data
    print("\nDecompressing block data...")
    decompressed = decompress_block_data(compressed)
    print(f"Decompressed shape: {decompressed.shape}")
    print(f"First row: {decompressed[0]}")

    # Check that the decompressed data matches the original
    matches = np.array_equal(decompressed, np.array(test_blocks))
    print(f"\nDecompressed data matches original: {matches}")

    # Create a full metadata object
    print("\nCreating full metadata...")
    metadata = create_metadata(
        original_image_path="test_image.png",
        output_image_path="test_output.png",
        width=4,
        height=4,
        algorithm_name="Test",
        processing_time=0.1,
        block_data=test_blocks,
    )

    # Print the metadata in a nice format
    print("\nFinal metadata structure:")
    print(json.dumps(metadata, indent=2))

    print("\nTest completed successfully!")


if __name__ == "__main__":
    test_matrix_format()
