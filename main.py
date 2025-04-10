#!/usr/bin/env python3
"""
Pixeletica - A Minecraft block color image processor.

This is the main entry point for the Pixeletica application.
It supports both GUI and CLI modes.
"""

import os
import sys
from PIL import Image, ImageTk

# Import Pixeletica modules
from pixeletica.block_utils.block_loader import load_block_colors
from pixeletica.cli import run_cli
from pixeletica.gui.app import DitherApp


def ensure_output_dir():
    """Ensure that the output directories exist."""
    os.makedirs("./out/dithered", exist_ok=True)
    os.makedirs("./out/schematics", exist_ok=True)


def run_gui():
    """Run the application in GUI mode."""
    try:
        import tkinter as tk
    except ImportError:
        print("Error: tkinter is not available. Running in CLI mode instead.")
        run_cli()
        return

    # Create and run the GUI
    root = tk.Tk()
    app = DitherApp(root)
    root.mainloop()


def main():
    """Main entry point for the application."""
    print("==== Pixeletica Minecraft Dithering ====")

    # Ensure output directory exists
    ensure_output_dir()

    # Ask user which interface to use
    print("1. Command Line Interface")
    print("2. Graphical User Interface")

    try:
        choice = input("Select interface (1 or 2): ").strip()

        if choice == "2":
            run_gui()
        else:
            run_cli()
    except KeyboardInterrupt:
        print("\nExiting Pixeletica...")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Exiting Pixeletica...")
        sys.exit(1)


if __name__ == "__main__":
    main()
