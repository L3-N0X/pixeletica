"""
Minecraft chunk calculation utilities.

This module provides functions to calculate chunk boundaries and offsets based on
Minecraft coordinates, ensuring proper alignment of chunk lines in exported images.
"""

import math

# Constants
CHUNK_SIZE = 16  # Minecraft chunks are 16x16 blocks


def get_chunk_from_position(x, z):
    """
    Get the chunk coordinates for a given position.

    Args:
        x: X-coordinate in the Minecraft world
        z: Z-coordinate in the Minecraft world

    Returns:
        Tuple of (chunk_x, chunk_z) coordinates
    """
    # Integer division to get the chunk
    chunk_x = math.floor(x / CHUNK_SIZE)
    chunk_z = math.floor(z / CHUNK_SIZE)

    return chunk_x, chunk_z


def get_offset_in_chunk(x, z):
    """
    Get the offset within a chunk for a given position.

    Args:
        x: X-coordinate in the Minecraft world
        z: Z-coordinate in the Minecraft world

    Returns:
        Tuple of (offset_x, offset_z) relative to the chunk corner
    """
    # Modulo to get position within chunk
    offset_x = x % CHUNK_SIZE
    # Handle negative coordinates properly
    if offset_x < 0:
        offset_x += CHUNK_SIZE

    offset_z = z % CHUNK_SIZE
    if offset_z < 0:
        offset_z += CHUNK_SIZE

    return int(offset_x), int(offset_z)


def is_chunk_boundary_x(x, offset_x=0):
    """
    Check if a given X-coordinate is on a chunk boundary.

    Args:
        x: X-coordinate in the image (0-indexed from the start of the image)
        offset_x: X offset from the world origin

    Returns:
        True if the position is on a chunk boundary, False otherwise
    """
    return (x + offset_x) % CHUNK_SIZE == 0


def is_chunk_boundary_z(z, offset_z=0):
    """
    Check if a given Z-coordinate is on a chunk boundary.

    Args:
        z: Z-coordinate in the image (0-indexed from the start of the image)
        offset_z: Z offset from the world origin

    Returns:
        True if the position is on a chunk boundary, False otherwise
    """
    return (z + offset_z) % CHUNK_SIZE == 0


def calculate_image_offset(origin_x, origin_z):
    """
    Calculate image offset based on a world origin position.

    In Minecraft, (0,0) is where 4 chunks meet. This function calculates
    the offset needed to properly align chunk lines in the image.

    Args:
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin

    Returns:
        Dictionary containing offset and chunk information:
            - origin_x, origin_z: The provided world coordinates
            - chunk_x, chunk_z: The chunk containing the world origin
            - offset_x, offset_z: Offset within the chunk
    """
    chunk_x, chunk_z = get_chunk_from_position(origin_x, origin_z)
    offset_x, offset_z = get_offset_in_chunk(origin_x, origin_z)

    return {
        "origin_x": origin_x,
        "origin_z": origin_z,
        "chunk_x": chunk_x,
        "chunk_z": chunk_z,
        "offset_x": offset_x,
        "offset_z": offset_z,
    }
