"""
Ordered dithering using a Bayer matrix.
"""

import numpy as np
from PIL import Image
from pixeletica.block_utils.color_matcher import find_closest_block_color


def apply_ordered_dithering(img):
    """
    Apply ordered dithering using a Bayer matrix.

    Args:
        img: PIL Image object

    Returns:
        PIL Image object with dithered colors using Minecraft block colors
    """
    if img is None:
        return None

    width, height = img.size
    img = img.convert("RGB")
    result = Image.new("RGB", (width, height))

    pixels = np.array(img)
    result_pixels = result.load()

    # 4x4 Bayer matrix
    bayer_matrix = (
        np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    )

    for y in range(height):
        for x in range(width):
            # Apply threshold based on Bayer matrix
            threshold = bayer_matrix[y % 4, x % 4]

            r, g, b = pixels[y, x]
            # Apply threshold adjustment
            r_adj = int(r + threshold * 64 - 32)
            g_adj = int(g + threshold * 64 - 32)
            b_adj = int(b + threshold * 64 - 32)

            # Clamp values
            r_adj = max(0, min(255, r_adj))
            g_adj = max(0, min(255, g_adj))
            b_adj = max(0, min(255, b_adj))

            # Find closest block color
            closest_block = find_closest_block_color((r_adj, g_adj, b_adj))
            if closest_block:  # Add check to make sure we found a block
                result_pixels[x, y] = closest_block["rgb"]
            else:  # Fallback if no block found
                result_pixels[x, y] = (r, g, b)

    return result
