"""
Block rendering using Minecraft textures.

This module provides functionality for rendering blocks using actual Minecraft textures
rather than solid colors from a color palette.
"""

import hashlib
import logging
import os
from PIL import Image

from src.pixeletica.rendering.texture_loader import TextureManager

# Set up logging
logger = logging.getLogger("pixeletica.rendering.block_renderer")


class BlockRenderer:
    """
    Renders blocks using Minecraft textures.
    """

    def __init__(self, texture_manager=None):
        """
        Initialize the block renderer.

        Args:
            texture_manager: TextureManager instance, or None to create a new one
        """
        self.texture_manager = texture_manager or TextureManager()
        self.texture_size = self.texture_manager.get_block_texture_size() or (16, 16)

    def render_block(
        self, block_id, scale=1, missing_textures=None, default_texture=None
    ):
        """
        Render a single block using its texture.

        Args:
            block_id: Minecraft block ID
            scale: Scale factor for the rendered block (default: 1)
            missing_textures: set to collect missing block IDs (for logging)
            default_texture: PIL Image to use if texture is missing

        Returns:
            PIL Image of the rendered block
        """
        # Normalize block ID (strip whitespace, lower-case)
        block_id = str(block_id).strip().lower()

        # For most blocks, we use the top texture in a flat map view
        texture = self.texture_manager.get_texture(block_id, face="top")

        # If no top texture is available, try side texture
        if texture is None:
            logger.debug(f"No top texture for {block_id}, trying side texture")
            texture = self.texture_manager.get_texture(block_id, face="side")

        # If still no texture, try any face
        if texture is None:
            logger.debug(f"No side texture for {block_id}, trying default texture")
            texture = self.texture_manager.get_texture(block_id)

        # Try with a simplified block ID (remove namespace if present)
        if texture is None and ":" in block_id:
            simple_block_id = block_id.split(":")[-1]
            logger.debug(f"Trying simplified block ID: {simple_block_id}")
            texture = self.texture_manager.get_texture(simple_block_id, face="top")
            if texture is None:
                texture = self.texture_manager.get_texture(simple_block_id, face="side")
            if texture is None:
                texture = self.texture_manager.get_texture(simple_block_id)

        # If still no texture is found, use default texture or create a colored placeholder
        if texture is None:
            if missing_textures is not None:
                missing_textures.add(block_id)
            if default_texture is not None:
                texture = default_texture.copy()
            else:
                # Hash the block ID to get a somewhat consistent color
                hash_val = int(hashlib.md5(block_id.encode()).hexdigest(), 16)
                r = (hash_val & 0xFF0000) >> 16
                g = (hash_val & 0x00FF00) >> 8
                b = hash_val & 0x0000FF
                texture = Image.new("RGBA", self.texture_size, (r, g, b, 255))

        # Ensure the texture is in RGBA mode to preserve colors
        if texture.mode != "RGBA":
            texture = texture.convert("RGBA")

        # Scale if needed
        if scale != 1:
            new_size = (int(texture.width * scale), int(texture.height * scale))
            texture = texture.resize(new_size, Image.NEAREST)

        return texture

    def render_block_array(self, block_ids, scale=1, progress_callback=None):
        """
        Render a 2D array of blocks.

        Args:
            block_ids: 2D array of block IDs
            scale: Scale factor for each block texture (default: 1)

        Returns:
            PIL Image of the rendered blocks
        """
        if not block_ids or len(block_ids) == 0 or len(block_ids[0]) == 0:
            return None

        # Get dimensions
        height = len(block_ids)
        width = len(block_ids[0])

        # Create the output image
        texture_width, texture_height = self.texture_size
        output_width = width * texture_width * scale
        output_height = height * texture_height * scale
        output_image = Image.new(
            "RGBA", (int(output_width), int(output_height)), (0, 0, 0, 0)
        )

        # Prepare for missing texture logging
        missing_textures = set()
        # Optionally, load a default texture (e.g., "stone")
        default_texture = self.texture_manager.get_texture("stone", face="top")

        # Render each block
        for z in range(height):
            for x in range(width):
                block_id = block_ids[z][x]
                if block_id:  # Skip None or empty blocks
                    block_img = self.render_block(
                        block_id,
                        scale,
                        missing_textures=missing_textures,
                        default_texture=default_texture,
                    )

                    # Calculate position
                    pos_x = x * texture_width * scale
                    pos_z = z * texture_height * scale

                    # Paste the block texture
                    output_image.paste(block_img, (int(pos_x), int(pos_z)), block_img)
            if progress_callback is not None:
                progress = int((z + 1) / height * 100)
                progress_callback(progress)

        if missing_textures:
            logger.warning(
                f"Missing textures for block IDs: {sorted(missing_textures)}"
            )

        return output_image


def render_blocks_from_block_ids(
    block_ids, scale=1, texture_manager=None, progress_callback=None
):
    """
    Convenience function to render blocks from block IDs.

    Args:
        block_ids: 2D array of block IDs
        scale: Scale factor for each block texture (default: 1)
        texture_manager: TextureManager instance or None
        progress_callback: Optional callback function for progress updates

    Returns:
        PIL Image of the rendered blocks
    """
    # Create a texture manager with absolute path to ensure correct texture loading
    if texture_manager is None:
        from src.pixeletica.rendering.texture_loader import DEFAULT_TEXTURE_PATH

        texture_path = os.path.abspath(DEFAULT_TEXTURE_PATH)
        logger.info(f"Creating new TextureManager with path: {texture_path}")
        texture_manager = TextureManager(texture_path)

    renderer = BlockRenderer(texture_manager)
    return renderer.render_block_array(
        block_ids, scale, progress_callback=progress_callback
    )
