# Pixeletica Developer Guide

## Introduction

Pixeletica is a tool for converting images into Minecraft block art. This guide provides information for developers who want to contribute to Pixeletica or use it as a library.

## Installation

### Standard Installation

1.  Clone the Pixeletica repository from [link to repository].
2.  Install the dependencies using `uv pip install -r requirements.txt`.
3.  Run the `pixeletica` executable.

### Docker Installation

1.  Install Docker Desktop from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/).
2.  Clone the Pixeletica repository from [link to repository].
3.  Navigate to the Pixeletica directory in your terminal.
4.  Run `docker-compose up` to start the Pixeletica API and worker.

## API Endpoints

The Pixeletica API provides the following endpoints:

*   `/api/conversion/start`: Starts a new image conversion task.
*   `/api/conversion/{taskId}`: Checks the status of a conversion task.
*   `/api/conversion/{taskId}/files`: Lists the available files for a conversion task.
*   `/api/conversion/{taskId}/download`: Downloads the files for a conversion task.
*   `/api/map/{mapId}/metadata.json`: Retrieves metadata for a specific map.
*   `/api/map/{mapId}/tiles/{zoom}/{x}/{y}.png`: Retrieves a specific map tile.
*   `/api/maps.json`: Lists all available maps (all previously exported maps).

## Code Structure

The Pixeletica codebase is structured as follows:

*   `pixeletica/`: Contains the core Pixeletica code.
    *   `api/`: Contains the API code.
        *   `main.py`: The main API entry point.
        *   `models.py`: The API models.
        *   `routes/`: Contains the API route handlers.
        *   `services/`: Contains the API services.
    *   `dithering/`: Contains the dithering algorithms.
    *   `export/`: Contains the export code.
    *   `image_ops.py`: Contains the image processing code.
    *   `cli.py`: Contains the command-line interface code.

## Contributing

To contribute to Pixeletica, please follow these steps:

1.  Fork the Pixeletica repository.
2.  Create a new branch for your changes.
3.  Make your changes and commit them.
4.  Submit a pull request.

## Explanation of Algorithms and Options

### Dithering Algorithms

Dithering algorithms are used to reduce the number of colors in an image while minimizing the appearance of banding. Pixeletica supports the following dithering algorithms:

*   `no-dither`: Simple color mapping to the nearest color.
*   `floyd-steinberg`: Floyd-Steinberg dithering.
*   `ordered-dither`: Ordered dithering with Bayer matrices.
*   `random-dither`: Random dithering with noise.

### Color Palettes

Color palettes are used to map the colors in an image to Minecraft blocks. Pixeletica supports the following color palettes:

*   `minecraft`: The standard Minecraft block color palette.

### Output Formats

Output formats are used to specify the format of the output file. Pixeletica supports the following output formats:

*   `png`: PNG image.

### Orientation Options

Orientation options are used to specify the orientation of the output. Pixeletica supports the following orientation options:

*   `x`: X-axis orientation.
*   `z`: Z-axis orientation.
*   `y_is_height`: Whether the Y-axis is the height.

### Scale Option

The scale option is used to specify the scale of the output.

### Split Options

The split options are used to specify the number of horizontal and vertical splits.

## Troubleshooting Guides

### Error: Image size exceeds maximum limit

This error occurs when the image size exceeds the maximum limit. To fix this error, reduce the size of the image or increase the maximum limit.

### Error: Failed to create conversion task

This error occurs when the conversion task fails to create. To fix this error, check the logs for more information.
