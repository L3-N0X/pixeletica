"""
Shared image processing logic for Pixeletica.

This module centralizes the core conversion process:
1. Applying dithering to map image pixels to Minecraft block colors and get block IDs.
2. Rendering the final image using Minecraft block textures based on the block IDs.
"""

import inspect
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from src.pixeletica.block_utils.block_loader import get_block_colors, load_block_colors
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.rendering.block_renderer import render_blocks_from_block_ids
from src.pixeletica.rendering.texture_loader import (
    DEFAULT_TEXTURE_PATH,
    TextureManager,
)

# Set up logging
logger = logging.getLogger("pixeletica.processing.converter")

# Global texture manager instance to avoid reloading textures repeatedly
_texture_manager = None


def _get_texture_manager():
    """Get or create a global TextureManager instance."""
    global _texture_manager
    if _texture_manager is None:
        texture_path = os.path.abspath(DEFAULT_TEXTURE_PATH)
        logger.info(f"Initializing global TextureManager with path: {texture_path}")
        _texture_manager = TextureManager(texture_path)
    return _texture_manager


def process_image_to_blocks(
    image: Image.Image,
    algorithm_name: str,
    color_palette: str = "minecraft",
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Processes an image by applying dithering and rendering with block textures.

    Args:
        image: Input PIL Image object.
        algorithm_name: Name of the dithering algorithm to use (e.g., "floyd_steinberg").
        color_palette: Name of the color palette to use ("minecraft" or "minecraft-2024").
        progress_callback: Optional function to report progress (percentage, step_name).

    Returns:
        A dictionary containing:
        - 'rendered_image': PIL Image rendered with block textures.
        - 'dithered_image': PIL Image dithered with block colors.
        - 'block_ids': 2D list of Minecraft block IDs (e.g., "minecraft:stone").
        - 'block_data': Dictionary containing 'blocks' (mapping short ID to block details)
                        and 'matrix' (2D list of short IDs).
        - 'processing_time_dither': Time taken for dithering (seconds).
        - 'processing_time_render': Time taken for rendering (seconds).

    Raises:
        ValueError: If the algorithm is unknown or block colors fail to load.
        Exception: For other processing errors.
    """
    start_total_time = time.time()

    def _report_progress(percent: int, step: str):
        if progress_callback:
            progress_callback(percent, step)

    _report_progress(0, "Starting processing")

    # --- 1. Load Block Colors ---
    _report_progress(5, "Loading block colors")
    if color_palette == "minecraft-2024":
        csv_path = "./src/minecraft/block-colors-2024.csv"
    else:
        csv_path = "./src/minecraft/block-colors-2025.csv"  # Default to 2025

    logger.info(f"Loading block colors from {csv_path} for palette '{color_palette}'")
    if not load_block_colors(csv_path):
        raise ValueError(f"Failed to load block colors from {csv_path}")
    _report_progress(10, "Block colors loaded")

    # --- 2. Apply Dithering ---
    _report_progress(15, f"Applying dithering: {algorithm_name}")
    dither_func, _ = get_algorithm_by_name(algorithm_name)
    if not dither_func:
        raise ValueError(f"Unknown dithering algorithm: {algorithm_name}")

    start_dither_time = time.time()
    dithered_image = None
    block_ids = None

    # Check if the dither function accepts a progress callback
    dither_func_params = inspect.signature(dither_func).parameters
    if "progress_callback" in dither_func_params:

        def dither_progress_wrapper(sub_progress):
            # Scale sub-progress (0-100) to fit within the dithering step (15% to 65%)
            overall_progress = 15 + int(sub_progress * 0.50)
            _report_progress(overall_progress, "Dithering")

        dithered_image, block_ids = dither_func(
            image, progress_callback=dither_progress_wrapper
        )
    else:
        # If no callback, estimate progress
        _report_progress(40, "Dithering")  # Estimate midpoint
        dithered_image, block_ids = dither_func(image)

    processing_time_dither = time.time() - start_dither_time
    _report_progress(65, "Dithering complete")
    logger.info(f"Dithering took {processing_time_dither:.2f} seconds.")

    if dithered_image is None or block_ids is None:
        raise RuntimeError("Dithering function failed to return image or block IDs.")

    # --- 3. Generate Block Data (Short IDs and Matrix) ---
    _report_progress(66, "Generating block data mapping")
    start_blockdata_time = time.time()

    # Find unique block IDs used in the image
    unique_mc_ids = set()
    for row in block_ids:
        unique_mc_ids.update(row)

    # Get all available block details
    all_blocks_details = get_block_colors()
    if not all_blocks_details:
        raise RuntimeError("Failed to retrieve loaded block colors for mapping.")

    # Create mapping from Minecraft ID to details for faster lookup
    mc_id_to_details = {block["id"]: block for block in all_blocks_details}

    # Create the 'blocks' dictionary mapping short ID to details
    block_map_short_id_to_details: Dict[int, Dict[str, Any]] = {}
    block_map_mc_id_to_short_id: Dict[str, int] = {}
    short_id_counter = 0
    for mc_id in sorted(list(unique_mc_ids)):  # Sort for consistent short ID assignment
        if mc_id in mc_id_to_details:
            details = mc_id_to_details[mc_id]
            block_map_short_id_to_details[short_id_counter] = {
                "name": details["name"],
                "minecraft_id": details["id"],  # Use a distinct key
                "hex": details["hex"],
                "rgb": details["rgb"],
            }
            block_map_mc_id_to_short_id[mc_id] = short_id_counter
            short_id_counter += 1
        else:
            logger.warning(
                f"Minecraft ID '{mc_id}' found in dithered result but not in loaded block colors. Skipping."
            )

    # Create the 'matrix' of short IDs
    height = len(block_ids)
    width = len(block_ids[0]) if height > 0 else 0
    matrix_short_ids: List[List[Optional[int]]] = [
        [None for _ in range(width)] for _ in range(height)
    ]

    for r in range(height):
        for c in range(width):
            mc_id = block_ids[r][c]
            if mc_id in block_map_mc_id_to_short_id:
                matrix_short_ids[r][c] = block_map_mc_id_to_short_id[mc_id]
            else:
                # Should not happen if warning above is handled, but good practice
                logger.warning(
                    f"Could not find short ID for Minecraft ID '{mc_id}' at ({r},{c}). Setting to null."
                )
                matrix_short_ids[r][c] = None  # Or handle as error?

    block_data = {
        "blocks": block_map_short_id_to_details,
        "matrix": matrix_short_ids,
    }
    processing_time_blockdata = time.time() - start_blockdata_time
    _report_progress(69, "Block data mapping complete")
    logger.info(f"Block data generation took {processing_time_blockdata:.2f} seconds.")

    # --- 4. Render Blocks with Textures ---
    _report_progress(70, "Rendering blocks with textures")
    start_render_time = time.time()
    texture_manager = _get_texture_manager()  # Use shared texture manager

    def render_progress_wrapper(sub_progress):
        # Scale sub-progress (0-100) to fit within the rendering step (70% to 95%)
        overall_progress = 70 + int(sub_progress * 0.25)
        _report_progress(overall_progress, "Rendering textures")

    rendered_image = render_blocks_from_block_ids(
        block_ids,
        texture_manager=texture_manager,
        progress_callback=render_progress_wrapper,
    )
    processing_time_render = time.time() - start_render_time
    _report_progress(95, "Rendering complete")
    logger.info(f"Texture rendering took {processing_time_render:.2f} seconds.")

    if rendered_image is None:
        raise RuntimeError("Block rendering failed to return an image.")

    _report_progress(100, "Processing finished")
    total_time = time.time() - start_total_time
    logger.info(f"Total processing time: {total_time:.2f} seconds.")

    return {
        "rendered_image": rendered_image,
        "dithered_image": dithered_image,
        "block_ids": block_ids,  # Keep original MC IDs for potential other uses
        "block_data": block_data,  # Add the new block data structure
        "processing_time_dither": processing_time_dither,
        "processing_time_render": processing_time_render,
        # Add block data time? Optional.
    }
