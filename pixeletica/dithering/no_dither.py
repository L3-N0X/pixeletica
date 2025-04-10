"""
Simple color quantization without dithering.
"""

from PIL import Image
from pixeletica.block_utils.color_matcher import find_closest_block_color


def apply_no_dithering(img):
    """
    Simple color quantization without dithering.

    Args:
        img: PIL Image object

    Returns:
        PIL Image object with colors replaced by nearest Minecraft block colors
    """
    if img is None:
        return None

    width, height = img.size
    result = Image.new("RGB", (width, height))

    # Make sure we're working with RGB images
    img = img.convert("RGB")

    pixels = img.load()
    result_pixels = result.load()

    for y in range(height):
        for x in range(width):
            closest_block = find_closest_block_color(pixels[x, y])
            if closest_block:  # Add check to make sure we found a block
                result_pixels[x, y] = closest_block["rgb"]
            else:  # Fallback if no block found (should not happen normally)
                result_pixels[x, y] = pixels[x, y]

    return result
