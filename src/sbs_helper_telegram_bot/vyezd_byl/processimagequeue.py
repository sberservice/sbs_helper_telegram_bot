"""
processimagequeue.py

Фоновый обработчик задач для бота SPRINT, накладывающего фейковую метку локации.

Постоянно опрашивает таблицу `imagequeue` на ожидающие задачи (status=0)
и обрабатывает загруженные скриншоты:

- Определяет светлый/тёмный режим по пикселю логотипа Яндекс.Карт
- Проверяет, что на карте ещё нет маркера локации
- Размещает случайную фейковую метку около центра экрана
    (с учётом границ UI в тёмном режиме)
- Сохраняет результат и отправляет его пользователю через Telegram

Управляет жизненным циклом задач:
    - Помечает задачи как выполняемые (status=1)
    - Помечает задачи как завершённые (status=2) при успехе или ошибке
    - Очищает зависшие незавершённые задачи при запуске

Использует Pillow для обработки изображений и Telegram Bot API для доставки.
Работает как долгоживущий демон.
"""

import logging
import time
import random
from pathlib import Path

import requests
from requests.exceptions import RequestException
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
    ERR_TELEGRAM_UPLOAD_FAILED,
    ERR_TOO_SMALL,
    ERROR_MESSAGES,
    ERR_UNKNOWN_FORMAT,
)
from src.sbs_helper_telegram_bot.vyezd_byl import messages
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


# статус = 0 задача не начата
# статус = 1 задача в работе
# статус = 2 задача завершена

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],  # консоль
)
logger = logging.getLogger(__name__)


TELEGRAM_HTTP_MAX_RETRIES = 3
TELEGRAM_HTTP_RETRY_BACKOFF_SECONDS = 2
TELEGRAM_SEND_MSG_TIMEOUT_SECONDS = (5, 20)
TELEGRAM_SEND_DOC_TIMEOUT_SECONDS = (10, 120)


def post_with_retries(
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    timeout: int | float | tuple[int | float, int | float] = 20,
    max_retries: int = TELEGRAM_HTTP_MAX_RETRIES,
) -> requests.Response:
    """
    Выполняет POST-запрос к Telegram API с повторами при временных сетевых ошибках.

    Args:
        url: URL Telegram Bot API.
        params: query-параметры запроса.
        data: form-data поля запроса.
        files: файловые поля запроса.
        timeout: таймаут `requests` (одно значение или кортеж connect/read).
        max_retries: максимальное количество попыток отправки.

    Returns:
        Успешный HTTP-ответ.

    Raises:
        RequestException: если все попытки исчерпаны.
    """
    last_exception: RequestException | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return requests.post(
                url,
                params=params,
                data=data,
                files=files,
                timeout=timeout,
            )
        except RequestException as exc:
            last_exception = exc
            if attempt == max_retries:
                break

            sleep_seconds = TELEGRAM_HTTP_RETRY_BACKOFF_SECONDS ** (attempt - 1)
            logger.warning(
                "Ошибка сети при запросе к Telegram API (попытка %s/%s): %s. Повтор через %s c.",
                attempt,
                max_retries,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    assert last_exception is not None
    raise last_exception


def send_msg(user_id, text) -> None:
    """
    Отправляет текстовое сообщение пользователю Telegram через Bot API.

    Args:
        user_id: ID чата Telegram получателя.
        text: текст сообщения для отправки.

    Логирует JSON-ответ API для отладки.
    """
    url_req = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        results = post_with_retries(
            url_req,
            params={"chat_id": user_id, "text": text},
            timeout=TELEGRAM_SEND_MSG_TIMEOUT_SECONDS,
        )
        logger.info(results.json())
    except RequestException as exc:
        logger.error("Не удалось отправить сообщение пользователю %s: %s", user_id, exc)


def is_color_close(
    pixel_color: tuple[int, int, int],
    target_color: tuple[int, int, int],
    tolerance: int = ALLOWED_COLOR_INTENSITY_DEVIATION,
) -> bool:
    """
    Проверяет, что два RGB-цвета находятся в пределах заданной допустимой разницы.

    Args:
        pixel_color: наблюдаемый RGB-цвет из изображения.
        target_color: ожидаемый эталонный RGB-цвет.
        tolerance: максимально допустимое отклонение по каналу (по умолчанию из конфига).

    Returns:
        True, если цвета достаточно близки по всем трём каналам, иначе False.
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
        Обрабатывает загруженный скриншот карты и накладывает фейковую метку локации.

        Шаги обработки:
        - Загружает исходное изображение ({user_id}.jpg)
        - Определяет светлый/тёмный режим по цвету логотипа Яндекс.Карт
        - Отклоняет изображения, где уже есть маркер локации
        - Считает безопасную зону размещения (центр, с учётом UI в тёмном режиме)
        - Случайно размещает нужную иконку локации (светлую или тёмную)
        - Сохраняет результат как `file_name` в IMAGES_DIR
        - Отправляет обработанное изображение пользователю через Telegram

        Args:
            user_id: ID пользователя Telegram (для поиска исходного изображения).
            file_name: желаемое имя выходного файла.

        Returns:
            Кортеж (success: bool, error_code: int | None).
            При успехе: (True, None)
            При ошибке: (False, error_code) из constants.errorcodes
    """

    dark_mode = False
    good_pixel_found = False

    # Загружаем файл с именем вида user_id.jpg из папки images
    # как фоновое изображение
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

                # Работает только если lowest ещё не менялся
                # тогда можно безопасно прервать поиск
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
                # Проверяем, нашли ли светлую иконку локации на карте
                if is_color_close(pixel, LIGHT_LOCATION_ICON_COLOR):
                    logger.info("Found light location circle in the image")
                    return False, ERR_ALREADY_HAS_CIRCLE

                # Проверяем, нашли ли светлый треугольник
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
    caption = messages.MESSAGE_PROCESSING_DONE

    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    try:
        with open(local_image_path, "rb") as photo_file:
            files = {"document": photo_file, "file_name": file_name, "filename": file_name}
            data = {
                #            "file_name": file_name,
                "chat_id": chat_id,
                "caption": caption,
                "filename": file_name,
            }
            response = post_with_retries(
                api_url,
                files=files,
                data=data,
                timeout=TELEGRAM_SEND_DOC_TIMEOUT_SECONDS,
            )
    except RequestException as exc:
        logger.error("Не удалось отправить изображение %s пользователю %s: %s", file_name, user_id, exc)
        return False, ERR_TELEGRAM_UPLOAD_FAILED

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
        Помечает задачу в imagequeue как завершённую.

        Обновляет статус указанной задачи на 2 (выполнено).

        Args:
            job_id: ID задачи в БД, которую нужно пометить как завершённую.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "update imagequeue set status=2 WHERE id=%s"
            val = (job_id,)
            cursor.execute(sql_query, val)


def get_next_pending_job_id() -> dict | None:
    """
        Получает самую старую ожидающую задачу (status=0) из очереди
        и атомарно помечает её как выполняемую (status=1).

        Использует SELECT ... FOR UPDATE с SKIP LOCKED, чтобы избежать гонок
        при работе нескольких воркеров одновременно.

        Returns:
            dict с ключами 'user_id', 'file_name', 'job_id', если задача есть,
            иначе None.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Атомарно выбираем и обновляем следующую ожидающую задачу
            # FOR UPDATE блокирует строку, SKIP LOCKED не ждёт заблокированные строки
            sql_query = """
                SELECT userid, file_name, id 
                FROM imagequeue 
                WHERE status=0 
                ORDER BY timestamp ASC 
                LIMIT 1 
                FOR UPDATE SKIP LOCKED
            """
            cursor.execute(sql_query)
            result = cursor.fetchone()
            
            if result:
                job_id = result["id"]
                user_id = result["userid"]
                file_name = result["file_name"]
                
                # Атомарно помечаем как выполняемую в той же транзакции
                update_query = "UPDATE imagequeue SET status=1 WHERE id=%s"
                cursor.execute(update_query, (job_id,))
                
                job = {"user_id": user_id, "file_name": file_name, "job_id": job_id}
                return job
            else:
                return None


def main() -> None:
    """
        Главный цикл демона обработки изображений.

        При старте: помечает все незавершённые задачи как завершённые (очистка зависших).
        Далее в цикле:
            - Берёт самую старую ожидающую задачу (status=0) и атомарно помечает её как выполняемую
            - Обрабатывает изображение через generate_image()
            - Отправляет пользователю сообщение об ошибке при неуспехе
            - Помечает задачу как завершённую (status=2)
            - Спит 1 секунду, если очередь пуста

        Работает непрерывно как фоновый воркер.
    """
    mark_all_unfinished_jobs_as_completed()

    while True:
        job = get_next_pending_job_id()
        if job:
            # Задача уже помечена как выполняемая в get_next_pending_job_id
            success, error_code = generate_image(job["user_id"], job["file_name"])
            if not success:
                send_msg(job["user_id"], ERROR_MESSAGES[error_code])
            mark_job_as_finished(job["job_id"])
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
