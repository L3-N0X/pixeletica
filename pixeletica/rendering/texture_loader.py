"""
Minecraft texture loading and management.

This module handles loading and caching Minecraft block textures from the default
texture pack and associating them with the appropriate blocks.
"""

import os
import json
from PIL import Image
from functools import lru_cache

# Default texture path
DEFAULT_TEXTURE_PATH = "./minecraft/texturepack/minecraft/textures/blocks"


class TextureManager:
    """
    Manages the loading and caching of Minecraft block textures.
    """

    def __init__(self, texture_path=DEFAULT_TEXTURE_PATH):
        """
        Initialize the texture manager.

        Args:
            texture_path: Path to the Minecraft block textures directory
        """
        self.texture_path = texture_path
        self.texture_cache = {}  # Cache textures by block_id
        self.block_mapping = {}  # Maps block IDs to texture files
        self._load_block_texture_mapping()

    def _load_block_texture_mapping(self):
        """Load the mapping between block IDs and texture files."""
        # This is a simplified version - in reality,
        # this would be a more complex mapping potentially loaded from a config file

        # Example mapping (to be expanded with actual block data)
        # Format: 'block_id': {'top': 'texture_file.png', 'side': 'texture_file.png', 'bottom': 'texture_file.png'}
        # If a block has the same texture on all sides, it can be a string instead of a dict

        # For now, we'll use a basic mapping as a starting point
        self.block_mapping = {
            # Basic blocks
            "minecraft:stone": "stone.png",
            "minecraft:grass_block": {
                "top": "grass_block_top.png",
                "side": "grass_block_side.png",
                "bottom": "dirt.png",
            },
            "minecraft:dirt": "dirt.png",
            "minecraft:cobblestone": "cobblestone.png",
            "minecraft:oak_planks": "oak_planks.png",
            "minecraft:sand": "sand.png",
            # Add more blocks as needed
        }

        # You could also load this from a JSON file
        mapping_file = os.path.join(
            os.path.dirname(__file__), "block_texture_mapping.json"
        )
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, "r") as f:
                    self.block_mapping.update(json.load(f))
            except Exception as e:
                print(f"Error loading block texture mapping: {e}")

    @lru_cache(maxsize=128)
    def _load_texture(self, texture_name):
        """
        Load a texture from the texture pack.

        Args:
            texture_name: Filename of the texture

        Returns:
            PIL Image object of the texture or None if not found
        """
        texture_path = os.path.join(self.texture_path, texture_name)
        try:
            if os.path.exists(texture_path):
                return Image.open(texture_path).convert("RGBA")
            else:
                print(f"Texture not found: {texture_path}")
                return None
        except Exception as e:
            print(f"Error loading texture {texture_name}: {e}")
            return None

    def get_texture(self, block_id, face="top"):
        """
        Get the texture for a given block ID and face.

        Args:
            block_id: Minecraft block ID
            face: Which face of the block (top, side, bottom)

        Returns:
            PIL Image object of the block texture or None if not found
        """
        # Check if we already have this texture in cache
        cache_key = f"{block_id}:{face}"
        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]

        # Get the texture filename for this block
        texture_info = self.block_mapping.get(block_id)
        if texture_info is None:
            # If not found in mapping, try using the block ID as the texture name
            texture_name = block_id.split(":")[-1] + ".png"
        elif isinstance(texture_info, dict):
            # If we have different textures for different faces
            texture_name = texture_info.get(face, texture_info.get("side", None))
            if texture_name is None:
                # No specific texture for this face
                return None
        else:
            # Same texture for all faces
            texture_name = texture_info

        # Load the texture
        texture = self._load_texture(texture_name)

        # Cache it for future use
        self.texture_cache[cache_key] = texture

        return texture

    def clear_cache(self):
        """Clear the texture cache."""
        self.texture_cache.clear()

    def get_block_texture_size(self):
        """
        Get the standard size of block textures.

        Returns:
            Tuple of (width, height) or None if no textures loaded
        """
        # Try to get a texture to determine the size
        for block_id in self.block_mapping:
            texture = self.get_texture(block_id)
            if texture:
                return texture.size
        return None
