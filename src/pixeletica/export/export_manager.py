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

import logging

logger = logging.getLogger("pixeletica.export.export_manager")

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
        progress_callback=None,
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
            progress_callback: Function to report progress (percentage, export type)

        Returns:
            Dictionary containing the export results consolidated into a single structure.
        """
        # Initialize progress tracking for export types
        total_types = len(export_types) if export_types else 0
        processed_types = 0
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

                # Define fine-grained progress callback for web files
                def web_progress_callback(percent, info):
                    # Map web progress (0-100) to 40% of total pipeline (per roadmap)
                    # The web_files step is assumed to be 40% of the total pipeline progress.
                    # If progress_callback is provided, call it with mapped percentage and step name.
                    if progress_callback:
                        # The web_files step starts at 60% and ends at 100% (if following the roadmap)
                        # So: mapped = 60 + percent * 0.4
                        mapped = 60 + (percent * 0.4)
                        mapped = min(100, max(0, mapped))
                        progress_callback(mapped, "web_files")

                # Export tiles using the simplified structure
                web_result = export_web_tiles(
                    image,
                    web_dir,  # Pass the web subdirectory path
                    tile_size=web_tile_size,
                    origin_x=origin_x,
                    origin_z=origin_z,
                    progress_callback=web_progress_callback,
                )
                # web_result now contains the detailed metadata including zoom_levels with tiles_x/tiles_z

                # --- Construct and save the lean export_metadata.json for the API ---
                lean_metadata = {
                    "id": base_name,  # Assuming base_name is the task_id
                    "name": f"Map {base_name[:8]}",
                    "created": datetime.datetime.now().isoformat(),
                    "description": None,  # Add later if needed
                    "width": web_result.get("width"),
                    "height": web_result.get("height"),
                    "origin_x": web_result.get("origin_x"),
                    "origin_z": web_result.get("origin_z"),
                    "tileSize": web_result.get(
                        "tile_size"
                    ),  # Rename for frontend consistency
                    "maxZoom": web_result.get(
                        "max_zoom"
                    ),  # Rename for frontend consistency
                    "minZoom": web_result.get(
                        "min_zoom"
                    ),  # Rename for frontend consistency
                    "tileFormat": "png",  # Assuming PNG, adjust if format varies
                    "zoomLevels": [  # Extract only necessary zoom level info
                        {
                            "zoomLevel": zl.get("zoomLevel"),
                            "tiles_x": zl.get("tiles_x"),
                            "tiles_z": zl.get("tiles_z"),
                        }
                        for zl in web_result.get("zoom_levels", [])
                    ],
                    # Add other relevant top-level info if needed
                    "dithering_algorithm": algorithm_name,
                    # "color_palette": "minecraft", # Add if available/relevant
                }

                export_metadata_path = os.path.join(export_dir, "export_metadata.json")
                try:
                    with open(export_metadata_path, "w") as f:
                        json.dump(lean_metadata, f, indent=2)
                    logger.info(
                        f"Saved lean web export metadata to {export_metadata_path}"
                    )
                    results["export_files"].append(
                        {"path": export_metadata_path, "category": "metadata"}
                    )
                except Exception as e:
                    logger.error(f"Failed to save lean export metadata: {e}")

                # Keep track of the detailed tile-data.json path as well
                detailed_metadata_path = os.path.join(web_dir, "tile-data.json")
                results["export_files"].append(
                    {"path": detailed_metadata_path, "category": "web_detailed"}
                )
                # Add individual tile files to export_files (optional, could be large)
                # for zoom_level in web_result.get("zoom_levels", []):
                #     for tile_info in zoom_level.get("tiles", []):
                #         results["export_files"].append(
                #             {
                #                 "path": os.path.join(web_dir, tile_info["filename"]),
                #                 "category": "web_tile",
                #             }
                #         )

                # Store the lean metadata in the main results dict for potential immediate use?
                # results["exports"]["web_summary"] = lean_metadata # Optional

                # report web export progress as 100% at the end (for safety)
                processed_types += 1
                if progress_callback:
                    progress_callback(100, "web_files")

            elif export_type == EXPORT_TYPE_LARGE:
                # Large single image - organized by line type
                rendered_dir = os.path.join(export_dir, "rendered")
                os.makedirs(rendered_dir, exist_ok=True)

                # Export versions based directly on versions_to_generate
                large_results = {}
                for folder_name, (
                    apply_chunk_lines,
                    apply_block_lines,
                ) in versions_to_generate.items():
                    # Create the appropriate subfolder
                    line_type_dir = os.path.join(rendered_dir, folder_name)
                    os.makedirs(line_type_dir, exist_ok=True)

                    # Define base filename for this version
                    version_base_name = f"{base_name}_{folder_name}"

                    if folder_name == "no_lines":
                        # Export without lines
                        image_to_save = image
                    else:
                        # Apply appropriate lines based on the version being generated
                        image_to_save = apply_lines_to_image(
                            image,
                            draw_chunk_lines=apply_chunk_lines,
                            chunk_line_color=chunk_line_color,
                            draw_block_lines=apply_block_lines,
                            block_line_color=block_line_color,
                            origin_x=origin_x,
                            origin_z=origin_z,
                        )

                    # Save the image
                    file_path = os.path.join(line_type_dir, f"{version_base_name}.png")
                    image_to_save.save(file_path)
                    large_results[folder_name] = file_path
                    results["export_files"].append(
                        {
                            "path": file_path,
                            "category": "rendered",
                        }  # Use top-level category
                    )

                results["exports"]["large"] = large_results
                # report large export progress
                processed_types += 1
                if progress_callback:
                    progress_callback(int(processed_types / total_types * 100), "large")

            elif export_type == EXPORT_TYPE_SPLIT:
                # Split into N equal parts - organized by line type subfolder
                from src.pixeletica.export.image_splitter import split_image

                # Create a properly configured texture manager for consistent rendering
                from src.pixeletica.rendering.texture_loader import (
                    TextureManager,
                    DEFAULT_TEXTURE_PATH,
                )

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
                            {
                                "path": p,
                                "category": "rendered",
                            }  # Use top-level category
                        )

                results["exports"]["split"] = split_results
                # report split export progress
                processed_types += 1
                if progress_callback:
                    progress_callback(int(processed_types / total_types * 100), "split")

        # Save metadata directly in the root output directory
        metadata_path = os.path.join(export_dir, "export_metadata.json")
        try:
            # Attempt to make the *overall* results JSON serializable
            # Note: We already saved the specific lean web metadata above.
            # This saves the consolidated results of *all* export types.
            serializable_results = json.loads(json.dumps(results, default=str))
            with open(metadata_path, "w") as f:
                json.dump(serializable_results, f, indent=2)
            # Don't add metadata_path again if it's the same as export_metadata_path
            if metadata_path not in [f["path"] for f in results["export_files"]]:
                results["export_files"].append(
                    {"path": metadata_path, "category": "consolidated_metadata"}
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
    progress_callback=None,
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
        progress_callback: Function to report progress (percentage, export type)

    Returns:
        Dictionary containing the export results consolidated into a single structure.
    """
    manager = ExportManager(output_dir=output_dir)

    # Call export_image once, passing version_options to handle line variations internally
    export_result = manager.export_image(
        image,
        base_name,  # Pass the original base_name
        export_types=export_types,
        # pass progress_callback for export progress
        progress_callback=progress_callback,
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
