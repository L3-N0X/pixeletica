"""
Floyd-Steinberg dithering implementation.
"""

import numpy as np
from PIL import Image
from pixeletica.block_utils.color_matcher import find_closest_block_color


def apply_floyd_steinberg_dithering(img):
    """
    Apply Floyd-Steinberg dithering algorithm.

    Args:
        img: PIL Image object

    Returns:
        PIL Image object with dithered colors using Minecraft block colors
    """
    if img is None:
        return None

    width, height = img.size
    img = img.convert("RGB")

    # Convert image to numpy array for faster processing
    pixels = np.array(img, dtype=float)
    result = np.zeros_like(pixels)

    for y in range(height):
        for x in range(width):
            old_pixel = pixels[y, x].copy()
            closest_block = find_closest_block_color(tuple(map(int, old_pixel)))

            if closest_block is None:  # Fallback if no block found
                new_pixel = np.array(old_pixel, dtype=int)
            else:
                new_pixel = np.array(closest_block["rgb"])

            # Set the result pixel
            result[y, x] = new_pixel

            # Calculate quantization error
            error = old_pixel - new_pixel

            # Distribute error to neighboring pixels (Floyd-Steinberg algorithm)
            if x + 1 < width:
                pixels[y, x + 1] += error * 7 / 16
            if x - 1 >= 0 and y + 1 < height:
                pixels[y + 1, x - 1] += error * 3 / 16
            if y + 1 < height:
                pixels[y + 1, x] += error * 5 / 16
            if x + 1 < width and y + 1 < height:
                pixels[y + 1, x + 1] += error * 1 / 16

    # Convert back to PIL Image
    result_img = Image.fromarray(np.uint8(result))
    return result_img
