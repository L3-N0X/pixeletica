#!/usr/bin/env python3
"""
Pixeletica - A Minecraft block color image processor.

This is the main entry point for the Pixeletica application.
It supports GUI, API, and CLI operating modes.

Available modes:
- GUI (default): A graphical user interface for interactive use
- API: A FastAPI-based API server for programmatic access
- Debug: A command-line interface for debugging purposes
"""

import os
import sys
import logging

# Import Pixeletica modules
from src.pixeletica.cli import main as cli_main


def ensure_output_dirs():
    """Ensure that the required output directories exist."""
    os.makedirs("./out/dithered", exist_ok=True)
    os.makedirs("./out/schematics", exist_ok=True)
    os.makedirs("./out/api_tasks", exist_ok=True)


def main():
    """Main entry point for the application."""
    print("==== Pixeletica Minecraft Block Art Generator ====")

    # Ensure output directories exist
    ensure_output_dirs()

    # Add support for --silent command line option
    silent_mode = "--silent" in sys.argv
    if silent_mode:
        # Remove the argument so it doesn't interfere with other code
        sys.argv.remove("--silent")
        # Redirect stdout to null in silent mode
        sys.stdout = open(os.devnull, "w")

    try:
        # Hand off control to the CLI module, which handles mode selection
        cli_main()
    except KeyboardInterrupt:
        print("\nExiting Pixeletica...")
    except Exception as e:
        # Errors are always printed, even in silent mode
        if silent_mode:
            sys.stdout = sys.__stdout__  # Restore stdout
        print(f"An error occurred: {e}")
        print("Exiting Pixeletica...")
        sys.exit(1)


if __name__ == "__main__":
    main()
