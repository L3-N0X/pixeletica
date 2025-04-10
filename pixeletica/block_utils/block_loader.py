"""
Functions for loading and parsing Minecraft block colors from CSV files.
"""

import csv

# Block color data
block_colors = []


def load_block_colors(csv_path):
    """Load Minecraft block colors from a CSV file."""
    global block_colors
    block_colors = []

    try:
        with open(csv_path, "r") as file:
            reader = csv.reader(file, delimiter=";")
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
        print(f"Loaded {len(block_colors)} block colors from {csv_path}")
    except Exception as e:
        print(f"Error loading block colors: {e}")

    return len(block_colors) > 0


def get_block_colors():
    """Return the loaded block colors."""
    return block_colors
