"""
Main GUI application for Pixeletica.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import platform
from PIL import Image, ImageTk

from src.pixeletica.block_utils.block_loader import load_block_colors, get_block_colors
from src.pixeletica.dithering import get_algorithm_by_name
from src.pixeletica.image_ops import load_image, resize_image, save_dithered_image
from src.pixeletica.gui.export_settings import ExportSettingsFrame
from src.pixeletica.rendering.block_renderer import render_blocks_from_block_ids
from src.pixeletica.export.export_manager import export_processed_image


class DitherApp:
    """Main GUI application class for Pixeletica."""

    def show_completion_alert(self, folder_path):
        """
        Show a success alert and ask if the user wants to open the output folder.

        Args:
            folder_path: Path to the folder containing the exported files
        """
        result = messagebox.askquestion(
            "Conversion Complete",
            "Conversion completed successfully!\n\nWould you like to open the output folder?",
            icon="info",
        )

        if result == "yes":
            self.open_folder(folder_path)

    def open_folder(self, path):
        """
        Open a folder in the file explorer.

        Args:
            path: Path to the folder to open
        """
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", path], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", path], check=True)
            return True
        except Exception as e:
            self.logger.error(f"Error opening folder: {e}")
            return False

    def __init__(self, root):
        """
        Initialize the application.

        Args:
            root: tkinter root window
        """
        self.root = root
        root.title("Pixeletica Minecraft Dithering")
        root.geometry("1000x700")  # Increased window size

        # Configure logging
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger("pixeletica")

        # Log application start
        self.logger.info("Application started")

        # Use default theme
        style = ttk.Style()

        # Create status bar at the bottom
        self._create_status_bar(root)

        # Main layout - split into two panes horizontally
        main_frame = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left side - settings with scrolling capability
        left_frame = ttk.Frame(main_frame)
        main_frame.add(left_frame, weight=1)

        # Create a canvas for scrolling
        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)

        # Settings frame inside the canvas
        settings_frame = ttk.Frame(canvas)

        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Add the settings frame to the canvas
        canvas_frame = canvas.create_window((0, 0), window=settings_frame, anchor="nw")

        # Make the settings frame expand to the width of the canvas
        def configure_frame(event):
            canvas.itemconfig(canvas_frame, width=event.width)

        canvas.bind("<Configure>", configure_frame)

        # Update the scrollregion when the size of the settings frame changes
        def on_frame_configured(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        settings_frame.bind("<Configure>", on_frame_configured)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Right side - preview
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="10")
        main_frame.add(preview_frame, weight=2)

        # Create the preview canvas
        self.canvas = tk.Canvas(preview_frame)  # Using default background
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind resize event to update image display when panel size changes
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Create the settings UI components in the left frame
        self._create_image_selection(settings_frame)
        self._create_dimensions_section(settings_frame)
        self._create_dithering_options(settings_frame)
        self._create_schematic_options(settings_frame)
        # Add export settings frame directly, not nested
        self.export_settings = ExportSettingsFrame(settings_frame)
        self.export_settings.pack(fill=tk.X, pady=5)
        self._create_action_buttons(settings_frame)

        # Initialize
        self.original_img = None
        self.resized_img = None
        self.dithered_img = None
        self.photo_img = None  # To keep reference to prevent garbage collection

        # Load block colors
        if load_block_colors("./src/minecraft/block-colors.csv"):
            self.status_var.set(
                f"Ready - Loaded {len(get_block_colors())} Minecraft block colors"
            )
        else:
            self.status_var.set("Error: Failed to load block colors")

    def _create_image_selection(self, parent):
        """Create image selection frame."""
        img_frame = ttk.LabelFrame(parent, text="Image Selection", padding="10")
        img_frame.pack(fill=tk.X, pady=10)

        self.img_path_var = tk.StringVar()
        ttk.Entry(img_frame, textvariable=self.img_path_var, width=50).pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True
        )
        ttk.Button(img_frame, text="Browse...", command=self.browse_image).pack(
            side=tk.RIGHT, padx=5
        )

    def _create_dimensions_section(self, parent):
        """Create dimensions section frame."""
        dim_frame = ttk.LabelFrame(parent, text="Dimensions", padding="10")
        dim_frame.pack(fill=tk.X, pady=5)

        # Create dimensions controls
        dim_controls = ttk.Frame(dim_frame)
        dim_controls.pack(fill=tk.X, pady=5)

        ttk.Label(dim_controls, text="Width:").grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.width_var = tk.StringVar()
        ttk.Entry(dim_controls, textvariable=self.width_var, width=10).grid(
            row=0, column=1, padx=5, pady=5
        )

        ttk.Label(dim_controls, text="Height:").grid(
            row=1, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.height_var = tk.StringVar()
        ttk.Entry(dim_controls, textvariable=self.height_var, width=10).grid(
            row=1, column=1, padx=5, pady=5
        )

        ttk.Label(dim_controls, text="(Leave empty to maintain aspect ratio)").grid(
            row=0, column=2, rowspan=2, padx=5, pady=5, sticky=tk.W
        )

    def _create_dithering_options(self, parent):
        """Create dithering algorithm options."""
        dither_frame = ttk.LabelFrame(parent, text="Dithering Algorithm", padding="10")
        dither_frame.pack(fill=tk.X, pady=5)

        self.algorithm_var = tk.StringVar(value="floyd_steinberg")

        # Create radio buttons for each algorithm
        ttk.Radiobutton(
            dither_frame,
            text="Floyd-Steinberg",
            variable=self.algorithm_var,
            value="floyd_steinberg",
        ).pack(anchor=tk.W, pady=3)

        ttk.Radiobutton(
            dither_frame,
            text="Ordered Dithering",
            variable=self.algorithm_var,
            value="ordered",
        ).pack(anchor=tk.W, pady=3)

        ttk.Radiobutton(
            dither_frame,
            text="Random Dithering",
            variable=self.algorithm_var,
            value="random",
        ).pack(anchor=tk.W, pady=3)

    def _create_schematic_options(self, parent):
        """Create options for Litematica schematic generation."""
        schematic_frame = ttk.LabelFrame(parent, text="Schematic", padding="10")
        schematic_frame.pack(fill=tk.X, pady=5)

        # Option to enable/disable schematic generation
        self.generate_schematic_var = tk.BooleanVar(value=False)
        self.generate_schematic_checkbox = ttk.Checkbutton(
            schematic_frame,
            text="Generate Litematica Schematic",
            variable=self.generate_schematic_var,
            command=self.toggle_schematic_options,
        )
        self.generate_schematic_checkbox.pack(pady=5, anchor=tk.W)

        # Create a frame for schematic options
        self.schematic_options_frame = ttk.Frame(schematic_frame)
        self.schematic_options_frame.pack(fill=tk.X, pady=5)

        # Author field
        ttk.Label(self.schematic_options_frame, text="Author:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.author_var = tk.StringVar(value="L3-N0X - pixeletica")
        self.author_entry = ttk.Entry(
            self.schematic_options_frame, textvariable=self.author_var
        )
        self.author_entry.grid(row=0, column=1, sticky=tk.W + tk.E, padx=5, pady=2)

        # Name field
        ttk.Label(self.schematic_options_frame, text="Name:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.schematic_name_var = tk.StringVar()
        self.schematic_name_entry = ttk.Entry(
            self.schematic_options_frame, textvariable=self.schematic_name_var
        )
        self.schematic_name_entry.grid(
            row=1, column=1, sticky=tk.W + tk.E, padx=5, pady=2
        )

        # Description field
        ttk.Label(self.schematic_options_frame, text="Description:").grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.description_var = tk.StringVar()
        self.description_entry = ttk.Entry(
            self.schematic_options_frame, textvariable=self.description_var
        )
        self.description_entry.grid(row=2, column=1, sticky=tk.W + tk.E, padx=5, pady=2)

        # Initially disable the schematic options
        self.toggle_schematic_options()

    def toggle_schematic_options(self):
        """Enable or disable schematic options based on checkbox."""
        if self.generate_schematic_var.get():
            for child in self.schematic_options_frame.winfo_children():
                child.configure(state="normal")
        else:
            for child in self.schematic_options_frame.winfo_children():
                if isinstance(child, ttk.Entry) or isinstance(child, ttk.Combobox):
                    child.configure(state="disabled")

    def _create_action_buttons(self, parent):
        """Create action buttons."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="Preview", command=self.preview_dithering).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            btn_frame, text="Process and Export", command=self.process_and_export
        ).pack(side=tk.RIGHT, padx=5)

    def _create_status_bar(self, parent):
        """Create status bar at the bottom of the window."""
        self.status_var = tk.StringVar()
        ttk.Label(
            parent, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        ).pack(side=tk.BOTTOM, fill=tk.X)

    def browse_image(self):
        """Open file dialog to choose an image file."""
        filepath = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                ("All files", "*.*"),
            ],
        )
        if filepath:
            self.img_path_var.set(filepath)
            self.load_image(filepath)

    def load_image(self, path):
        """Load image from path and display it."""
        try:
            self.original_img = load_image(path)
            if self.original_img:
                self.status_var.set(
                    f"Image loaded: {path} - {self.original_img.width}x{self.original_img.height}"
                )
                self.display_image(self.original_img)
            else:
                self.status_var.set("Failed to load image")
        except Exception as e:
            self.status_var.set(f"Error loading image: {e}")

    def resize_image_from_inputs(self):
        """Resize image based on width/height inputs."""
        if self.original_img is None:
            self.status_var.set("Error: No image loaded")
            return None

        width_input = self.width_var.get().strip()
        height_input = self.height_var.get().strip()

        target_width = int(width_input) if width_input else None
        target_height = int(height_input) if height_input else None

        try:
            self.resized_img = resize_image(
                self.original_img, target_width, target_height
            )

            if self.resized_img:
                actual_width, actual_height = self.resized_img.size
                self.status_var.set(f"Image resized to: {actual_width}x{actual_height}")

            return self.resized_img
        except Exception as e:
            self.status_var.set(f"Error resizing image: {e}")
            return None

    def apply_dithering(self, img):
        """Apply selected dithering algorithm to the image."""
        if img is None:
            return None, None, None

        algorithm_name = self.algorithm_var.get()

        dither_func, algorithm_id = get_algorithm_by_name(algorithm_name)

        if dither_func is None:
            self.status_var.set(f"Unknown algorithm: {algorithm_name}")
            return None, None, None

        try:
            # Track processing time
            import time

            start_time = time.time()
            result_img, block_ids = dither_func(img)
            processing_time = time.time() - start_time

            return (
                result_img,
                algorithm_id,
                {"block_ids": block_ids, "processing_time": processing_time},
            )
        except Exception as e:
            self.status_var.set(f"Error applying dithering: {e}")
            return None, None, None

    def preview_dithering(self):
        """Generate and display a preview of the dithered image."""
        resized_img = self.resize_image_from_inputs()
        if resized_img:
            self.status_var.set("Applying dithering for preview...")
            self.root.update_idletasks()

            dithered_img, algorithm_name, metadata_info = self.apply_dithering(
                resized_img
            )
            if dithered_img:
                self.dithered_img = dithered_img
                self.display_image(dithered_img)

                # Show processing time in status
                if metadata_info and "processing_time" in metadata_info:
                    processing_time = metadata_info["processing_time"]
                    self.status_var.set(
                        f"Preview: {algorithm_name} dithering - Processing time: {processing_time:.2f}s"
                    )
                else:
                    self.status_var.set(f"Preview: {algorithm_name} dithering")
            else:
                self.status_var.set("Failed to apply dithering algorithm")

    def process_and_save(self):
        """Process the image with the selected algorithm and save the result."""
        if not self.img_path_var.get():
            self.status_var.set("Error: No image selected")
            return

        # Resize image
        resized_img = self.resize_image_from_inputs()
        if not resized_img:
            return

        # Apply dithering
        self.status_var.set("Applying dithering...")
        self.root.update_idletasks()

        dithered_img, algorithm_name, metadata_info = self.apply_dithering(resized_img)
        if not dithered_img:
            self.status_var.set("Failed to apply dithering algorithm")
            return

        # Save the dithered image with metadata
        try:
            block_ids = metadata_info.get("block_ids") if metadata_info else None
            processing_time = (
                metadata_info.get("processing_time", 0) if metadata_info else 0
            )

            saved_path = save_dithered_image(
                dithered_img,
                self.img_path_var.get(),
                algorithm_name,
                block_ids=block_ids,
                processing_time=processing_time,
            )

            self.status_var.set(
                f"Saved: {saved_path} (processing time: {processing_time:.2f}s)"
            )
            self.dithered_img = dithered_img
            self.display_image(dithered_img)

            # Export with textures if settings are available
            export_settings = self.export_settings.get_export_settings()
            export_dir = None

            if any(export_settings["export_types"]):
                try:
                    self.status_var.set("Rendering blocks with textures...")
                    self.root.update_idletasks()

                    # Render blocks with textures
                    block_image = render_blocks_from_block_ids(block_ids)

                    if block_image:
                        self.status_var.set("Exporting images...")
                        self.root.update_idletasks()

                        base_name = os.path.splitext(
                            os.path.basename(self.img_path_var.get())
                        )[0]

                        # Export with the configured settings
                        export_results = export_processed_image(
                            block_image,
                            base_name,
                            export_types=export_settings["export_types"],
                            origin_x=export_settings["origin_x"],
                            origin_z=export_settings["origin_z"],
                            draw_chunk_lines=export_settings["draw_chunk_lines"],
                            chunk_line_color=export_settings["chunk_line_color"],
                            draw_block_lines=export_settings["draw_block_lines"],
                            block_line_color=export_settings["block_line_color"],
                            split_count=export_settings["split_count"],
                            include_lines_version=export_settings.get(
                                "with_lines", True
                            ),
                            include_no_lines_version=export_settings.get(
                                "without_lines", False
                            ),
                            version_options=export_settings.get("version_options", {}),
                            algorithm_name=algorithm_name,
                        )

                        export_dir = export_results["export_dir"]
                        self.status_var.set(
                            f"Export successful! Files saved to: {export_dir}"
                        )

                        # Update the original metadata with export information
                        metadata_path = os.path.splitext(saved_path)[0] + ".json"
                        if os.path.exists(metadata_path):
                            from src.pixeletica.metadata import (
                                load_metadata_json,
                                save_metadata_json,
                            )

                            metadata = load_metadata_json(metadata_path)
                            metadata["export_settings"] = export_settings
                            metadata["exports"] = export_results
                            save_metadata_json(metadata, saved_path)
                    else:
                        self.status_var.set(
                            "Error: Failed to render blocks with textures"
                        )
                except Exception as e:
                    self.status_var.set(f"Error during export: {e}")

            # Generate schematic if requested
            schematic_path = None
            if self.generate_schematic_var.get() and block_ids:
                try:
                    # Set default name if empty
                    if not self.schematic_name_var.get():
                        image_name = os.path.basename(self.img_path_var.get())
                        base_name = os.path.splitext(image_name)[0]
                        self.schematic_name_var.set(base_name)

                    # Import schematic generator
                    from src.pixeletica.schematic_generator import generate_schematic

                    # Prepare metadata
                    metadata = {
                        "author": self.author_var.get(),
                        "name": self.schematic_name_var.get(),
                        "description": self.description_var.get(),
                    }

                    # Generate schematic
                    self.status_var.set("Generating Litematica schematic...")
                    self.root.update_idletasks()

                    # Get Y-coordinate from export settings if available
                    origin_y = export_settings.get("origin_y", 0)

                    schematic_path = generate_schematic(
                        block_ids,
                        self.img_path_var.get(),
                        algorithm_name,
                        metadata,
                        origin_x=export_settings["origin_x"],
                        origin_y=origin_y,
                        origin_z=export_settings["origin_z"],
                    )

                    if export_dir:
                        self.status_var.set(
                            f"Process complete! Exported images to: {export_dir} and schematic to: {schematic_path}"
                        )
                    else:
                        self.status_var.set(f"Saved schematic to: {schematic_path}")
                except Exception as e:
                    self.status_var.set(f"Error generating schematic: {e}")

            # Show completion alert if we have files to show
            if export_dir:
                self.show_completion_alert(export_dir)

        except Exception as e:
            self.status_var.set(f"Error saving image: {e}")

    def process_and_export(self):
        """Process, save and export the image in one operation."""
        if not self.img_path_var.get():
            self.status_var.set("Error: No image selected")
            return

        # Step 1: Resize image
        resized_img = self.resize_image_from_inputs()
        if not resized_img:
            return

        # Step 2: Apply dithering
        self.status_var.set("Applying dithering...")
        self.root.update_idletasks()

        dithered_img, algorithm_name, metadata_info = self.apply_dithering(resized_img)
        if not dithered_img:
            self.status_var.set("Failed to apply dithering algorithm")
            return

        # Save dithered image and display it
        try:
            block_ids = metadata_info.get("block_ids") if metadata_info else None
            processing_time = (
                metadata_info.get("processing_time", 0) if metadata_info else 0
            )

            saved_path = save_dithered_image(
                dithered_img,
                self.img_path_var.get(),
                algorithm_name,
                block_ids=block_ids,
                processing_time=processing_time,
            )
            self.status_var.set(
                f"Saved: {saved_path} (processing time: {processing_time:.2f}s)"
            )
            self.dithered_img = dithered_img
            self.display_image(dithered_img)
            self.block_ids = block_ids

            # Step 3: Export with textures
            export_settings = self.export_settings.get_export_settings()
            if any(export_settings["export_types"]):
                self.status_var.set("Rendering blocks with textures...")
                self.root.update_idletasks()

                # Render blocks with textures
                block_image = render_blocks_from_block_ids(block_ids)

                if block_image:
                    self.status_var.set("Exporting images...")
                    self.root.update_idletasks()

                    # Get base name for export
                    base_name = os.path.splitext(
                        os.path.basename(self.img_path_var.get())
                    )[0]

                    # Apply version options from line settings
                    version_options = export_settings["version_options"]

                    # Export with the configured settings
                    export_results = export_processed_image(
                        block_image,
                        base_name,
                        export_types=export_settings["export_types"],
                        origin_x=export_settings["origin_x"],
                        origin_z=export_settings["origin_z"],
                        draw_chunk_lines=export_settings["draw_chunk_lines"],
                        chunk_line_color=export_settings["chunk_line_color"],
                        draw_block_lines=export_settings["draw_block_lines"],
                        block_line_color=export_settings["block_line_color"],
                        split_count=export_settings["split_count"],
                        version_options=version_options,
                        algorithm_name=algorithm_name,
                    )

                    # Update the metadata with export information
                    metadata_path = os.path.splitext(saved_path)[0] + ".json"
                    if os.path.exists(metadata_path):
                        from src.pixeletica.metadata import (
                            load_metadata_json,
                            save_metadata_json,
                        )

                        metadata = load_metadata_json(metadata_path)
                        metadata["export_settings"] = export_settings
                        metadata["exports"] = export_results
                        save_metadata_json(metadata, saved_path)

                    # Step 4: Generate schematic if requested
                    if self.generate_schematic_var.get():
                        try:
                            # Set default name if empty
                            if not self.schematic_name_var.get():
                                image_name = os.path.basename(self.img_path_var.get())
                                base_name = os.path.splitext(image_name)[0]
                                self.schematic_name_var.set(base_name)

                            # Import schematic generator
                            from src.pixeletica.schematic_generator import (
                                generate_schematic,
                            )

                            # Prepare metadata
                            schematic_metadata = {
                                "author": self.author_var.get(),
                                "name": self.schematic_name_var.get(),
                                "description": self.description_var.get(),
                            }

                            # Generate schematic
                            self.status_var.set("Generating Litematica schematic...")
                            self.root.update_idletasks()

                            # Get Y-coordinate from export settings if available
                            origin_y = export_settings.get("origin_y", 0)

                            # Generate schematic with origin coordinates
                            schematic_path = generate_schematic(
                                block_ids,
                                self.img_path_var.get(),
                                algorithm_name,
                                schematic_metadata,
                                origin_x=export_settings["origin_x"],
                                origin_y=origin_y,  # Use Y-coordinate if available
                                origin_z=export_settings["origin_z"],
                            )

                            self.status_var.set(
                                f"Process complete! Exported images to: {export_results['export_dir']} and schematic to: {schematic_path}"
                            )

                            # Show success alert and ask to open folder
                            success_message = f"Conversion completed successfully!\n\nImages exported to: {export_results['export_dir']}\nSchematic saved to: {schematic_path}"
                            self.show_completion_alert(export_results["export_dir"])

                        except Exception as e:
                            self.status_var.set(f"Error generating schematic: {e}")
                    else:
                        self.status_var.set(
                            f"Process complete! Exported images to: {export_results['export_dir']}"
                        )

                        # Show success alert and ask to open folder
                        success_message = f"Conversion completed successfully!\n\nImages exported to: {export_results['export_dir']}"
                        self.show_completion_alert(export_results["export_dir"])
                else:
                    self.status_var.set("Error: Failed to render blocks with textures")
        except Exception as e:
            self.status_var.set(f"Error during processing: {e}")

    def export_images(self):
        """Export images using current export settings."""
        if self.dithered_img is None:
            self.status_var.set(
                "Error: No processed image to export. Please preview or process an image first."
            )
            return

        # Get metadata for the current dithered image
        # We need block_ids for rendering with block textures
        algorithm_name = self.algorithm_var.get()
        _, algorithm_id = get_algorithm_by_name(algorithm_name)

        # Check if we have a processed image with block IDs
        if not hasattr(self, "block_ids"):
            # If not, we need to reprocess the image to get block IDs
            self.status_var.set("Preparing image for export...")
            self.root.update_idletasks()

            # Apply dithering to get block IDs
            _, _, metadata_info = self.apply_dithering(self.resized_img)
            if metadata_info and "block_ids" in metadata_info:
                self.block_ids = metadata_info["block_ids"]
            else:
                self.status_var.set("Error: Unable to generate block IDs for export.")
                return

        # Export with textures using the export settings
        export_settings = self.export_settings.get_export_settings()
        if any(export_settings["export_types"]):
            try:
                self.status_var.set("Rendering blocks with textures...")
                self.root.update_idletasks()

                # Render blocks with textures
                block_image = render_blocks_from_block_ids(self.block_ids)

                if block_image:
                    self.status_var.set("Exporting images...")
                    self.root.update_idletasks()

                    # Get base name for export
                    if self.img_path_var.get():
                        base_name = os.path.splitext(
                            os.path.basename(self.img_path_var.get())
                        )[0]
                    else:
                        base_name = f"pixeletica_export_{algorithm_id}"

                    # Apply version options from line settings
                    version_options = export_settings["version_options"]

                    # Export with the configured settings
                    export_results = export_processed_image(
                        block_image,
                        base_name,
                        export_types=export_settings["export_types"],
                        origin_x=export_settings["origin_x"],
                        origin_z=export_settings["origin_z"],
                        draw_chunk_lines=export_settings["draw_chunk_lines"],
                        chunk_line_color=export_settings["chunk_line_color"],
                        draw_block_lines=export_settings["draw_block_lines"],
                        block_line_color=export_settings["block_line_color"],
                        split_count=export_settings["split_count"],
                        version_options=version_options,
                        algorithm_name=algorithm_id,
                    )

                    export_dir = export_results["export_dir"]
                    self.status_var.set(
                        f"Export successful! Files saved to: {export_dir}"
                    )

                    # Show success alert and ask to open folder
                    self.show_completion_alert(export_dir)
                else:
                    self.status_var.set("Error: Failed to render blocks with textures")
            except Exception as e:
                self.status_var.set(f"Error during export: {e}")
        else:
            self.status_var.set("Error: No export types selected in Export Settings")

    def _on_canvas_resize(self, event):
        """Handle canvas resize events to update the displayed image."""
        # Check if we need to redisplay the image
        if hasattr(self, "dithered_img") and self.dithered_img is not None:
            # Log the resize event
            self.logger.info(f"Canvas resized to: {event.width}x{event.height}")
            # Redisplay the current image to fit the new size
            self.display_image(self.dithered_img)
        elif hasattr(self, "original_img") and self.original_img is not None:
            # If no dithered image, display the original
            self.display_image(self.original_img)

    def display_image(self, img):
        """Display an image in the preview area."""
        if img is None:
            return

        try:
            # Clear canvas
            self.canvas.delete("all")

            # Resize image to fit canvas if needed
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1:  # Canvas not yet realized
                canvas_width = 400
                canvas_height = 300

            img_width, img_height = img.size

            # Calculate scale factor to fit image within canvas - always scale to fill the available space
            scale_width = (
                canvas_width / img_width
            )  # Always calculate scaling factor, even for small images
            scale_height = canvas_height / img_height
            scale = min(
                scale_width, scale_height
            )  # Use the smaller scaling factor to keep aspect ratio

            # Always resize image to fill available space, using NEAREST for pixel art clarity
            display_width = int(img_width * scale)
            display_height = int(img_height * scale)
            display_img = img.resize((display_width, display_height), Image.NEAREST)

            # Convert to PhotoImage and display
            self.photo_img = ImageTk.PhotoImage(display_img)
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.photo_img,
                anchor=tk.CENTER,
            )
        except Exception as e:
            # Log any errors during image display
            self.logger.error(f"Error displaying image: {e}")
            self.status_var.set(f"Error displaying image: {e}")
