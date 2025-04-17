import os
import logging

logger = logging.getLogger("pixeletica.rendering.texture_utils")


def get_best_texture_name(block_id, texture_path, block_mapping, face="top"):
    """
    Advanced logic to resolve the best texture name for a given block_id.

    Args:
        block_id: Minecraft block ID (str)
        texture_path: Path to the texture directory (str)
        block_mapping: Mapping of block IDs to texture info (dict)
        face: Preferred face ("top", "side", etc.)

    Returns:
        texture_name (str) or None
    """
    import re

    # 1. Try direct mapping
    texture_info = block_mapping.get(block_id)
    texture_name = None

    if texture_info:
        if isinstance(texture_info, dict):
            if "texture" in texture_info:
                texture_name = texture_info["texture"]
            else:
                texture_name = texture_info.get(face)
                if not texture_name:
                    texture_name = texture_info.get("side")
        else:
            texture_name = texture_info

    if not texture_name:
        # Try "_top" and base texture
        block_name = block_id.split(":")[-1]
        base_texture_name = f"{block_name}.png"
        top_texture_name = f"{block_name}_top.png"

        if os.path.exists(os.path.join(texture_path, top_texture_name)):
            texture_name = top_texture_name
        elif os.path.exists(os.path.join(texture_path, base_texture_name)):
            texture_name = base_texture_name
        else:
            # Regex fallback
            regex = re.compile(f"{block_name}(|_\\w+)?\\.png$")
            try:
                for filename in os.listdir(texture_path):
                    if regex.match(filename):
                        texture_name = filename
                        break
            except Exception as e:
                logger.error(f"Error listing texture directory: {e}")

    # --- Advanced matching logic ---
    if not texture_name:
        block_name_part = block_id.split(":")[-1]

        # Wood/Hyphae to Log/Stem conversion
        if "wood" in block_name_part or "hyphae" in block_name_part:
            if block_name_part.endswith("_wood"):
                log_block_id = block_id.replace("_wood", "_log")
                logger.debug(f"Trying wood/hyphae to log conversion: {log_block_id}")
                return get_best_texture_name(
                    log_block_id, texture_path, block_mapping, face
                )
            elif block_name_part.endswith("_hyphae"):
                log_block_id = block_id.replace("_hyphae", "_stem")
                logger.debug(f"Trying wood/hyphae to log conversion: {log_block_id}")
                return get_best_texture_name(
                    log_block_id, texture_path, block_mapping, face
                )

        # Waxed blocks (remove "waxed_" prefix)
        if "waxed" in block_name_part:
            unwaxed_block_id = block_id.replace("waxed_", "")
            logger.debug(f"Trying without 'waxed_' prefix: {unwaxed_block_id}")
            return get_best_texture_name(
                unwaxed_block_id, texture_path, block_mapping, face
            )

        # Remove "_block" suffix
        if block_name_part.endswith("_block"):
            base_block_id = block_id[:-6]
            logger.debug(f"Trying without '_block' suffix: {base_block_id}")
            return get_best_texture_name(
                base_block_id, texture_path, block_mapping, face
            )

        # Try simplified block ID (remove namespace)
        if ":" in block_id:
            simple_block_id = block_id.split(":")[-1]
            logger.debug(f"Trying simplified block ID: {simple_block_id}")
            return get_best_texture_name(
                simple_block_id, texture_path, block_mapping, face
            )

    return texture_name
