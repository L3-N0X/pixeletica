"""
Functions for color matching and finding closest block colors.
"""

from pixeletica.block_utils.block_loader import get_block_colors


def find_closest_block_color(pixel_color):
    """Find the Minecraft block color closest to the given RGB color."""
    block_colors = get_block_colors()

    if not block_colors:
        raise ValueError("Block colors not loaded. Call load_block_colors() first.")

    r, g, b = pixel_color
    min_distance = float("inf")
    closest_block = None

    for block in block_colors:
        block_r, block_g, block_b = block["rgb"]
        # Calculate color distance using Euclidean distance
        distance = ((block_r - r) ** 2 + (block_g - g) ** 2 + (block_b - b) ** 2) ** 0.5

        if distance < min_distance:
            min_distance = distance
            closest_block = block

    return closest_block
