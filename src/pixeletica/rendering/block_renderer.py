"""
Block rendering using Minecraft textures.

This module provides functionality for rendering blocks using actual Minecraft textures
rather than solid colors from a color palette.
"""

import numpy as np
from PIL import Image

from src.pixeletica.rendering.texture_loader import TextureManager


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

    def render_block(self, block_id, scale=1):
        """
        Render a single block using its texture.

        Args:
            block_id: Minecraft block ID
            scale: Scale factor for the rendered block (default: 1)

        Returns:
            PIL Image of the rendered block
        """
        # For most blocks, we use the top texture in a flat map view
        texture = self.texture_manager.get_texture(block_id, face="top")

        # If no top texture is available, try side texture
        if texture is None:
            texture = self.texture_manager.get_texture(block_id, face="side")

        # If still no texture, try any face
        if texture is None:
            texture = self.texture_manager.get_texture(block_id)

        # If no texture is found, create a colored placeholder based on the block ID
        if texture is None:
            # Hash the block ID to get a somewhat consistent color
            import hashlib

            hash_val = int(hashlib.md5(block_id.encode()).hexdigest(), 16)
            r = (hash_val & 0xFF0000) >> 16
            g = (hash_val & 0x00FF00) >> 8
            b = hash_val & 0x0000FF

            # Create a placeholder with the hashed color
            texture = Image.new("RGBA", self.texture_size, (r, g, b, 255))

        # Ensure the texture is in RGBA mode to preserve colors
        if texture.mode != "RGBA":
            texture = texture.convert("RGBA")

        # Scale if needed
        if scale != 1:
            new_size = (int(texture.width * scale), int(texture.height * scale))
            texture = texture.resize(new_size, Image.NEAREST)

        return texture

    def render_block_array(self, block_ids, scale=1):
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

        # Render each block
        for z in range(height):
            for x in range(width):
                block_id = block_ids[z][x]
                if block_id:  # Skip None or empty blocks
                    block_img = self.render_block(block_id, scale)

                    # Calculate position
                    pos_x = x * texture_width * scale
                    pos_z = z * texture_height * scale

                    # Paste the block texture
                    output_image.paste(block_img, (int(pos_x), int(pos_z)), block_img)

        return output_image


def render_blocks_from_block_ids(block_ids, scale=1, texture_manager=None):
    """
    Convenience function to render blocks from block IDs.

    Args:
        block_ids: 2D array of block IDs
        scale: Scale factor for each block texture (default: 1)
        texture_manager: TextureManager instance or None

    Returns:
        PIL Image of the rendered blocks
    """
    renderer = BlockRenderer(texture_manager)
    return renderer.render_block_array(block_ids, scale)
