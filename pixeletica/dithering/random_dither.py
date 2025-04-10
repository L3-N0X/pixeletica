"""
Random dithering implementation.
"""

import numpy as np
from PIL import Image
from pixeletica.block_utils.color_matcher import find_closest_block_color


def apply_random_dithering(img):
    """
    Apply random dithering algorithm.

    Args:
        img: PIL Image object

    Returns:
        PIL Image object with randomly dithered colors using Minecraft block colors
    """
    if img is None:
        return None

    width, height = img.size
    img = img.convert("RGB")
    result = Image.new("RGB", (width, height))

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
            closest_block = find_closest_block_color((r_adj, g_adj, b_adj))
            if closest_block:  # Add check to make sure we found a block
                result_pixels[x, y] = closest_block["rgb"]
            else:  # Fallback if no block found
                result_pixels[x, y] = (r, g, b)

    return result
