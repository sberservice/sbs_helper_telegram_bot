"""
processimagequeue.py

Background job processor for the SPRINT app fake-location overlay bot.

Continuously polls the `imagequeue` table for pending jobs (status=0),
processes each uploaded screenshot by:

- Detecting light/dark mode via Yandex Maps logo pixel
- Verifying the map does not already contain a location marker
- Placing a random fake location icon near the screen center
  (adjusted for dark-mode UI borders)
- Saving the result and sending it back to the user via Telegram

Manages job lifecycle:
  - Marks jobs as in-progress (status=1)
  - Marks jobs as finished (status=2) on completion or error
  - Clears stale unfinished jobs on startup

Uses Pillow for image manipulation and Telegram Bot API for delivery.
Runs as a long-living daemon process.
"""

import logging
import time
import random
from pathlib import Path

import requests
from PIL import Image
import src.common.database as database

from src.common.constants.telegram import TELEGRAM_TOKEN
from src.common.constants.os import IMAGES_DIR, ASSETS_DIR
from src.common.constants.errorcodes import (
    ERR_ALREADY_HAS_CIRCLE,
    ERR_ALREADY_HAS_DARK_CIRCLE,
    ERR_ALREADY_HAS_DARK_TRIANGLE,
    ERR_ALREADY_HAS_TRIANGLE,
    ERR_FILE_NOT_FOUND,
    ERR_NO_TRIGGER_PIXEL,
    ERR_TOO_SMALL,
    ERROR_MESSAGES,
    ERR_UNKNOWN_FORMAT,
)
from config.settings import (
    MIN_UPLOADED_IMAGE_HEIGHT,
    MIN_UPLOADED_IMAGE_WIDTH,
    DEBUG,
    FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE,
    ALLOWED_COLOR_INTENSITY_DEVIATION,
    DARK_PIXEL_COLOR,
    LIGHT_PIXEL_COLOR,
    DARK_LOCATION_ICON_COLOR,
    DARK_TRIANGLE_ICON_COLOR,
    LIGHT_LOCATION_ICON_COLOR,
    LIGHT_TRIANGLE_ICON_COLOR,
    FRAME_BORDER_COLOR,
    TASKS_BORDER_COLOR,
    MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL,
    MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL,
    COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR,
    COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR,
)


# status = 0 job is not started
# status = 1 job started
# status = 2 job finished

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],  # console
)
logger = logging.getLogger(__name__)


def send_msg(user_id, text) -> None:
    """
    Sends a text message to a Telegram user via the Bot API.

    Args:
        user_id: Telegram chat ID of the recipient.
        text: Message text to send.

    Logs the API response JSON for debugging.
    """
    url_req = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    results = requests.post(url_req, params={"chat_id": user_id, "text": text},timeout=5)
    logger.info(results.json())


def is_color_close(
    pixel_color: tuple[int, int, int],
    target_color: tuple[int, int, int],
    tolerance: int = ALLOWED_COLOR_INTENSITY_DEVIATION,
) -> bool:
    """
    Checks if two RGB colors are within a given tolerance of each other.

    Args:
        pixel_color: Observed RGB color from the image.
        target_color: Expected reference RGB color.
        tolerance: Maximum allowed difference per channel (default from config).

    Returns:
        True if the colors are close enough in all three channels, False otherwise.
    """
    r, g, b = pixel_color
    rt, gt, bt = target_color

    return (
        abs(r - rt) <= tolerance
        and abs(g - gt) <= tolerance
        and abs(b - bt) <= tolerance
    )


def generate_image(user_id, file_name) -> bool:
    """
        Processes a user's uploaded map screenshot and overlays a fake location marker.

        Performs the following steps:
        - Loads the source image ({user_id}.jpg)
        - Detects light/dark mode by checking Yandex Maps logo color
        - Rejects images that already contain a location marker
        - Calculates safe placement zone (centered, avoids UI elements in dark mode)
        - Randomly places the appropriate location icon (light or dark variant)
        - Saves the result as `file_name` in IMAGES_DIR
        - Sends the processed image back to the user via Telegram

        Args:
            user_id: Telegram user ID (used to locate original image).
            file_name: Desired output filename for the processed image.

        Returns:
            Tuple of (success: bool, error_code: int | None).
            On success: (True, None)
            On failure: (False, error_code) from constants.errorcodes
    """

    dark_mode = False
    good_pixel_found = False

    # let's load the file that has name like user_id+jpg in the images folder
    # as a background_image
    try:
        if not Path(IMAGES_DIR / f"{user_id}.jpg").exists():
            logger.critical(f"Can't open the file: {IMAGES_DIR / f'{user_id}.jpg'}")
            return False, ERR_FILE_NOT_FOUND

        background_image = Image.open(IMAGES_DIR / f"{user_id}.jpg")
    except Exception as e:
        logger.warning(str(e))
        return False, ERR_UNKNOWN_FORMAT

    if background_image.mode != "RGB":
        background_image = background_image.convert("RGB")

    width, height = background_image.size
    if width < MIN_UPLOADED_IMAGE_WIDTH or height < MIN_UPLOADED_IMAGE_HEIGHT:
        logger.warning("We've got the file with dimensions too small")
        return False, ERR_TOO_SMALL

    logger.info(
        "Starting checking for color to determine if we are in the dark mode or light mode"
    )

    for y in range(
        MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL,
        min(MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL, height),
    ):
        if good_pixel_found:
            logger.info("since we found the good pixel, break")
            break
        for x in range(width):
            pixel = background_image.getpixel((x, y))
            if is_color_close(pixel, DARK_PIXEL_COLOR):
                logger.info(
                    "Found the dark pixel in Yandex maps logo, enabling dark mode"
                )
                dark_mode = True
                good_pixel_found = True
                break

            if is_color_close(pixel, LIGHT_PIXEL_COLOR):
                logger.info(
                    "Found the light pixel in Yandex maps logo, enabling light mode"
                )
                good_pixel_found = True
                break

    if dark_mode:
        highest = 0
        lowest = height
        escape = False
        for y in range(height):
            if escape:
                break
            for x in range(width):
                pixel = background_image.getpixel((x, y))

                # анализ темных границ нам нужно найти верхний и нижний пиксель
                if x == COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR and is_color_close(
                    pixel, FRAME_BORDER_COLOR
                ):
                    highest = y

                # it only works if lowest value was untouched before
                # then we can safely escape
                if (
                    x == COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR
                    and lowest == height
                    and is_color_close(pixel, TASKS_BORDER_COLOR)
                ):
                    lowest = y
                    escape = True
                    break

                if is_color_close(pixel, DARK_LOCATION_ICON_COLOR):
                    logger.info("Found dark location circle in the image")
                    return False, ERR_ALREADY_HAS_DARK_CIRCLE

                if is_color_close(pixel, DARK_TRIANGLE_ICON_COLOR):
                    logger.info("Found dark triangle in the image")
                    return False, ERR_ALREADY_HAS_DARK_TRIANGLE

    if not dark_mode:
        escape = False
        for y in range(height):
            for x in range(width):
                pixel = background_image.getpixel((x, y))
                # check if we found light location icon on the make
                if is_color_close(pixel, LIGHT_LOCATION_ICON_COLOR):
                    logger.info("Found light location circle in the image")
                    return False, ERR_ALREADY_HAS_CIRCLE

                # Check if we found the light triangle
                if is_color_close(pixel, LIGHT_TRIANGLE_ICON_COLOR):
                    return False, ERR_ALREADY_HAS_TRIANGLE

    if not good_pixel_found:
        return False, ERR_NO_TRIGGER_PIXEL

    if not dark_mode:
        logger.info("LIGHTMODE ON")
        overlay_image = Image.open(ASSETS_DIR / "location.png")
        location_icon_width, location_icon_height = overlay_image.size

    else:
        logger.info("DARKMODE ON")
        overlay_image = Image.open(ASSETS_DIR / "location_dark14.png")
        location_icon_width, location_icon_height = overlay_image.size

    if overlay_image.mode != "RGBA":
        overlay_image = overlay_image.convert("RGBA")

    if not dark_mode:
        deviation = FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE
        low_boundx = round(width / 2 - width * deviation)
        low_boundy = round(height / 2 - height * deviation)
        high_boundx = round(width / 2 + width * deviation)
        high_boundy = round(height / 2 + height * deviation)

        x = random.randint(low_boundx, high_boundx) - round(location_icon_width / 2)
        y = random.randint(low_boundy, high_boundy) - round(location_icon_height / 2)
    else:
        logger.info("Highest: %s", str(highest))
        logger.info("Lowest: %s", str(lowest))
        deviation = FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE
        low_boundx = round(width / 2 - width * deviation)
        low_boundy = round(
            highest + (lowest - highest) / 2 - (lowest - highest) * deviation
        )
        logger.info("low_boundy: %s", str(low_boundy))

        high_boundx = round(width / 2 + width * deviation)
        high_boundy = round(
            highest + (lowest - highest) / 2 + (lowest - highest) * deviation
        )
        logger.info("high_boundy: %s", str(high_boundy))

        x = random.randint(low_boundx, high_boundx) - round(location_icon_width / 2)
        y = random.randint(low_boundy, high_boundy) - round(location_icon_height / 2)

        logger.info("Y: %s", str(y))

    background_image.paste(overlay_image, (x, y), overlay_image)

    background_image.save(IMAGES_DIR / file_name)

    chat_id = user_id
    local_image_path = IMAGES_DIR / file_name
    caption = "Готово!"

    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    with open(local_image_path, "rb") as photo_file:
        files = {"document": photo_file, "file_name": file_name, "filename": file_name}
        data = {
            #            "file_name": file_name,
            "chat_id": chat_id,
            "caption": caption,
            "filename": file_name,
        }
        response = requests.post(api_url, files=files, data=data,timeout=20)
    logger.info(api_url)
    logger.info(file_name)
    logger.info(response.json())

    return True, None


def mark_job_as_in_progress(job_id) -> None:
    """
        Marks a queued image-processing job as started.

        Updates the `status` column to 1 (in progress) for the given job ID.

        Args:
            job_id: Primary key of the job in the `imagequeue` table.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "update imagequeue set status=1 WHERE id=%s"
            val = (job_id,)
            cursor.execute(sql_query, val)


def mark_all_unfinished_jobs_as_completed() -> None:
    """
        Marks every job in the queue as completed (status=2).

        Used on worker startup to clean up jobs left in pending (0) or in-progress (1)
        states from a previous crash or restart, preventing stale tasks from blocking
        the queue.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "update imagequeue set status=2"
            cursor.execute(sql_query)


def mark_job_as_finished(job_id) -> None:
    """
        Marks a job in the imagequeue as finished.

        Updates the status of the specified job to 2 (completed).

        Args:
            job_id: The database ID of the job to mark as finished.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "update imagequeue set status=2 WHERE id=%s"
            val = (job_id,)
            cursor.execute(sql_query, val)


def get_next_pending_job_id() -> dict | None:
    """
        Retrieves the oldest pending job (status=0) from the image processing queue.

        Returns:
            dict with keys 'user_id', 'file_name', and 'job_id' if a pending job exists,
            otherwise None.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT userid, file_name,id FROM imagequeue WHERE status=0 order by timestamp asc limit 1"
            cursor.execute(sql_query)
            result = cursor.fetchone()
            if result:
                user_id = result["userid"]
                file_name = result["file_name"]
                job_id = result["id"]
                job = {"user_id": user_id, "file_name": file_name, "job_id": job_id}
                return job
            else:
                return None


def main() -> None:
    """
    Main daemon loop of the image processing worker.

    On start: marks all unfinished jobs as completed (clears stale entries).
    Then continuously:
      - Fetches the oldest pending job (status=0)
      - Processes the image with generate_image()
      - Sends error message to user if processing fails
      - Marks job as finished (status=2)
      - Sleeps 1 second if queue is empty

    Runs indefinitely as a background worker process.
    """
    mark_all_unfinished_jobs_as_completed()

    while True:
        job = get_next_pending_job_id()
        if job:
            mark_job_as_in_progress(job["job_id"])
            success, error_code = generate_image(job["user_id"], job["file_name"])
            if not success:
                send_msg(job["user_id"], ERROR_MESSAGES[error_code])
            mark_job_as_finished(job["job_id"])
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
