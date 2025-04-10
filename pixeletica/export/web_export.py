"""
Web export functionality.

This module provides functionality for exporting Minecraft images as web-optimized tiles.
"""

import os
import json
import math
from PIL import Image
from pathlib import Path


def export_web_tiles(image, output_dir, tile_size=512, origin_x=0, origin_z=0):
    """
    Export an image as a set of web-optimized tiles.

    Args:
        image: PIL Image to export
        output_dir: Directory to output the tiles to
        tile_size: Size of each tile (default: 512×512)
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin

    Returns:
        Dictionary containing information about the exported tiles
    """
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    width, height = image.size

    # Calculate number of tiles
    tiles_x = math.ceil(width / tile_size)
    tiles_z = math.ceil(height / tile_size)

    # Information about the export
    export_info = {
        "tile_size": tile_size,
        "width": width,
        "height": height,
        "tiles_x": tiles_x,
        "tiles_z": tiles_z,
        "origin_x": origin_x,
        "origin_z": origin_z,
        "tiles": [],
    }

    # Generate tiles
    for z in range(tiles_z):
        for x in range(tiles_x):
            # Calculate tile boundaries
            left = x * tile_size
            top = z * tile_size
            right = min((x + 1) * tile_size, width)
            bottom = min((z + 1) * tile_size, height)

            # Crop the tile from the image
            tile = image.crop((left, top, right, bottom))

            # Calculate in-world coordinates for naming and metadata
            world_x = left + origin_x
            world_z = top + origin_z

            # Create tile filename
            tile_filename = f"tile_x{world_x}_z{world_z}.png"
            tile_path = os.path.join(output_dir, tile_filename)

            # Save the tile
            tile.save(tile_path)

            # Add tile info to the export metadata
            tile_info = {
                "filename": tile_filename,
                "x": x,
                "z": z,
                "world_x": world_x,
                "world_z": world_z,
                "width": right - left,
                "height": bottom - top,
            }
            export_info["tiles"].append(tile_info)

    # Create an index.html file for viewing the tiles
    create_web_viewer_html(output_dir, export_info)

    # Save export info as JSON
    info_path = os.path.join(output_dir, "tiles_info.json")
    with open(info_path, "w") as f:
        json.dump(export_info, f, indent=2)

    return export_info


def create_web_viewer_html(output_dir, export_info):
    """
    Create a simple HTML viewer for the tiles.

    Args:
        output_dir: Directory to output the HTML file
        export_info: Dictionary containing information about the exported tiles
    """
    html_path = os.path.join(output_dir, "index.html")

    # Simple HTML template for viewing the tiles
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Minecraft Map Viewer</title>
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            background: #222;
            color: #fff;
            font-family: Arial, sans-serif;
        }}
        .container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }}
        .map-container {{
            position: relative;
            width: {export_info["width"]}px;
            height: {export_info["height"]}px;
            overflow: auto;
            border: 1px solid #333;
            background: #000;
        }}
        .map {{
            position: absolute;
            top: 0;
            left: 0;
            width: {export_info["width"]}px;
            height: {export_info["height"]}px;
        }}
        .tile {{
            position: absolute;
            image-rendering: pixelated;
        }}
        .info {{
            margin-top: 20px;
            padding: 10px;
            background: #333;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Minecraft Map Viewer</h1>
        <div class="map-container">
            <div class="map" id="map"></div>
        </div>
        <div class="info">
            <p>Map Size: {export_info["width"]}×{export_info["height"]} pixels</p>
            <p>Tiles: {export_info["tiles_x"]}×{export_info["tiles_z"]}</p>
            <p>Origin: ({export_info["origin_x"]}, {export_info["origin_z"]})</p>
        </div>
    </div>

    <script>
        const mapElement = document.getElementById('map');
        const tilesInfo = {json.dumps(export_info["tiles"])};
        
        // Add tiles to the map
        tilesInfo.forEach(tile => {{
            const tileElement = document.createElement('img');
            tileElement.src = tile.filename;
            tileElement.className = 'tile';
            tileElement.style.left = (tile.x * {export_info["tile_size"]}) + 'px';
            tileElement.style.top = (tile.z * {export_info["tile_size"]}) + 'px';
            tileElement.style.width = tile.width + 'px';
            tileElement.style.height = tile.height + 'px';
            mapElement.appendChild(tileElement);
        }});
    </script>
</body>
</html>"""

    with open(html_path, "w") as f:
        f.write(html_content)
