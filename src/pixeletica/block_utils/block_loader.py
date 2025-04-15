"""
Functions for loading and parsing Minecraft block colors from CSV files.
"""

import csv
import logging
import os

# Set up logging
logger = logging.getLogger("pixeletica.block_utils.block_loader")

# Block color data
block_colors = []
loaded_csv_path = None


def load_block_colors(csv_path):
    """
    Load Minecraft block colors from a CSV file.

    Args:
        csv_path: Path to the CSV file with block color data

    Returns:
        Boolean indicating success or failure
    """
    global block_colors, loaded_csv_path
    block_colors = []

    if not os.path.exists(csv_path):
        logger.error(f"Block colors file not found: {csv_path}")
        return False

    logger.info(f"Loading block colors from {csv_path}")

    try:
        with open(csv_path, "r") as file:
            reader = csv.reader(file, delimiter=";")
            row_count = 0
            for row in reader:
                if len(row) >= 4:  # Ensure we have enough columns
                    name = row[0]
                    block_id = row[1]
                    hex_color = row[2]
                    rgb_str = row[3].strip("()").split(",")
                    r = int(rgb_str[0].strip())
                    g = int(rgb_str[1].strip())
                    b = int(rgb_str[2].strip())

                    block_colors.append(
                        {
                            "name": name,
                            "id": block_id,
                            "hex": hex_color,
                            "rgb": (r, g, b),
                        }
                    )
                    row_count += 1

        loaded_csv_path = csv_path
        logger.warning(f"Loaded {len(block_colors)} block colors from {csv_path}")

        # Verify colors are available through get_block_colors()
        verify_colors = get_block_colors()
        if not verify_colors or len(verify_colors) == 0:
            logger.error(
                "Block colors were loaded but are not accessible through get_block_colors()"
            )
            return False

        return len(block_colors) > 0
    except Exception as e:
        logger.error(f"Error loading block colors: {e}")
        return False


def get_block_colors():
    """Return the loaded block colors."""
    global block_colors
    if not block_colors:
        logger.warning(
            f"get_block_colors() called but block_colors list is empty (loaded_path={loaded_csv_path})"
        )
    return block_colors
