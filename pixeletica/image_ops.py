"""
Basic image operations module.
"""

import os
import datetime
from PIL import Image


def resize_image(img, target_width=None, target_height=None):
    """
    Resize an image while maintaining aspect ratio.

    Args:
        img: PIL Image object
        target_width: Target width, or None to calculate from height
        target_height: Target height, or None to calculate from width

    Returns:
        Resized PIL Image object
    """
    if img is None:
        return None

    # Get original dimensions
    original_width, original_height = img.size

    # Keep original size if no dimensions are specified
    if target_width is None and target_height is None:
        return img.copy()

    # Calculate dimensions based on input
    if target_width is not None and target_height is None:
        # Calculate height based on width to maintain aspect ratio
        aspect_ratio = original_height / original_width
        target_height = int(target_width * aspect_ratio)

    elif target_width is None and target_height is not None:
        # Calculate width based on height to maintain aspect ratio
        aspect_ratio = original_width / original_height
        target_width = int(target_height * aspect_ratio)

    # Resize the image
    resized_img = img.resize((target_width, target_height), Image.LANCZOS)
    return resized_img


def load_image(image_path):
    """
    Load an image from the given path.

    Args:
        image_path: Path to the image file

    Returns:
        PIL Image object or None if error
    """
    try:
        img = Image.open(image_path)
        return img
    except Exception as e:
        print(f"Error opening image: {e}")
        return None


def save_dithered_image(img, original_path, algorithm_name):
    """
    Save dithered image with timestamp and original filename.

    Args:
        img: PIL Image object to save
        original_path: Original image path (used for filename)
        algorithm_name: Name of the dithering algorithm used

    Returns:
        Path of the saved image
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(original_path)
    name, ext = os.path.splitext(filename)

    output_dir = "./out/dithered"
    os.makedirs(output_dir, exist_ok=True)

    output_path = f"{output_dir}/{name}_{algorithm_name}_{timestamp}{ext}"
    img.save(output_path)
    print(f"Saved dithered image as: {output_path}")

    return output_path
