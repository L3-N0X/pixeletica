"""
Random dithering implementation.
"""

import numpy as np
from PIL import Image
from src.pixeletica.block_utils.color_matcher import find_closest_block_color


def apply_random_dithering(img):
    """
    Apply random dithering algorithm.

    Args:
        img: PIL Image object

    Returns:
        Tuple of:
        - PIL Image object with randomly dithered colors using Minecraft block colors
        - 2D array of block IDs for each pixel
    """
    if img is None:
        return None, None

    width, height = img.size
    img = img.convert("RGB")
    result = Image.new("RGB", (width, height))

    # Track block IDs for metadata
    block_ids = [[None for _ in range(width)] for _ in range(height)]

    pixels = np.array(img)
    result_pixels = result.load()

    # Generate random noise
    random_noise = np.random.uniform(-32, 32, (height, width, 3))

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[y, x]

            # Apply random noise
            r_adj = int(r + random_noise[y, x, 0])
            g_adj = int(g + random_noise[y, x, 1])
            b_adj = int(b + random_noise[y, x, 2])

            # Clamp values
            r_adj = max(0, min(255, r_adj))
            g_adj = max(0, min(255, g_adj))
            b_adj = max(0, min(255, b_adj))

            # Find closest block color
            closest_block, block_id = find_closest_block_color((r_adj, g_adj, b_adj))

            if closest_block:  # Add check to make sure we found a block
                result_pixels[x, y] = closest_block["rgb"]
                block_ids[y][x] = block_id  # Store the block ID
            else:  # Fallback if no block found
                result_pixels[x, y] = (r, g, b)
                block_ids[y][x] = None

    return result, block_ids
