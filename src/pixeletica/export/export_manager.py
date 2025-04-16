"""
Export manager for processed images.

This module provides functionality for exporting processed Minecraft images in various formats,
handling web exports, single large images, and split images with or without lines.
"""

import os
import datetime
import json
from PIL import Image
from pathlib import Path

from src.pixeletica.rendering.line_renderer import apply_lines_to_image
from src.pixeletica.coordinates.chunk_calculator import calculate_image_offset

# Export settings constants
EXPORT_TYPE_WEB = "web"
EXPORT_TYPE_LARGE = "large"
EXPORT_TYPE_SPLIT = "split"


class ExportManager:
    """
    Manages the export of processed Minecraft images in various formats.
    """

    def __init__(self, output_dir="./out"):
        """
        Initialize the export manager.

        Args:
            output_dir: Base directory for output files
        """
        self.output_dir = output_dir
        self.base_export_dir = os.path.join(output_dir, "exports")

        # Ensure output directories exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.base_export_dir, exist_ok=True)

    def export_image(
        self,
        image,
        base_name,
        export_types=None,
        origin_x=0,
        origin_z=0,
        draw_chunk_lines=False,
        chunk_line_color="FF0000FF",
        draw_block_lines=False,
        block_line_color="CCCCCC88",
        split_count=4,
        web_tile_size=512,
        include_lines_version=True,
        include_no_lines_version=False,
        algorithm_name="",
    ):
        """
        Export an image in the specified formats.

        Args:
            image: PIL Image to export
            base_name: Base name for the exported files
            export_types: List of export types (web, large, split) or None to export all
            origin_x: X-coordinate of the world origin
            origin_z: Z-coordinate of the world origin
            draw_chunk_lines: Whether to draw chunk lines on exported images
            chunk_line_color: Color for chunk lines (hex format)
            draw_block_lines: Whether to draw block grid lines on exported images
            block_line_color: Color for block lines (hex format)
            split_count: Number of parts to split the image into
            web_tile_size: Size of web tiles (e.g., 512×512)
            include_lines_version: Whether to include versions with lines
            include_no_lines_version: Whether to include versions without lines
            algorithm_name: Name of the algorithm used to process the image

        Returns:
            Dictionary containing the export results
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_name = (
            f"{base_name}_{algorithm_name}_{timestamp}"
            if algorithm_name
            else f"{base_name}_{timestamp}"
        )

        # Create export directory - directly in the output_dir rather than in exports/
        export_dir = os.path.join(self.output_dir, export_name)
        os.makedirs(export_dir, exist_ok=True)

        # Export in the specified formats
        if export_types is None:
            export_types = [EXPORT_TYPE_LARGE]

        # Calculate offset information
        offset_info = calculate_image_offset(origin_x, origin_z)

        results = {
            "export_dir": export_dir,
            "timestamp": timestamp,
            "coordinates": offset_info,
            "exports": {},
        }

        # Export each requested format
        for export_type in export_types:
            if export_type == EXPORT_TYPE_WEB:
                # Web exports (simplified structure with only tiles and metadata)
                from src.pixeletica.export.web_export import export_web_tiles

                # Web exports never have lines
                web_dir = os.path.join(export_dir, "web")
                os.makedirs(web_dir, exist_ok=True)

                # Export tiles using the simplified structure
                web_result = export_web_tiles(
                    image,
                    web_dir,
                    tile_size=web_tile_size,
                    origin_x=origin_x,
                    origin_z=origin_z,
                )
                results["exports"]["web"] = web_result

            elif export_type == EXPORT_TYPE_LARGE:
                # Large single image - organized by line type
                rendered_dir = os.path.join(export_dir, "rendered")
                os.makedirs(rendered_dir, exist_ok=True)

                # Export versions with and without lines
                large_results = {}

                # Determine the appropriate subfolder based on line settings
                folder_name = None
                if include_no_lines_version and not include_lines_version:
                    folder_name = "no_lines"
                elif include_lines_version:
                    if draw_chunk_lines and draw_block_lines:
                        folder_name = "both_lines"
                    elif draw_chunk_lines:
                        folder_name = "chunk_lines"
                    elif draw_block_lines:
                        folder_name = "block_lines"
                    else:
                        folder_name = "no_lines"

                if folder_name:
                    # Create the appropriate subfolder
                    line_type_dir = os.path.join(rendered_dir, folder_name)
                    os.makedirs(line_type_dir, exist_ok=True)

                    if include_no_lines_version and folder_name == "no_lines":
                        # Export without lines
                        file_path = os.path.join(line_type_dir, f"{base_name}.png")
                        image.save(file_path)
                        large_results["no_lines"] = file_path

                    if include_lines_version and folder_name != "no_lines":
                        # Apply appropriate lines based on folder name
                        apply_chunk_lines = folder_name in ["chunk_lines", "both_lines"]
                        apply_block_lines = folder_name in ["block_lines", "both_lines"]

                        with_lines_image = apply_lines_to_image(
                            image,
                            draw_chunk_lines=apply_chunk_lines,
                            chunk_line_color=chunk_line_color,
                            draw_block_lines=apply_block_lines,
                            block_line_color=block_line_color,
                            origin_x=origin_x,
                            origin_z=origin_z,
                        )
                        file_path = os.path.join(line_type_dir, f"{base_name}.png")
                        with_lines_image.save(file_path)
                        large_results[folder_name] = file_path

                results["exports"]["large"] = large_results

            elif export_type == EXPORT_TYPE_SPLIT:
                # Split into N equal parts - organize by line type subfolder
                from src.pixeletica.export.image_splitter import split_image

                # Create a properly configured texture manager for consistent rendering
                from src.pixeletica.rendering.texture_loader import (
                    TextureManager,
                    DEFAULT_TEXTURE_PATH,
                )
                import logging

                logger = logging.getLogger("pixeletica.export.export_manager")
                texture_path = os.path.abspath(DEFAULT_TEXTURE_PATH)
                logger.info(
                    f"Creating TextureManager with absolute path: {texture_path}"
                )
                texture_manager = TextureManager(texture_path)

                # Create main rendered directory
                rendered_dir = os.path.join(export_dir, "rendered")
                os.makedirs(rendered_dir, exist_ok=True)

                split_results = {}

                # Determine line type subfolder based on settings (similar to LARGE export)
                folder_name = None
                if include_no_lines_version and not include_lines_version:
                    folder_name = "no_lines"
                elif include_lines_version:
                    if draw_chunk_lines and draw_block_lines:
                        folder_name = "both_lines"
                    elif draw_chunk_lines:
                        folder_name = "chunk_lines"
                    elif draw_block_lines:
                        folder_name = "block_lines"
                    else:
                        folder_name = "no_lines"

                if folder_name:
                    # Create the appropriate subfolder
                    line_type_dir = os.path.join(rendered_dir, folder_name)
                    os.makedirs(line_type_dir, exist_ok=True)

                    if include_no_lines_version and folder_name == "no_lines":
                        # Split without lines
                        no_lines_paths = split_image(
                            image,
                            line_type_dir,
                            base_name,
                            split_count,
                            texture_manager=texture_manager,
                            use_simplified_naming=True,
                        )
                        split_results["no_lines"] = no_lines_paths

                    if include_lines_version and folder_name != "no_lines":
                        # Apply appropriate lines based on folder name
                        apply_chunk_lines = folder_name in ["chunk_lines", "both_lines"]
                        apply_block_lines = folder_name in ["block_lines", "both_lines"]

                        # Apply lines to the image
                        with_lines_image = apply_lines_to_image(
                            image,
                            draw_chunk_lines=apply_chunk_lines,
                            chunk_line_color=chunk_line_color,
                            draw_block_lines=apply_block_lines,
                            block_line_color=block_line_color,
                            origin_x=origin_x,
                            origin_z=origin_z,
                        )

                        # Split the image with lines
                        with_lines_paths = split_image(
                            with_lines_image,
                            line_type_dir,
                            base_name,
                            split_count,
                            texture_manager=texture_manager,
                            use_simplified_naming=True,
                        )
                        split_results[folder_name] = with_lines_paths

                results["exports"]["split"] = split_results

        # Save metadata
        metadata_path = os.path.join(export_dir, "export_metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(results, f, indent=2)

        return results


def export_processed_image(
    image,
    base_name,
    export_types=None,
    origin_x=0,
    origin_z=0,
    draw_chunk_lines=False,
    chunk_line_color="FF0000FF",
    draw_block_lines=False,
    block_line_color="CCCCCC88",
    split_count=4,
    web_tile_size=512,
    include_lines_version=True,
    include_no_lines_version=False,
    algorithm_name="",
    output_dir="./out",
    version_options=None,
):
    """
    Convenience function for exporting processed images.

    Args:
        (Same as ExportManager.export_image)
        version_options: Dictionary containing options for different versions of line rendering
            - no_lines: Export version with no lines
            - only_block_lines: Export version with only block grid lines
            - only_chunk_lines: Export version with only chunk lines
            - both_lines: Export version with both block and chunk lines

    Returns:
        Dictionary containing the export results
    """
    manager = ExportManager(output_dir=output_dir)
    export_results = {}

    # Process all requested line versions
    if version_options:
        # Export with no lines if requested
        if version_options.get("no_lines", False):
            no_lines_result = manager.export_image(
                image,
                f"{base_name}_no_lines",
                export_types=export_types,
                origin_x=origin_x,
                origin_z=origin_z,
                draw_chunk_lines=False,
                chunk_line_color=chunk_line_color,
                draw_block_lines=False,
                block_line_color=block_line_color,
                split_count=split_count,
                web_tile_size=web_tile_size,
                include_lines_version=False,
                include_no_lines_version=True,
                algorithm_name=algorithm_name,
            )
            export_results["no_lines"] = no_lines_result

        # Export with only block lines
        if version_options.get("only_block_lines", False):
            block_lines_result = manager.export_image(
                image,
                f"{base_name}_block_lines",
                export_types=export_types,
                origin_x=origin_x,
                origin_z=origin_z,
                draw_chunk_lines=False,
                chunk_line_color=chunk_line_color,
                draw_block_lines=True,
                block_line_color=block_line_color,
                split_count=split_count,
                web_tile_size=web_tile_size,
                include_lines_version=True,
                include_no_lines_version=False,
                algorithm_name=algorithm_name,
            )
            export_results["block_lines"] = block_lines_result

        # Export with only chunk lines
        if version_options.get("only_chunk_lines", False):
            chunk_lines_result = manager.export_image(
                image,
                f"{base_name}_chunk_lines",
                export_types=export_types,
                origin_x=origin_x,
                origin_z=origin_z,
                draw_chunk_lines=True,
                chunk_line_color=chunk_line_color,
                draw_block_lines=False,
                block_line_color=block_line_color,
                split_count=split_count,
                web_tile_size=web_tile_size,
                include_lines_version=True,
                include_no_lines_version=False,
                algorithm_name=algorithm_name,
            )
            export_results["chunk_lines"] = chunk_lines_result

        # Export with both line types
        if version_options.get("both_lines", False):
            both_lines_result = manager.export_image(
                image,
                f"{base_name}_both_lines",
                export_types=export_types,
                origin_x=origin_x,
                origin_z=origin_z,
                draw_chunk_lines=True,
                chunk_line_color=chunk_line_color,
                draw_block_lines=True,
                block_line_color=block_line_color,
                split_count=split_count,
                web_tile_size=web_tile_size,
                include_lines_version=True,
                include_no_lines_version=False,
                algorithm_name=algorithm_name,
            )
            export_results["both_lines"] = both_lines_result

        # If no specific options were selected, use the fallback approach
        if not export_results:
            return_result = manager.export_image(
                image,
                base_name,
                export_types=export_types,
                origin_x=origin_x,
                origin_z=origin_z,
                draw_chunk_lines=draw_chunk_lines,
                chunk_line_color=chunk_line_color,
                draw_block_lines=draw_block_lines,
                block_line_color=block_line_color,
                split_count=split_count,
                web_tile_size=web_tile_size,
                include_lines_version=include_lines_version,
                include_no_lines_version=include_no_lines_version,
                algorithm_name=algorithm_name,
            )
            return return_result

        # Combine and return all results
        if len(export_results) == 1:
            return list(export_results.values())[0]

        # Combine multiple export results
        combined_result = {
            "export_dir": next(iter(export_results.values()))["export_dir"],
            "timestamp": next(iter(export_results.values()))["timestamp"],
            "coordinates": next(iter(export_results.values()))["coordinates"],
            "version_exports": export_results,
        }
        return combined_result

    # Legacy path when no version_options are provided
    else:
        # Log the export settings
        import logging

        logging.info(
            f"Exporting image with settings: draw_chunk_lines={draw_chunk_lines}, "
            f"draw_block_lines={draw_block_lines}, "
            f"include_lines_version={include_lines_version}, "
            f"include_no_lines_version={include_no_lines_version}"
        )

        return manager.export_image(
            image,
            base_name,
            export_types=export_types,
            origin_x=origin_x,
            origin_z=origin_z,
            draw_chunk_lines=draw_chunk_lines,
            chunk_line_color=chunk_line_color,
            draw_block_lines=draw_block_lines,
            block_line_color=block_line_color,
            split_count=split_count,
            web_tile_size=web_tile_size,
            include_lines_version=include_lines_version,
            include_no_lines_version=include_no_lines_version,
            algorithm_name=algorithm_name,
        )
