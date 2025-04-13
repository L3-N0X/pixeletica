# Pixeletica User Guide

## Introduction

Pixeletica is a tool for converting images into Minecraft block art. This guide will walk you through the process of using Pixeletica to create your own Minecraft masterpieces.

## Installation

### Standard Installation

1.  Download the latest version of Pixeletica from [link to download].
2.  Extract the downloaded archive to a directory of your choice.
3.  Run the `pixeletica` executable.

### Docker Installation

1.  Install Docker Desktop from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/).
2.  Clone the Pixeletica repository from [link to repository].
3.  Navigate to the Pixeletica directory in your terminal.
4.  Run `docker-compose up` to start the Pixeletica API and worker.

## Usage

### API Usage

The Pixeletica API can be used to convert images programmatically. The API endpoints are documented in the [API documentation](api.md).

### GUI Usage

The Pixeletica GUI can be used to convert images interactively. To use the GUI, run the `pixeletica` executable and follow the instructions on the screen.

## API Usage Examples

### Start a Conversion Task

To start a conversion task, send a POST request to the `/api/conversion/start` endpoint with the following parameters:

*   `image_url`: The URL of the image to convert.
*   `dithering_algorithm`: The dithering algorithm to use.
*   `color_palette`: The color palette to use.
*   `output_format`: The output format to use.
*   `x_orientation`: The X-axis orientation.
*   `z_orientation`: The Z-axis orientation.
*   `y_is_height`: Whether the Y-axis is the height.
*   `scale`: The scale of the output.
*   `split_x`: The number of horizontal splits.
*   `split_z`: The number of vertical splits.

### Check Conversion Status

To check the status of a conversion task, send a GET request to the `/api/conversion/{taskId}` endpoint, where `{taskId}` is the ID of the task.

### List Available Files

To list the available files for a conversion task, send a GET request to the `/api/conversion/{taskId}/files` endpoint, where `{taskId}` is the ID of the task.

### Download Files

To download the files for a conversion task, send a GET request to the `/api/conversion/{taskId}/download` endpoint, where `{taskId}` is the ID of the task.

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
