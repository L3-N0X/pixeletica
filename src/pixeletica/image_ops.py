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


def save_dithered_image(
    img, original_path, algorithm_name, block_ids=None, processing_time=0
):
    """
    Save dithered image with timestamp, original filename, and metadata (if block IDs provided).

    Args:
        img: PIL Image object to save
        original_path: Original image path (used for filename)
        algorithm_name: Name of the dithering algorithm used
        block_ids: 2D array of block IDs used for each pixel (optional)
        processing_time: Time taken to process in seconds (optional)

    Returns:
        Path of the saved image
    """
    from pixeletica.metadata import create_metadata, save_metadata_json

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(original_path)
    name, ext = os.path.splitext(filename)

    output_dir = "./out/dithered"
    os.makedirs(output_dir, exist_ok=True)

    output_path = f"{output_dir}/{name}_{algorithm_name}_{timestamp}{ext}"
    img.save(output_path)
    print(f"Saved dithered image as: {output_path}")

    # Save metadata if block IDs are provided
    if block_ids is not None:
        width, height = img.size

        # Create metadata object
        metadata = create_metadata(
            original_image_path=original_path,
            output_image_path=output_path,
            width=width,
            height=height,
            algorithm_name=algorithm_name,
            processing_time=processing_time,
            block_data=block_ids,
        )

        # Save metadata to JSON file
        json_path = save_metadata_json(metadata, output_path)
        print(f"Saved metadata as: {json_path}")

    return output_path
