"""
Web export functionality.

This module provides functionality for exporting Minecraft images as web-optimized tiles
with support for multiple zoom levels.
"""

import os
import json
import math
from PIL import Image
from pathlib import Path


def export_web_tiles(
    image, output_dir, tile_size=256, origin_x=0, origin_z=0, min_zoom=0, max_zoom=4
):
    """
    Export an image as a set of web-optimized tiles with multiple zoom levels.

    Args:
        image: PIL Image to export
        output_dir: Directory to output the tiles to
        tile_size: Size of each tile (default: 256×256)
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin
        min_zoom: Minimum zoom level (default: 0, most zoomed out)
        max_zoom: Maximum zoom level (default: 4, most detailed)

    Returns:
        Dictionary containing information about the exported tiles
    """
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Create a rendered directory inside output_dir for web tiles
    rendered_dir = os.path.join(output_dir, "rendered")
    os.makedirs(rendered_dir, exist_ok=True)

    width, height = image.size

    # Save the full image for initial loading
    full_image_path = os.path.join(rendered_dir, "full-image.png")
    # Create a copy of the image to avoid modifying the original
    full_image = image.copy()
    # If the image is large, resize it to a reasonable size for the full image
    if max(width, height) > 2048:
        scale_factor = 2048 / max(width, height)
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        full_image = full_image.resize((new_width, new_height), Image.LANCZOS)

    # Save the full image as PNG with reasonable quality
    full_image.save(full_image_path, "PNG")

    # Create metadata structure
    metadata = {
        "width": width,
        "height": height,
        "origin_x": origin_x,
        "origin_z": origin_z,
        "tile_size": tile_size,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "zoom_levels": {},
    }

    # Create tiles directory structure
    tiles_base_dir = os.path.join(rendered_dir, "tiles")
    os.makedirs(tiles_base_dir, exist_ok=True)

    # Generate tiles for each zoom level
    for zoom in range(min_zoom, max_zoom + 1):
        # For each zoom level, calculate the size of the image
        zoom_factor = 2 ** (max_zoom - zoom)
        zoom_width = max(1, width // zoom_factor)
        zoom_height = max(1, height // zoom_factor)

        # Create the zoom level directory
        zoom_dir = os.path.join(tiles_base_dir, str(zoom))
        os.makedirs(zoom_dir, exist_ok=True)

        # Resize the image for this zoom level if needed
        if zoom == max_zoom:
            zoom_image = image  # Use original for max zoom
        else:
            zoom_image = image.resize((zoom_width, zoom_height), Image.LANCZOS)

        # Calculate tiles for this zoom level
        tiles_x = math.ceil(zoom_width / tile_size)
        tiles_z = math.ceil(zoom_height / tile_size)

        zoom_metadata = {
            "width": zoom_width,
            "height": zoom_height,
            "tiles_x": tiles_x,
            "tiles_z": tiles_z,
            "tiles": [],
        }

        # Generate tiles for this zoom level
        for z in range(tiles_z):
            for x in range(tiles_x):
                # Calculate tile boundaries
                left = x * tile_size
                top = z * tile_size
                right = min((x + 1) * tile_size, zoom_width)
                bottom = min((z + 1) * tile_size, zoom_height)

                # Crop the tile
                tile = zoom_image.crop((left, top, right, bottom))

                # Calculate in-world coordinates
                world_x = (left * zoom_factor) + origin_x
                world_z = (top * zoom_factor) + origin_z

                # Create tile filename and path
                tile_filename = f"{x}_{z}.png"
                tile_path = os.path.join(zoom_dir, tile_filename)

                # Save the tile
                tile.save(tile_path, "PNG", optimize=True)

                # Add tile info to metadata
                tile_info = {
                    "x": x,
                    "z": z,
                    "world_x": world_x,
                    "world_z": world_z,
                    "width": right - left,
                    "height": bottom - top,
                    "filename": f"tiles/{zoom}/{tile_filename}",
                }
                zoom_metadata["tiles"].append(tile_info)

        metadata["zoom_levels"][str(zoom)] = zoom_metadata

    # Create an index.html file for viewing the tiles
    create_web_viewer_html(output_dir, metadata)

    # Save metadata as JSON (only in one location)
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def create_web_viewer_html(output_dir, metadata):
    """
    Create a simple HTML viewer for the tiles with zoom support.

    Args:
        output_dir: Directory to output the HTML file
        metadata: Dictionary containing information about the exported tiles
    """
    html_path = os.path.join(output_dir, "index.html")

    # Get max zoom level for initial display
    max_zoom = metadata["max_zoom"]
    min_zoom = metadata["min_zoom"]
    initial_zoom = min(min_zoom + 2, max_zoom)  # Start at a reasonable zoom level

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
            width: 800px;
            height: 600px;
            overflow: auto;
            border: 1px solid #333;
            background: #000;
        }}
        .map {{
            position: absolute;
            top: 0;
            left: 0;
            width: {metadata["width"]}px;
            height: {metadata["height"]}px;
        }}
        .tile {{
            position: absolute;
            image-rendering: pixelated;
        }}
        .controls {{
            margin: 10px 0;
            padding: 10px;
            background: #333;
            border-radius: 5px;
            display: flex;
            align-items: center;
        }}
        .controls button {{
            margin: 0 5px;
            padding: 5px 10px;
            background: #555;
            border: none;
            color: white;
            border-radius: 3px;
            cursor: pointer;
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
        
        <div class="controls">
            <button id="zoomIn">Zoom In</button>
            <button id="zoomOut">Zoom Out</button>
            <span id="zoomLevel">Zoom: {initial_zoom}</span>
        </div>
        
        <div class="map-container" id="mapContainer">
            <div class="map" id="map"></div>
        </div>
        
        <div class="info">
            <p>Map Size: {metadata["width"]}×{metadata["height"]} pixels</p>
            <p>Origin: ({metadata["origin_x"]}, {metadata["origin_z"]})</p>
            <p>Zoom Levels: {min_zoom} - {max_zoom}</p>
        </div>
    </div>

    <script>
        // Map metadata
        const metadata = {json.dumps(metadata)};
        const mapElement = document.getElementById('map');
        const mapContainer = document.getElementById('mapContainer');
        const zoomLevelDisplay = document.getElementById('zoomLevel');
        
        // Current zoom level
        let currentZoom = {initial_zoom};
        
        // Load tiles for the current zoom level
        function loadZoomLevel(zoom) {{
            // Clear previous tiles
            mapElement.innerHTML = '';
            
            // Get zoom level data
            const zoomData = metadata.zoom_levels[zoom];
            if (!zoomData) return;
            
            // Update map size based on zoom level
            mapElement.style.width = zoomData.width + 'px';
            mapElement.style.height = zoomData.height + 'px';
            
            // Add tiles to the map
            zoomData.tiles.forEach(tile => {{
                const tileElement = document.createElement('img');
                tileElement.src = tile.filename;
                tileElement.className = 'tile';
                tileElement.style.left = (tile.x * metadata.tile_size) + 'px';
                tileElement.style.top = (tile.z * metadata.tile_size) + 'px';
                tileElement.style.width = tile.width + 'px';
                tileElement.style.height = tile.height + 'px';
                mapElement.appendChild(tileElement);
            }});
            
            // Update zoom display
            zoomLevelDisplay.textContent = 'Zoom: ' + zoom;
        }}
        
        // Zoom in button
        document.getElementById('zoomIn').addEventListener('click', () => {{
            if (currentZoom < metadata.max_zoom) {{
                currentZoom++;
                loadZoomLevel(currentZoom);
            }}
        }});
        
        // Zoom out button
        document.getElementById('zoomOut').addEventListener('click', () => {{
            if (currentZoom > metadata.min_zoom) {{
                currentZoom--;
                loadZoomLevel(currentZoom);
            }}
        }});
        
        // Initial load
        loadZoomLevel(currentZoom);
        
        // Center the map initially
        mapContainer.scrollLeft = (mapElement.offsetWidth - mapContainer.offsetWidth) / 2;
        mapContainer.scrollTop = (mapElement.offsetHeight - mapContainer.offsetHeight) / 2;
    </script>
</body>
</html>"""

    with open(html_path, "w") as f:
        f.write(html_content)
