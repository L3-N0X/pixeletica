"""
Minecraft texture loading and management.

This module handles loading and caching Minecraft block textures from the default
texture pack and associating them with the appropriate blocks.
"""

import os
import json
import re
import logging
from PIL import Image
from functools import lru_cache

# Set up logging
logger = logging.getLogger("pixeletica.rendering.texture_loader")

# Default texture path
DEFAULT_TEXTURE_PATH = "./src/minecraft/texturepack/minecraft/textures/block"


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

        # Load block texture mapping from JSON file
        mapping_file = "./src/minecraft/block_texture_mapping.json"
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, "r") as f:
                    self.block_mapping = json.load(f)
                logger.info(f"Loaded block texture mapping from {mapping_file}")
            except Exception as e:
                logger.error(f"Error loading block texture mapping: {e}")
        else:
            logger.warning(f"Block texture mapping file not found: {mapping_file}")

    @lru_cache(maxsize=128)
    def _load_texture(self, texture_name):
        """
        Load a texture from the texture pack and handle animations.

        Args:
            texture_name: Filename of the texture

        Returns:
            PIL Image object of the texture or None if not found
        """
        # First, try the texture name directly
        texture_path = os.path.join(self.texture_path, texture_name)

        # If it doesn't exist and starts with "block/", try without that prefix
        if not os.path.exists(texture_path) and texture_name.startswith("block/"):
            texture_path = os.path.join(self.texture_path, texture_name[6:])

        try:
            if os.path.exists(texture_path):
                logger.debug(f"Loading texture from: {texture_path}")
                image = Image.open(texture_path).convert("RGBA")
                if image.height > 16:
                    # Crop to first frame (16x16) for animated textures
                    image = image.crop((0, 0, 16, 16))
                # Ensure we're preserving color information properly
                return image
            else:
                logger.warning(f"Texture not found: {texture_path}")
                return None
        except Exception as e:
            logger.error(f"Error loading texture {texture_name}: {e}")
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
        # Debug logging
        logger.debug(f"Getting texture for block_id={block_id}, face={face}")

        # Check cache
        cache_key = f"{block_id}:{face}"
        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]

        texture_name = None
        texture_info = self.block_mapping.get(block_id)

        if texture_info:
            if isinstance(texture_info, dict):
                # Check if there's a specific texture for this face
                if "texture" in texture_info:
                    texture_name = texture_info["texture"]
                else:
                    texture_name = texture_info.get(face)
                    if not texture_name:
                        texture_name = texture_info.get("side")
            else:
                texture_name = texture_info

        if not texture_name:
            # Regex-based matching and prioritize "_top" textures
            block_name = block_id.split(":")[-1]
            base_texture_name = f"{block_name}.png"
            top_texture_name = f"{block_name}_top.png"

            if os.path.exists(os.path.join(self.texture_path, top_texture_name)):
                texture_name = top_texture_name
            elif os.path.exists(os.path.join(self.texture_path, base_texture_name)):
                texture_name = base_texture_name
            else:
                # Fallback: try to find any texture matching block name using regex
                regex = re.compile(f"{block_name}(|_\\w+)?\\.png$")
                try:
                    for filename in os.listdir(self.texture_path):
                        if regex.match(filename):
                            texture_name = filename
                            break
                except Exception as e:
                    logger.error(f"Error listing texture directory: {e}")

        if texture_name:
            texture = self._load_texture(texture_name)
            self.texture_cache[cache_key] = texture
            if texture:
                logger.debug(f"Found texture {texture_name} for {block_id}")
                return texture
            else:
                logger.warning(f"Failed to load texture {texture_name} for {block_id}")
                return None
        else:
            logger.warning(f"No texture name found for block {block_id}")
            return None

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
