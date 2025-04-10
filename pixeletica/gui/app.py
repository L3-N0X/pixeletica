"""
Main GUI application for Pixeletica.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk

from pixeletica.block_utils.block_loader import load_block_colors, get_block_colors
from pixeletica.dithering import get_algorithm_by_name
from pixeletica.image_ops import load_image, resize_image, save_dithered_image


class DitherApp:
    """Main GUI application class for Pixeletica."""

    def __init__(self, root):
        """
        Initialize the application.

        Args:
            root: tkinter root window
        """
        self.root = root
        root.title("Pixeletica Minecraft Dithering")
        root.geometry("800x600")

        # Set style
        style = ttk.Style()
        try:
            style.theme_use("clam")  # Use clam theme if available
        except tk.TclError:
            # Fallback if theme not available
            pass

        # Main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create the UI components
        self._create_image_selection(main_frame)
        self._create_resize_options(main_frame)
        self._create_dithering_options(main_frame)
        self._create_action_buttons(main_frame)
        self._create_status_bar(root)
        self._create_preview_area(main_frame)

        # Initialize
        self.original_img = None
        self.resized_img = None
        self.dithered_img = None
        self.photo_img = None  # To keep reference to prevent garbage collection

        # Load block colors
        if load_block_colors("./minecraft/block-colors.csv"):
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

    def _create_resize_options(self, parent):
        """Create resize options frame."""
        resize_frame = ttk.LabelFrame(parent, text="Resize Options", padding="10")
        resize_frame.pack(fill=tk.X, pady=10)

        ttk.Label(resize_frame, text="Width:").grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.width_var = tk.StringVar()
        ttk.Entry(resize_frame, textvariable=self.width_var, width=10).grid(
            row=0, column=1, padx=5, pady=5
        )

        ttk.Label(resize_frame, text="Height:").grid(
            row=1, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.height_var = tk.StringVar()
        ttk.Entry(resize_frame, textvariable=self.height_var, width=10).grid(
            row=1, column=1, padx=5, pady=5
        )

        ttk.Label(resize_frame, text="(Leave empty to maintain aspect ratio)").grid(
            row=0, column=2, rowspan=2, padx=5, pady=5, sticky=tk.W
        )

    def _create_dithering_options(self, parent):
        """Create dithering algorithm options."""
        dither_frame = ttk.LabelFrame(parent, text="Dithering Algorithm", padding="10")
        dither_frame.pack(fill=tk.X, pady=10)

        self.algorithm_var = tk.StringVar(value="floyd_steinberg")

        # Create radio buttons for each algorithm
        ttk.Radiobutton(
            dither_frame, text="No Dithering", variable=self.algorithm_var, value="none"
        ).pack(anchor=tk.W, pady=5)

        ttk.Radiobutton(
            dither_frame,
            text="Floyd-Steinberg",
            variable=self.algorithm_var,
            value="floyd_steinberg",
        ).pack(anchor=tk.W, pady=5)

        ttk.Radiobutton(
            dither_frame,
            text="Ordered Dithering",
            variable=self.algorithm_var,
            value="ordered",
        ).pack(anchor=tk.W, pady=5)

        ttk.Radiobutton(
            dither_frame,
            text="Random Dithering",
            variable=self.algorithm_var,
            value="random",
        ).pack(anchor=tk.W, pady=5)

    def _create_action_buttons(self, parent):
        """Create action buttons."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=20)

        ttk.Button(btn_frame, text="Preview", command=self.preview_dithering).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            btn_frame, text="Process and Save", command=self.process_and_save
        ).pack(side=tk.RIGHT, padx=5)

    def _create_status_bar(self, parent):
        """Create status bar at the bottom of the window."""
        self.status_var = tk.StringVar()
        ttk.Label(
            parent, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        ).pack(side=tk.BOTTOM, fill=tk.X)

    def _create_preview_area(self, parent):
        """Create the preview area for image display."""
        preview_frame = ttk.LabelFrame(parent, text="Preview", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.canvas = tk.Canvas(preview_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

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
        if resized_img:
            # Apply dithering
            self.status_var.set("Applying dithering...")
            self.root.update_idletasks()

            dithered_img, algorithm_name, metadata_info = self.apply_dithering(
                resized_img
            )
            if dithered_img:
                # Save the dithered image with metadata
                try:
                    block_ids = (
                        metadata_info.get("block_ids") if metadata_info else None
                    )
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
                except Exception as e:
                    self.status_var.set(f"Error saving image: {e}")

    def display_image(self, img):
        """Display an image in the preview area."""
        if img is None:
            return

        # Clear canvas
        self.canvas.delete("all")

        # Resize image to fit canvas if needed
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1:  # Canvas not yet realized
            canvas_width = 400
            canvas_height = 300

        img_width, img_height = img.size

        # Calculate scale factor to fit image within canvas
        scale_width = canvas_width / img_width if img_width > canvas_width else 1
        scale_height = canvas_height / img_height if img_height > canvas_height else 1
        scale = min(scale_width, scale_height)

        # Resize image for display
        if scale < 1:
            display_width = int(img_width * scale)
            display_height = int(img_height * scale)
            display_img = img.resize((display_width, display_height), Image.LANCZOS)
        else:
            display_img = img.copy()

        # Convert to PhotoImage and display
        self.photo_img = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.photo_img,
            anchor=tk.CENTER,
        )
