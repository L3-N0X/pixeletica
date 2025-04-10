"""
Export settings UI component for Pixeletica.

This module provides the GUI components for configuring export settings.
"""

import tkinter as tk
from tkinter import ttk, colorchooser
import re

from pixeletica.rendering.line_renderer import (
    DEFAULT_CHUNK_LINE_COLOR,
    DEFAULT_BLOCK_LINE_COLOR,
)
from pixeletica.export.export_manager import (
    EXPORT_TYPE_WEB,
    EXPORT_TYPE_LARGE,
    EXPORT_TYPE_SPLIT,
)


class ExportSettingsFrame(ttk.LabelFrame):
    """Export settings frame for the GUI."""

    def __init__(self, parent, **kwargs):
        """Initialize the export settings frame."""
        super().__init__(parent, text="Export Settings", padding="10", **kwargs)

        # Initialize variables
        self.origin_x_var = tk.IntVar(value=0)
        self.origin_z_var = tk.IntVar(value=0)

        self.chunk_lines_var = tk.BooleanVar(value=False)
        self.chunk_line_color = DEFAULT_CHUNK_LINE_COLOR

        self.block_lines_var = tk.BooleanVar(value=False)
        self.block_line_color = DEFAULT_BLOCK_LINE_COLOR

        self.web_export_var = tk.BooleanVar(value=False)
        self.large_export_var = tk.BooleanVar(value=True)  # Default to large export
        self.split_export_var = tk.BooleanVar(value=False)
        self.split_count_var = tk.IntVar(value=4)

        self.with_lines_var = tk.BooleanVar(value=True)
        self.without_lines_var = tk.BooleanVar(value=False)

        # Create the UI
        self.create_coordinate_settings()
        self.create_line_settings()
        self.create_export_type_settings()
        self.create_line_version_settings()

    def create_coordinate_settings(self):
        """Create coordinate settings UI."""
        coord_frame = ttk.LabelFrame(self, text="Minecraft Coordinates", padding="5")
        coord_frame.pack(fill=tk.X, pady=5)

        ttk.Label(coord_frame, text="Origin X:").grid(
            row=0, column=0, padx=5, pady=2, sticky=tk.W
        )
        ttk.Entry(coord_frame, textvariable=self.origin_x_var, width=6).grid(
            row=0, column=1, padx=5, pady=2
        )

        ttk.Label(coord_frame, text="Origin Z:").grid(
            row=1, column=0, padx=5, pady=2, sticky=tk.W
        )
        ttk.Entry(coord_frame, textvariable=self.origin_z_var, width=6).grid(
            row=1, column=1, padx=5, pady=2
        )

        ttk.Label(
            coord_frame, text="(Coordinates of the top-left corner in Minecraft world)"
        ).grid(row=0, column=2, rowspan=2, padx=5, pady=2, sticky=tk.W)

    def create_line_settings(self):
        """Create line settings UI."""
        line_frame = ttk.LabelFrame(self, text="Line Settings", padding="5")
        line_frame.pack(fill=tk.X, pady=5)

        # Chunk lines
        chunk_frame = ttk.Frame(line_frame)
        chunk_frame.pack(fill=tk.X, pady=2)

        ttk.Checkbutton(
            chunk_frame, text="Show chunk lines", variable=self.chunk_lines_var
        ).pack(side=tk.LEFT, padx=5)

        self.chunk_color_btn = ttk.Button(
            chunk_frame, text="Select Color", command=lambda: self.select_color("chunk")
        )
        self.chunk_color_btn.pack(side=tk.LEFT, padx=5)

        self.chunk_color_preview = tk.Canvas(
            chunk_frame,
            width=20,
            height=20,
            bg=self._hex_to_rgb(DEFAULT_CHUNK_LINE_COLOR),
        )
        self.chunk_color_preview.pack(side=tk.LEFT, padx=5)

        # Block lines
        block_frame = ttk.Frame(line_frame)
        block_frame.pack(fill=tk.X, pady=2)

        ttk.Checkbutton(
            block_frame, text="Show block grid lines", variable=self.block_lines_var
        ).pack(side=tk.LEFT, padx=5)

        self.block_color_btn = ttk.Button(
            block_frame, text="Select Color", command=lambda: self.select_color("block")
        )
        self.block_color_btn.pack(side=tk.LEFT, padx=5)

        self.block_color_preview = tk.Canvas(
            block_frame,
            width=20,
            height=20,
            bg=self._hex_to_rgb(DEFAULT_BLOCK_LINE_COLOR),
        )
        self.block_color_preview.pack(side=tk.LEFT, padx=5)

    def create_export_type_settings(self):
        """Create export type settings UI."""
        export_frame = ttk.LabelFrame(self, text="Export Types", padding="5")
        export_frame.pack(fill=tk.X, pady=5)

        # Web export
        ttk.Checkbutton(
            export_frame,
            text="Web-optimized tiles (512×512)",
            variable=self.web_export_var,
        ).pack(anchor=tk.W, padx=5, pady=2)

        # Large image export
        ttk.Checkbutton(
            export_frame, text="Single large image", variable=self.large_export_var
        ).pack(anchor=tk.W, padx=5, pady=2)

        # Split export
        split_frame = ttk.Frame(export_frame)
        split_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Checkbutton(
            split_frame, text="Split into parts:", variable=self.split_export_var
        ).pack(side=tk.LEFT)

        ttk.Entry(split_frame, textvariable=self.split_count_var, width=3).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(split_frame, text="equal parts").pack(side=tk.LEFT)

    def create_line_version_settings(self):
        """Create line version settings UI with options for different line versions."""
        versions_frame = ttk.LabelFrame(self, text="Version Options", padding="5")
        versions_frame.pack(fill=tk.X, pady=5)

        self.no_lines_var = tk.BooleanVar(value=False)
        self.only_block_lines_var = tk.BooleanVar(value=False)
        self.only_chunk_lines_var = tk.BooleanVar(value=False)
        self.both_lines_var = tk.BooleanVar(value=True)  # Default to both lines

        ttk.Checkbutton(
            versions_frame,
            text="No lines",
            variable=self.no_lines_var,
        ).pack(anchor=tk.W, padx=5, pady=2)

        ttk.Checkbutton(
            versions_frame,
            text="Only block lines",
            variable=self.only_block_lines_var,
        ).pack(anchor=tk.W, padx=5, pady=2)

        ttk.Checkbutton(
            versions_frame,
            text="Only chunk lines",
            variable=self.only_chunk_lines_var,
        ).pack(anchor=tk.W, padx=5, pady=2)

        ttk.Checkbutton(
            versions_frame,
            text="Both lines (block and chunk)",
            variable=self.both_lines_var,
        ).pack(anchor=tk.W, padx=5, pady=2)

    def select_color(self, line_type):
        """Open a color chooser dialog and update the selected color, including alpha."""
        current_color = (
            self.chunk_line_color if line_type == "chunk" else self.block_line_color
        )
        rgb_color = self._hex_to_rgb(current_color)

        # Open color chooser with alpha support
        color = colorchooser.askcolor(
            initialcolor=rgb_color,
            title=f"Select {line_type.capitalize()} Line Color",
            color=rgb_color,  # Initial color for the dialog
        )

        if color[1]:  # If a color was selected (not cancelled)
            hex_color = color[1]
            if hex_color:
                hex_color = hex_color.lstrip("#")
                # Ensure it's 8 characters long (RGBA)
                if len(hex_color) == 6:
                    hex_color += "ff"  # Default alpha to opaque if not provided

                # Update the color and preview
                if line_type == "chunk":
                    self.chunk_line_color = "#" + hex_color
                    self.chunk_color_preview.config(
                        bg=self._hex_to_rgb("#" + hex_color)
                    )
                else:
                    self.block_line_color = "#" + hex_color
                    self.block_color_preview.config(
                        bg=self._hex_to_rgb("#" + hex_color)
                    )

    def _hex_to_rgb(self, hex_color):
        """Convert hex color to RGB format for Tkinter, ignoring alpha."""
        hex_color = hex_color.lstrip("#")

        # If alpha is present, ignore it for Tkinter color preview
        if len(hex_color) == 8:
            hex_color = hex_color[:6]

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        return f"#{r:02x}{g:02x}{b:02x}"

    def get_export_settings(self):
        """Get the current export settings."""
        # Build export types list
        export_types = []
        if self.web_export_var.get():
            export_types.append(EXPORT_TYPE_WEB)
        if self.large_export_var.get():
            export_types.append(EXPORT_TYPE_LARGE)
        if self.split_export_var.get():
            export_types.append(EXPORT_TYPE_SPLIT)

        # Ensure at least one export type is selected
        if not export_types:
            export_types.append(EXPORT_TYPE_LARGE)

        # Ensure at least one version is selected
        with_lines = self.with_lines_var.get()
        without_lines = self.without_lines_var.get()

        version_options = {
            "no_lines": self.no_lines_var.get(),
            "only_block_lines": self.only_block_lines_var.get(),
            "only_chunk_lines": self.only_chunk_lines_var.get(),
            "both_lines": self.both_lines_var.get(),
        }

        # Ensure at least one version is selected
        if not any(version_options.values()):
            version_options["both_lines"] = (
                True  # Default to both lines if none selected
            )

        return {
            "origin_x": self.origin_x_var.get(),
            "origin_z": self.origin_z_var.get(),
            "draw_chunk_lines": self.chunk_lines_var.get(),
            "chunk_line_color": self.chunk_line_color,
            "draw_block_lines": self.block_lines_var.get(),
            "block_line_color": self.block_line_color,
            "export_types": export_types,
            "split_count": self.split_count_var.get(),
            "version_options": version_options,
        }
