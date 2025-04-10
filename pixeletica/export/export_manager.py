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

from pixeletica.rendering.line_renderer import apply_lines_to_image
from pixeletica.coordinates.chunk_calculator import calculate_image_offset

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

        # Create export directory
        export_dir = os.path.join(self.base_export_dir, export_name)
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
                # Web exports (tile-based for web viewer)
                from pixeletica.export.web_export import export_web_tiles

                # Web exports never have lines
                web_dir = os.path.join(export_dir, f"web_{base_name}")
                web_result = export_web_tiles(
                    image,
                    web_dir,
                    tile_size=web_tile_size,
                    origin_x=origin_x,
                    origin_z=origin_z,
                )
                results["exports"]["web"] = web_result

            elif export_type == EXPORT_TYPE_LARGE:
                # Large single image
                large_dir = os.path.join(export_dir, "large")
                os.makedirs(large_dir, exist_ok=True)

                # Export versions with and without lines
                large_results = {}

                if include_no_lines_version:
                    # Export without lines
                    no_lines_path = os.path.join(large_dir, f"{base_name}_no_lines.png")
                    image.save(no_lines_path)
                    large_results["no_lines"] = no_lines_path

                if include_lines_version:
                    # Export with lines
                    with_lines_image = apply_lines_to_image(
                        image,
                        draw_chunk_lines=draw_chunk_lines,
                        chunk_line_color=chunk_line_color,
                        draw_block_lines=draw_block_lines,
                        block_line_color=block_line_color,
                        origin_x=origin_x,
                        origin_z=origin_z,
                    )
                    with_lines_path = os.path.join(
                        large_dir, f"{base_name}_with_lines.png"
                    )
                    with_lines_image.save(with_lines_path)
                    large_results["with_lines"] = with_lines_path

                results["exports"]["large"] = large_results

            elif export_type == EXPORT_TYPE_SPLIT:
                # Split into N equal parts
                from pixeletica.export.image_splitter import split_image

                split_dir = os.path.join(export_dir, f"split_{split_count}")
                os.makedirs(split_dir, exist_ok=True)

                split_results = {}

                if include_no_lines_version:
                    # Split without lines
                    no_lines_paths = split_image(
                        image, split_dir, f"{base_name}_no_lines", split_count
                    )
                    split_results["no_lines"] = no_lines_paths

                if include_lines_version:
                    # Split with lines
                    with_lines_image = apply_lines_to_image(
                        image,
                        draw_chunk_lines=draw_chunk_lines,
                        chunk_line_color=chunk_line_color,
                        draw_block_lines=draw_block_lines,
                        block_line_color=block_line_color,
                        origin_x=origin_x,
                        origin_z=origin_z,
                    )
                    with_lines_paths = split_image(
                        with_lines_image,
                        split_dir,
                        f"{base_name}_with_lines",
                        split_count,
                    )
                    split_results["with_lines"] = with_lines_paths

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
):
    """
    Convenience function for exporting processed images.

    Args:
        (Same as ExportManager.export_image)

    Returns:
        Dictionary containing the export results
    """
    manager = ExportManager(output_dir=output_dir)
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
