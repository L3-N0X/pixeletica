"""
Command-line interface for Pixeletica.

This module provides different operating modes:
- GUI (default): A graphical user interface for interactive use
- API: A FastAPI-based API server for programmatic access
- Debug: A command-line interface for debugging purposes
"""

import os
import sys
import time
import argparse
import logging
from src.pixeletica.block_utils.block_loader import load_block_colors
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.image_ops import load_image, resize_image, save_dithered_image


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
    """
    Run the command-line interface for Pixeletica.

    This function is kept as a fallback for debugging purposes.
    The main application now uses GUI by default.
    """
    print("==== Pixeletica Minecraft Dithering (DEBUG MODE) ====")
    print("Note: This CLI interface is maintained for debugging purposes only.")
    print("For normal use, please use the GUI interface.\n")

    # Load block colors
    if not load_block_colors("./src/minecraft/block-colors.csv"):
        print(
            "Error: Failed to load block colors from ./src/minecraft/block-colors.csv"
        )
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

        # Ask if the user wants to export the image with textures
        print("\nDo you want to export the image with Minecraft textures? (y/n)")
        export_image = input().strip().lower() == "y"

        if export_image:
            # Get export options
            print("\n--- Image Export Options ---")

            # Coordinate settings
            print("\n--- Coordinate Settings ---")
            print(
                "Enter the starting coordinates in the Minecraft world (Leave empty for 0,0)"
            )
            origin_x_input = input("Origin X: ").strip()
            origin_z_input = input("Origin Z: ").strip()

            origin_x = int(origin_x_input) if origin_x_input else 0
            origin_z = int(origin_z_input) if origin_z_input else 0

            print("\n--- Line Rendering Options ---")
            print("Do you want to include chunk lines? (y/n)")
            draw_chunk_lines = input().strip().lower() == "y"

            chunk_line_color = "FF0000FF"  # Default: Red
            if draw_chunk_lines:
                print(
                    "Chunk line color [FF0000FF] (RRGGBBAA format, leave empty for default): "
                )
                color_input = input().strip()
                if color_input:
                    chunk_line_color = color_input

            print("Do you want to include block grid lines? (y/n)")
            draw_block_lines = input().strip().lower() == "y"

            block_line_color = "CCCCCC88"  # Default: Light gray
            if draw_block_lines:
                print(
                    "Block line color [CCCCCC88] (RRGGBBAA format, leave empty for default): "
                )
                color_input = input().strip()
                if color_input:
                    block_line_color = color_input

            print("\n--- Export Types ---")
            print("Select export types (you can choose multiple):")
            print("1. Web-optimized tiles (512×512)")
            print("2. Single large image")
            print("3. Split into multiple parts")

            export_types = []

            web_export = input("Export as web tiles? (y/n): ").strip().lower() == "y"
            if web_export:
                export_types.append("web")

            large_export = (
                input("Export as single large image? (y/n): ").strip().lower() == "y"
            )
            if large_export:
                export_types.append("large")

            split_export = (
                input("Export as split parts? (y/n): ").strip().lower() == "y"
            )
            if split_export:
                export_types.append("split")
                print("Number of parts to split into [4]: ")
                split_count_input = input().strip()
                split_count = int(split_count_input) if split_count_input else 4
            else:
                split_count = 4

            print("\n--- Line Version Options ---")
            print("Which versions would you like to export?")
            with_lines = input("Version with lines? (y/n): ").strip().lower() == "y"
            without_lines = (
                input("Version without lines? (y/n): ").strip().lower() == "y"
            )

            if not with_lines and not without_lines:
                print(
                    "You must select at least one version. Using 'with lines' by default."
                )
                with_lines = True

            # Render blocks with textures
            from src.pixeletica.rendering.block_renderer import (
                render_blocks_from_block_ids,
            )

            print("Rendering blocks with textures...")
            block_image = render_blocks_from_block_ids(block_ids)

            if block_image:
                # Export the images
                from src.pixeletica.export.export_manager import export_processed_image

                print("Exporting images...")
                try:
                    export_results = export_processed_image(
                        block_image,
                        os.path.splitext(os.path.basename(image_path))[0],
                        export_types=export_types,
                        origin_x=origin_x,
                        origin_z=origin_z,
                        draw_chunk_lines=draw_chunk_lines,
                        chunk_line_color=chunk_line_color,
                        draw_block_lines=draw_block_lines,
                        block_line_color=block_line_color,
                        split_count=split_count,
                        include_lines_version=with_lines,
                        include_no_lines_version=without_lines,
                        algorithm_name=algorithm_id,
                    )

                    print(
                        f"\nExport successful! Files saved to: {export_results['export_dir']}"
                    )

                    # Update metadata with export information
                    metadata_path = os.path.splitext(output_path)[0] + ".json"
                    if os.path.exists(metadata_path):
                        from src.pixeletica.metadata import (
                            load_metadata_json,
                            save_metadata_json,
                        )

                        metadata = load_metadata_json(metadata_path)
                        metadata["export_settings"] = {
                            "origin_x": origin_x,
                            "origin_z": origin_z,
                            "draw_chunk_lines": draw_chunk_lines,
                            "chunk_line_color": chunk_line_color,
                            "draw_block_lines": draw_block_lines,
                            "block_line_color": block_line_color,
                            "export_types": export_types,
                            "split_count": split_count,
                        }
                        metadata["exports"] = export_results
                        save_metadata_json(metadata, output_path)
                except Exception as e:
                    print(f"Error during export: {e}")
            else:
                print("Error: Failed to render blocks with textures")

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
            from src.pixeletica.schematic_generator import generate_schematic

            metadata = {
                "author": author,
                "name": schematic_name,
                "description": description,
            }

            try:
                schematic_path = generate_schematic(
                    block_ids,
                    image_path,
                    algorithm_id,
                    metadata,
                    origin_x=origin_x,
                    origin_z=origin_z,
                )
                print(f"Success! Schematic saved to: {schematic_path}")
            except Exception as e:
                print(f"Error generating schematic: {e}")

    except Exception as e:
        print(f"Error applying dithering: {e}")


def run_api_server():
    """
    Start the Pixeletica API server.

    This function starts a FastAPI server for programmatic access to Pixeletica.
    """
    # Import and run the API server
    from src.pixeletica.api.main import start_api

    start_api()


def main():
    """
    Main entry point for Pixeletica with command-line argument parsing.
    """
    parser = argparse.ArgumentParser(
        description="Pixeletica Minecraft block art generator"
    )

    # Add command-line arguments
    parser.add_argument(
        "--mode",
        choices=["gui", "api", "debug"],
        default="gui",
        help="Operating mode: gui (default), api (server), or debug (command-line)",
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the API server to (only applicable in API mode)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the API server to (only applicable in API mode)",
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Logging level",
    )

    # Parse arguments
    args = parser.parse_args()

    # Configure logging
    numeric_level = getattr(logging, args.log_level.upper(), None)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Set environment variables for API mode if specified
    if args.mode == "api":
        os.environ["PIXELETICA_API_HOST"] = args.host
        os.environ["PIXELETICA_API_PORT"] = str(args.port)

    # Run the selected mode
    if args.mode == "gui":
        # Import GUI-related modules only when needed
        from src.pixeletica.gui.app import DitherApp
        import tkinter as tk

        # Start the GUI
        root = tk.Tk()
        app = DitherApp(root)
        root.mainloop()
    elif args.mode == "api":
        # Start the API server
        run_api_server()
    elif args.mode == "debug":
        # Run the debug CLI
        run_cli()
    else:
        # Should never happen due to argparse choices
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
