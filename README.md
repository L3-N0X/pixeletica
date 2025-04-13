# Pixeletica - Minecraft Image Processor

Pixeletica is a powerful tool for converting images into Minecraft blocks with various dithering methods. It can generate color-matched images, Litematica schematics, and textured image exports.

## Features

### Dithering Algorithms

- **No Dithering**: Simple color mapping without dithering
- **Floyd-Steinberg**: Error diffusion dithering for smooth results
- **Ordered Dithering**: Pattern-based dithering with Bayer matrices
- **Random Dithering**: Adds random noise for a pixelated effect

### Export Options

- **Texture Rendering**: Visualize images using actual Minecraft textures
- **Web Optimization**: Split images into 512×512 tiles for web viewing
- **Split Export**: Divide images into configurable number of parts
- **Schematic Generation**: Create Litematica schematics for in-game building

### Visualization Options

- **Chunk Lines**: Display Minecraft chunk boundaries (every 16 blocks)
- **Block Grid**: Show block boundaries for precise positioning
- **Customizable Colors**: Configure line colors with alpha channel support
- **Coordinate System**: Specify world coordinates for proper alignment

## Usage

### GUI Mode

1. Launch the application with `python main.py` and select GUI mode
2. Load an image and set your desired size
3. Choose a dithering algorithm
4. Configure export settings in the Export tab
5. Process and save your image

### CLI Mode

Run the application with command line mode for batch processing:

```bash
python main.py
```

## Export Settings

### Minecraft Coordinates

Enter the top-left X,Z coordinates in the Minecraft world. These coordinates determine how chunk boundaries align.

### Line Options

- **Chunk Lines**: Shows Minecraft chunk boundaries (every 16 blocks)
- **Block Grid**: Shows individual block boundaries
- Customize colors with hex format (RRGGBBAA)

### Export Types

- **Web Tiles**: Creates 512×512 tiles with HTML viewer
- **Large Image**: Single combined image
- **Split Parts**: Divides the image into multiple equal parts

## Installation

### Standard Installation

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Place Minecraft textures in `./minecraft/texturepack/minecraft/textures/block`
4. Run the application: `python main.py`

You can also use uv for installation (recommended):

```bash
uv install -r requirements.txt
uv run main.py
```

### Docker Installation (API Mode)

Pixeletica API can be run using Docker containers for easy deployment:

1. Make sure Docker and Docker Compose are installed on your system
2. Clone this repository
3. Start the services:

```bash
docker-compose up -d
```

This will start the API server, Celery worker, and Redis in separate containers.

For configuration options and advanced usage, see the [Docker documentation](./docker/README.md).

#### Docker Configuration

- API is accessible at `http://localhost:8000` by default
- Configure via environment variables or docker-compose.override.yml
- Data is persisted in Docker volumes

```bash
# Basic usage
docker-compose up -d                    # Start all services
docker-compose down                     # Stop all services
docker-compose logs -f                  # View logs
docker-compose up -d --scale worker=3   # Run with 3 worker instances
```

## Requirements

- Python 3.8+
- Pillow (PIL)
- NumPy
- Litemapy

## License

This project is licensed under the MIT License - see LICENSE file for details.
