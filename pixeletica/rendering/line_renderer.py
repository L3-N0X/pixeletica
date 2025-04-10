"""
Line rendering for image visualization.

This module provides functionality for adding chunk boundary lines and block grid lines to images.
"""

from PIL import Image, ImageDraw
import re

from pixeletica.coordinates.chunk_calculator import (
    is_chunk_boundary_x,
    is_chunk_boundary_z,
)

# Default colors
DEFAULT_CHUNK_LINE_COLOR = "FF0000FF"  # Red with full alpha
DEFAULT_BLOCK_LINE_COLOR = "CCCCCC88"  # Light gray with partial opacity


def hex_to_rgba(hex_color):
    """
    Convert hex color string to RGBA tuple.

    Args:
        hex_color: Hex color string (#RRGGBB or RRGGBBAA)

    Returns:
        Tuple of (R, G, B, A) values
    """
    hex_color = hex_color.lstrip("#")

    if len(hex_color) == 6:
        # No alpha specified, assume fully opaque
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        a = 255
    elif len(hex_color) == 8:
        # Alpha specified
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        a = int(hex_color[6:8], 16)
    else:
        raise ValueError(f"Invalid hex color format: {hex_color}")

    return (r, g, b, a)


def validate_hex_color(hex_color):
    """
    Validate that a string is a proper hex color code.

    Args:
        hex_color: Color string to validate

    Returns:
        True if valid, False otherwise
    """
    pattern = r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$"
    return bool(re.match(pattern, hex_color))


class LineRenderer:
    """
    Renders chunk boundary lines and block grid lines on images.
    """

    def __init__(
        self,
        draw_chunk_lines=False,
        chunk_line_color=DEFAULT_CHUNK_LINE_COLOR,
        draw_block_lines=False,
        block_line_color=DEFAULT_BLOCK_LINE_COLOR,
        origin_x=0,
        origin_z=0,
    ):
        """
        Initialize the line renderer.

        Args:
            draw_chunk_lines: Whether to draw chunk boundary lines
            chunk_line_color: Color for chunk lines (hex format)
            draw_block_lines: Whether to draw block grid lines
            block_line_color: Color for block lines (hex format)
            origin_x: X-coordinate of the world origin
            origin_z: Z-coordinate of the world origin
        """
        self.draw_chunk_lines = draw_chunk_lines
        self.draw_block_lines = draw_block_lines

        # Validate and set colors
        if validate_hex_color(chunk_line_color):
            self.chunk_line_color = hex_to_rgba(chunk_line_color)
        else:
            print(f"Invalid chunk line color: {chunk_line_color}, using default")
            self.chunk_line_color = hex_to_rgba(DEFAULT_CHUNK_LINE_COLOR)

        if validate_hex_color(block_line_color):
            self.block_line_color = hex_to_rgba(block_line_color)
        else:
            print(f"Invalid block line color: {block_line_color}, using default")
            self.block_line_color = hex_to_rgba(DEFAULT_BLOCK_LINE_COLOR)

        # Calculate offsets based on origin coordinates
        from pixeletica.coordinates.chunk_calculator import get_offset_in_chunk

        self.offset_x, self.offset_z = get_offset_in_chunk(origin_x, origin_z)
        self.origin_x = origin_x
        self.origin_z = origin_z

    def add_lines_to_image(self, image):
        """
        Add chunk lines and/or block grid lines to an image.

        Args:
            image: PIL Image to add lines to

        Returns:
            New PIL Image with lines added
        """
        # Create a copy of the image to work with
        result_image = image.copy().convert("RGBA")
        width, height = result_image.size

        # Create a drawing surface
        draw = ImageDraw.Draw(result_image)

        # Draw block grid lines
        if self.draw_block_lines:
            self._draw_block_lines(draw, width, height)

        # Draw chunk boundary lines
        if self.draw_chunk_lines:
            self._draw_chunk_lines(draw, width, height)

        return result_image

    def _draw_block_lines(self, draw, width, height):
        """
        Draw block grid lines on the image.

        Args:
            draw: ImageDraw object to draw on
            width: Width of the image
            height: Height of the image
        """
        # Vertical lines (down)
        for x in range(1, width):
            draw.line([(x, 0), (x, height - 1)], fill=self.block_line_color, width=1)

        # Horizontal lines (across)
        for y in range(1, height):
            draw.line([(0, y), (width - 1, y)], fill=self.block_line_color, width=1)

    def _draw_chunk_lines(self, draw, width, height):
        """
        Draw chunk boundary lines on the image.

        Args:
            draw: ImageDraw object to draw on
            width: Width of the image
            height: Height of the image
        """
        # Vertical chunk lines
        for x in range(width):
            if is_chunk_boundary_x(x, self.offset_x):
                draw.line(
                    [(x, 0), (x, height - 1)], fill=self.chunk_line_color, width=1
                )

        # Horizontal chunk lines
        for z in range(height):
            if is_chunk_boundary_z(z, self.offset_z):
                draw.line([(0, z), (width - 1, z)], fill=self.chunk_line_color, width=1)


def apply_lines_to_image(
    image,
    draw_chunk_lines=False,
    chunk_line_color=DEFAULT_CHUNK_LINE_COLOR,
    draw_block_lines=False,
    block_line_color=DEFAULT_BLOCK_LINE_COLOR,
    origin_x=0,
    origin_z=0,
):
    """
    Convenience function to apply lines to an image.

    Args:
        image: PIL Image to add lines to
        draw_chunk_lines: Whether to draw chunk boundary lines
        chunk_line_color: Color for chunk lines (hex format)
        draw_block_lines: Whether to draw block grid lines
        block_line_color: Color for block lines (hex format)
        origin_x: X-coordinate of the world origin
        origin_z: Z-coordinate of the world origin

    Returns:
        New PIL Image with lines added
    """
    renderer = LineRenderer(
        draw_chunk_lines=draw_chunk_lines,
        chunk_line_color=chunk_line_color,
        draw_block_lines=draw_block_lines,
        block_line_color=block_line_color,
        origin_x=origin_x,
        origin_z=origin_z,
    )

    return renderer.add_lines_to_image(image)
