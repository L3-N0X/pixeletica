"""
Command-line interface for Pixeletica.
"""

import os
import time
from pixeletica.block_utils.block_loader import load_block_colors
from pixeletica.dithering import get_algorithm_by_name
from pixeletica.image_ops import load_image, resize_image, save_dithered_image


def resize_image_interactive(image_path):
    """
    Interactive command-line interface for resizing an image.

    Args:
        image_path: Path to the image file

    Returns:
        PIL Image object of the resized image
    """
    # Load the image
    img = load_image(image_path)
    if not img:
        return None

    # Get original dimensions
    original_width, original_height = img.size
    print(f"Original image dimensions: {original_width}x{original_height}")

    # Ask user for target dimensions
    print("Enter the target dimensions. Leave empty to keep original size.")
    print("To maintain aspect ratio, enter only width OR height, not both.")

    # Get width input
    width_input = input("Target width (px): ").strip()
    target_width = int(width_input) if width_input else None

    # Get height input
    height_input = input("Target height (px): ").strip()
    target_height = int(height_input) if height_input else None

    # Resize the image
    resized_img = resize_image(img, target_width, target_height)

    if resized_img:
        actual_width, actual_height = resized_img.size
        print(f"Image resized to: {actual_width}x{actual_height}")

    return resized_img


def run_cli():
    """Run the command-line interface for Pixeletica."""
    print("==== Pixeletica Minecraft Dithering ====")

    # Load block colors
    if not load_block_colors("./minecraft/block-colors.csv"):
        print("Error: Failed to load block colors from ./minecraft/block-colors.csv")
        return

    # Ask for image path
    image_path = input("Enter the path to your image: ").strip()

    # Check if file exists and load it
    img = load_image(image_path)
    if not img:
        print(f"Error: Could not load image '{image_path}'")
        return

    # Resize image
    resized_img = resize_image_interactive(image_path)
    if not resized_img:
        print("Error: Could not resize image")
        return

    # Select dithering algorithm
    print("\nSelect dithering algorithm:")
    print("1. No dithering")
    print("2. Floyd-Steinberg dithering")
    print("3. Ordered dithering")
    print("4. Random dithering")
    algorithm_choice = input("Enter your choice (1-4): ").strip()

    # Map user choice to algorithm name
    algorithm_map = {"1": "none", "2": "floyd_steinberg", "3": "ordered", "4": "random"}

    algorithm_name = algorithm_map.get(algorithm_choice, "floyd_steinberg")

    # Get dithering function and algorithm ID
    dither_func, algorithm_id = get_algorithm_by_name(algorithm_name)

    if not dither_func:
        print(
            f"Unknown algorithm selected. Using Floyd-Steinberg dithering as default."
        )
        dither_func, algorithm_id = get_algorithm_by_name("floyd_steinberg")

    # Apply selected dithering algorithm
    try:
        print(f"Applying {algorithm_id} dithering...")

        # Track processing time
        start_time = time.time()
        dithered_img, block_ids = dither_func(resized_img)
        processing_time = time.time() - start_time

        if not dithered_img:
            print("Error: Failed to apply dithering")
            return

        # Save the dithered image with metadata
        output_path = save_dithered_image(
            dithered_img,
            image_path,
            algorithm_id,
            block_ids=block_ids,
            processing_time=processing_time,
        )
        print(f"Success! Dithered image saved to: {output_path}")
        print(f"Processing took {processing_time:.2f} seconds")

        # Ask if the user wants to generate a schematic
        print("\nDo you want to generate a Litematica schematic? (y/n)")
        generate_schematic = input().strip().lower() == "y"

        if generate_schematic:
            # Get schematic metadata
            print("\n--- Schematic Metadata ---")
            print("Leave empty to use default values")

            author = input("Author [L3-N0X - pixeletica]: ").strip()
            if not author:
                author = "L3-N0X - pixeletica"

            schematic_name = input(
                f"Name [{os.path.splitext(os.path.basename(image_path))[0]}]: "
            ).strip()
            if not schematic_name:
                schematic_name = os.path.splitext(os.path.basename(image_path))[0]

            description = input("Description: ").strip()

            # Generate the schematic
            from pixeletica.schematic_generator import generate_schematic

            metadata = {
                "author": author,
                "name": schematic_name,
                "description": description,
            }

            try:
                schematic_path = generate_schematic(
                    block_ids, image_path, algorithm_id, metadata
                )
                print(f"Success! Schematic saved to: {schematic_path}")
            except Exception as e:
                print(f"Error generating schematic: {e}")

    except Exception as e:
        print(f"Error applying dithering: {e}")
