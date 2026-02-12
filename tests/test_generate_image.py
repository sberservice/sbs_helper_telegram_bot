"""
    test_generate_image.py

    Pytest suite for the image processing logic in processimagequeue.generate_image.

    Tests:
    - Detection of existing location markers (light/dark circle & triangle)
    - Rejection of too-small images
    - Detection of missing Yandex Maps logo trigger pixel
    - Unknown file format handling
    - Full processing cycle in both light and dark modes
"""
import shutil

import pytest
import requests

from PIL import Image
import src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue as processimagequeue
from src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue import generate_image
from src.common.constants.os import TEST_SAMPLES_DIR,IMAGES_DIR
from src.common.constants.errorcodes import ERR_ALREADY_HAS_CIRCLE,ERR_ALREADY_HAS_DARK_CIRCLE,ERR_ALREADY_HAS_DARK_TRIANGLE,ERR_ALREADY_HAS_TRIANGLE,ERR_TELEGRAM_UPLOAD_FAILED,ERR_TOO_SMALL,ERR_NO_TRIGGER_PIXEL,ERR_UNKNOWN_FORMAT


@pytest.fixture
def cleanup():
    yield
    # remove generated files
    for p in IMAGES_DIR.glob("test_*.jpg"):
        p.unlink(missing_ok=True)

def test_detect_dark_circle(cleanup):
    img = Image.open(TEST_SAMPLES_DIR / "dark_circle_present.jpg")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_dark_circle_present.jpg") 
    assert success is False
    assert error_code == ERR_ALREADY_HAS_DARK_CIRCLE

def test_detect_light_circle(cleanup):
    img = Image.open(TEST_SAMPLES_DIR / "light_circle_present.jpg")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_light_circle_present.jpg")
    assert success is False
    assert error_code == ERR_ALREADY_HAS_CIRCLE

def test_detect_light_triangle(cleanup):
    img = Image.open(TEST_SAMPLES_DIR / "light_triangle_present.jpg")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_light_triangle_present.jpg")
    assert success is False
    assert error_code == ERR_ALREADY_HAS_TRIANGLE

def test_detect_dark_triangle(cleanup):
    img = Image.open(TEST_SAMPLES_DIR / "dark_triangle_present.jpg")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_dark_triangle_present.jpg")
    assert success is False
    assert error_code == ERR_ALREADY_HAS_DARK_TRIANGLE


def test_reject_small_image(cleanup):
    img = Image.new("RGB", (50, 50), "black")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_dark_circle_present.jpg")
    assert success is False
    assert error_code == ERR_TOO_SMALL

def test_no_triggering_pixel(cleanup):
    img = Image.open(TEST_SAMPLES_DIR / "no_triggering_pixel_present.jpg")
    img.save(IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_no_triggering_pixel_present.jpg")
    assert success is False
    assert error_code == ERR_NO_TRIGGER_PIXEL

def test_unknown_format(cleanup):
    shutil.copy2(TEST_SAMPLES_DIR / "unknown_format.jpg",IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_unknown_format.png")
    assert success is False
    assert error_code == ERR_UNKNOWN_FORMAT

LIGHT_MODE_SAMPLES = TEST_SAMPLES_DIR / "light_mode"

@pytest.mark.parametrize(
    "sample_filename",
    [p.name for p in LIGHT_MODE_SAMPLES.iterdir() if p.is_file() and p.suffix.lower() in {".jpg"}],
    ids=lambda x: x,   # nice test names in output
)
def test_complete_cycle_light_mode(sample_filename,cleanup):
    
    shutil.copy2(LIGHT_MODE_SAMPLES / sample_filename,IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_light_mode_screen.jpg")
    assert success is True
    success, error_code = generate_image("test_light_mode_screen", "test_deleteme.jpg")
    assert success is False
    assert error_code == ERR_ALREADY_HAS_CIRCLE




def test_complete_cycle_dark_mode(cleanup):
    shutil.copy2(TEST_SAMPLES_DIR / "dark_mode_screen.jpg",IMAGES_DIR / "test_999.jpg")
    success, error_code = generate_image("test_999", "test_dark_mode_screen.jpg")
    assert success is True
    success, error_code = generate_image("test_dark_mode_screen", "test_deleteme.jpg")
    assert success is False
    assert error_code == ERR_ALREADY_HAS_DARK_CIRCLE


def test_upload_timeout_returns_network_error(cleanup, monkeypatch):
    shutil.copy2(TEST_SAMPLES_DIR / "dark_mode_screen.jpg", IMAGES_DIR / "test_999.jpg")

    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network timeout")

    monkeypatch.setattr(processimagequeue, "post_with_retries", raise_timeout)

    success, error_code = generate_image("test_999", "test_network_timeout.jpg")
    assert success is False
    assert error_code == ERR_TELEGRAM_UPLOAD_FAILED
