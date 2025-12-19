"""
    Path constants for the project.

    Defines absolute paths relative to the project root
    - ROOT_DIR: Project root directory
    - IMAGES_DIR: Directory for uploaded and processed images
    - ASSETS_DIR: Directory for static assets (location icons, etc.)
    - TEST_DIR: Directory for test files
    - TEST_SAMPLES_DIR: Directory containing sample images for testing
"""

from pathlib import Path
ROOT_DIR = (Path(__file__).parent.parent).resolve()
IMAGES_DIR = (Path(__file__).parent.parent.parent.parent / "images").resolve()
ASSETS_DIR = (Path(__file__).parent.parent.parent.parent / "assets").resolve()
TEST_DIR = (Path(__file__).parent.parent.parent.parent / "tests").resolve()
TEST_SAMPLES_DIR = (Path(__file__).parent.parent.parent.parent / "tests" / "samples").resolve()
