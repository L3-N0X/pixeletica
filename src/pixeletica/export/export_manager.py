"""
Export manager for processed images.

This module provides functionality for exporting processed Minecraft images in various formats,
handling web exports, single large images, and split images with or without lines.
"""

import os
import datetime
import json

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
        # self.base_export_dir = os.path.join(output_dir, "exports") # Removed unused base_export_dir

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        # os.makedirs(self.base_export_dir, exist_ok=True) # Removed unused base_export_dir creation

    def export_image(
        self,
        image,
        base_name,
        export_types=None,
        origin_x=0,
        origin_z=0,
        # Default flags, primarily used if version_options is None or for fallback
        draw_chunk_lines=False,
        chunk_line_color="FF0000FF",
        draw_block_lines=False,
        block_line_color="CCCCCC88",
        split_count=4,
        web_tile_size=512,
        algorithm_name="",
        version_options=None,  # Preferred way to specify line versions
        # Deprecated flags, kept for potential internal fallback logic but shouldn't be primary control
        include_lines_version=None,
        include_no_lines_version=None,
    ):
        """
        Export an image in the specified formats, handling multiple line versions.

        Args:
            image: PIL Image to export
            base_name: Base name for the exported files
            export_types: List of export types (web, large, split) or None to export all
            origin_x: X-coordinate of the world origin
            origin_z: Z-coordinate of the world origin
            draw_chunk_lines: Default flag if version_options is None
            chunk_line_color: Color for chunk lines (hex format)
            draw_block_lines: Default flag if version_options is None
            block_line_color: Color for block lines (hex format)
            split_count: Number of parts to split the image into
            web_tile_size: Size of web tiles (e.g., 512×512)
            algorithm_name: Name of the algorithm used to process the image
            version_options: Dictionary specifying which line versions to export (no_lines, block_lines, chunk_lines, both_lines)
            include_lines_version: Deprecated - use version_options instead
            include_no_lines_version: Deprecated - use version_options instead

        Returns:
            Dictionary containing the export results consolidated into a single structure.
        """
        # Use self.output_dir directly as the base export directory
        export_dir = self.output_dir
        os.makedirs(export_dir, exist_ok=True)  # Ensure root task dir exists

        # Export in the specified formats
        if export_types is None:
            export_types = [
                EXPORT_TYPE_LARGE
            ]  # Default to large export if none specified

        # Calculate offset information
        offset_info = calculate_image_offset(origin_x, origin_z)

        results = {
            "export_dir": str(export_dir),  # Store the root task dir path
            "timestamp": datetime.datetime.now().isoformat(),  # Use ISO format timestamp
            "coordinates": offset_info,
            "exports": {},
            "export_files": [],  # List to track all generated files for metadata
        }

        # --- Determine which line versions to generate based on version_options ---
        versions_to_generate = {}  # Key: folder_name, Value: (apply_chunk, apply_block)
        if version_options:
            if version_options.get("no_lines"):
                versions_to_generate["no_lines"] = (False, False)
            if version_options.get("only_block_lines"):
                versions_to_generate["block_lines"] = (False, True)
            if version_options.get("only_chunk_lines"):
                versions_to_generate["chunk_lines"] = (True, False)
            if version_options.get("both_lines"):
                versions_to_generate["both_lines"] = (True, True)
        else:
            # Fallback to old flags if version_options not provided or empty
            # Use provided include_ flags if they are not None, otherwise default to True/False
            _include_lines = (
                include_lines_version if include_lines_version is not None else True
            )
            _include_no_lines = (
                include_no_lines_version
                if include_no_lines_version is not None
                else False
            )

            if _include_no_lines:
                versions_to_generate["no_lines"] = (False, False)
            if _include_lines:
                # Determine which specific line version based on draw flags
                if draw_chunk_lines and draw_block_lines:
                    versions_to_generate["both_lines"] = (True, True)
                elif draw_chunk_lines:
                    versions_to_generate["chunk_lines"] = (True, False)
                elif draw_block_lines:
                    versions_to_generate["block_lines"] = (False, True)
                else:
                    versions_to_generate["no_lines"] = (
                        False,
                        False,
                    )  # Lines included, but none specified

        # Ensure at least one version is generated if none specified or derived
        if not versions_to_generate:
            versions_to_generate["no_lines"] = (False, False)  # Default to no_lines

        # Export each requested format
        for export_type in export_types:
            if export_type == EXPORT_TYPE_WEB:
                # Web exports (simplified structure with only tiles and metadata)
                from src.pixeletica.export.web_export import export_web_tiles

                # Web exports never have lines
                web_dir = os.path.join(export_dir, "web")
                # os.makedirs(web_dir, exist_ok=True) # web_export handles this

                # Export tiles using the simplified structure
                web_result = export_web_tiles(
                    image,
                    web_dir,  # Pass the web subdirectory path
                    tile_size=web_tile_size,
                    origin_x=origin_x,
                    origin_z=origin_z,
                )
                results["exports"]["web"] = web_result
                # Add web files to the list
                results["export_files"].append(
                    {"path": os.path.join(web_dir, "tile-data.json"), "category": "web"}
                )
                for tile_info in web_result.get("tiles", []):
                    results["export_files"].append(
                        {
                            "path": os.path.join(
                                export_dir, tile_info["filename"]
                            ),  # Path relative to task dir
                            "category": "web",
                        }
                    )

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
                    else:  # Default to no_lines if lines requested but none specified
                        folder_name = "no_lines"
                # If neither version is explicitly requested, default based on line flags
                elif not include_no_lines_version and not include_lines_version:
                    if draw_chunk_lines or draw_block_lines:
                        # Determine folder based on flags if include_lines_version was false
                        if draw_chunk_lines and draw_block_lines:
                            folder_name = "both_lines"
                        elif draw_chunk_lines:
                            folder_name = "chunk_lines"
                        elif draw_block_lines:
                            folder_name = "block_lines"
                        else:
                            folder_name = (
                                "no_lines"  # Should not happen if flags are true
                            )
                    else:
                        folder_name = "no_lines"  # Default if no lines requested at all

                if folder_name:
                    # Create the appropriate subfolder
                    line_type_dir = os.path.join(rendered_dir, folder_name)
                    os.makedirs(line_type_dir, exist_ok=True)

                    # Define base filename for this version
                    version_base_name = f"{base_name}_{folder_name}"

                    if folder_name == "no_lines":
                        # Export without lines
                        file_path = os.path.join(
                            line_type_dir, f"{version_base_name}.png"
                        )
                        image.save(file_path)
                        large_results["no_lines"] = file_path
                        results["export_files"].append(
                            {"path": file_path, "category": f"rendered/{folder_name}"}
                        )
                    else:
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
                        file_path = os.path.join(
                            line_type_dir, f"{version_base_name}.png"
                        )
                        with_lines_image.save(file_path)
                        large_results[folder_name] = file_path
                        results["export_files"].append(
                            {"path": file_path, "category": f"rendered/{folder_name}"}
                        )

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

                for folder_name, (
                    apply_chunk_lines,
                    apply_block_lines,
                ) in versions_to_generate.items():
                    line_type_dir = os.path.join(rendered_dir, folder_name)
                    os.makedirs(line_type_dir, exist_ok=True)
                    version_base_name = f"{base_name}_{folder_name}"

                    if folder_name == "no_lines":
                        image_to_split = image
                    else:
                        image_to_split = apply_lines_to_image(
                            image,
                            draw_chunk_lines=apply_chunk_lines,
                            chunk_line_color=chunk_line_color,
                            draw_block_lines=apply_block_lines,
                            block_line_color=block_line_color,
                            origin_x=origin_x,
                            origin_z=origin_z,
                        )

                    split_paths = split_image(
                        image_to_split,
                        line_type_dir,
                        version_base_name,  # Use versioned base name
                        split_count,
                        texture_manager=texture_manager,
                        use_simplified_naming=True,
                    )
                    split_results[folder_name] = split_paths
                    for p in split_paths:
                        results["export_files"].append(
                            {"path": p, "category": f"rendered/{folder_name}"}
                        )

                results["exports"]["split"] = split_results

        # Save metadata directly in the root output directory
        metadata_path = os.path.join(export_dir, "export_metadata.json")
        try:
            # Attempt to make the results JSON serializable
            serializable_results = json.loads(json.dumps(results, default=str))
            with open(metadata_path, "w") as f:
                json.dump(serializable_results, f, indent=2)
            results["export_files"].append(
                {"path": metadata_path, "category": "metadata"}
            )
        except TypeError as e:
            import logging

            logging.error(f"Failed to serialize export metadata: {e}")
            # Optionally save a simplified version or log the error more prominently
            simplified_results = {
                "error": "Failed to serialize full metadata",
                "details": str(e),
            }
            with open(metadata_path, "w") as f:
                json.dump(simplified_results, f, indent=2)

        return results


def export_processed_image(
    image,
    base_name,
    export_types=None,
    origin_x=0,
    origin_z=0,
    draw_chunk_lines=False,  # Default flag, used if version_options is None
    chunk_line_color="FF0000FF",
    draw_block_lines=False,  # Default flag, used if version_options is None
    block_line_color="CCCCCC88",
    split_count=4,
    web_tile_size=512,
    algorithm_name="",
    output_dir="./out",
    version_options=None,  # Preferred way to specify line versions
):
    """
    Convenience function for exporting processed images. Handles multiple line versions.

    Args:
        image: PIL Image to export
        base_name: Base name for the exported files
        export_types: List of export types (web, large, split) or None to export all
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin
        draw_chunk_lines: Default flag if version_options is None
        chunk_line_color: Color for chunk lines (hex format)
        draw_block_lines: Default flag if version_options is None
        block_line_color: Color for block lines (hex format)
        split_count: Number of parts to split the image into
        web_tile_size: Size of web tiles (e.g., 512×512)
        algorithm_name: Name of the algorithm used to process the image
        output_dir: Base directory for output files (should be the task root)
        version_options: Dictionary containing options for different versions of line rendering
            - no_lines: Export version with no lines
            - only_block_lines: Export version with only block grid lines
            - only_chunk_lines: Export version with only chunk lines
            - both_lines: Export version with both block and chunk lines

    Returns:
        Dictionary containing the export results consolidated into a single structure.
    """
    manager = ExportManager(output_dir=output_dir)

    # Call export_image once, passing version_options to handle line variations internally
    export_result = manager.export_image(
        image,
        base_name,  # Pass the original base_name
        export_types=export_types,
        origin_x=origin_x,
        origin_z=origin_z,
        # Pass default flags for fallback if version_options is None
        draw_chunk_lines=draw_chunk_lines,
        chunk_line_color=chunk_line_color,
        draw_block_lines=draw_block_lines,
        block_line_color=block_line_color,
        split_count=split_count,
        web_tile_size=web_tile_size,
        # Pass version_options directly
        version_options=version_options,
        # Deprecated flags are no longer needed here, handled by fallback in export_image
        algorithm_name=algorithm_name,
    )

    # The result from export_image already contains all generated versions
    return export_result
