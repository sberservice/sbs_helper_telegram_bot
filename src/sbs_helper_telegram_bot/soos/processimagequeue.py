"""
Фоновый обработчик очереди СООС.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests
from requests.exceptions import RequestException

import src.common.database as database
from src.common.constants.os import IMAGES_DIR
from src.common.constants.telegram import TELEGRAM_TOKEN
from config.settings import (
    DEBUG,
    TELEGRAM_HTTP_MAX_RETRIES,
    TELEGRAM_HTTP_RETRY_BACKOFF_SECONDS,
    TELEGRAM_SEND_DOC_CONNECT_TIMEOUT_SECONDS,
    TELEGRAM_SEND_DOC_READ_TIMEOUT_SECONDS,
    TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS,
    TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS,
)

from . import messages, settings, soos_parser, soos_template, soos_renderer

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

TELEGRAM_SEND_MSG_TIMEOUT_SECONDS = (
    TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS,
    TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS,
)
TELEGRAM_SEND_PHOTO_TIMEOUT_SECONDS = (
    TELEGRAM_SEND_DOC_CONNECT_TIMEOUT_SECONDS,
    TELEGRAM_SEND_DOC_READ_TIMEOUT_SECONDS,
)


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
    Выполнить POST-запрос с повторами при временных сетевых ошибках.

    Args:
        url: URL Telegram API.
        params: Query-параметры.
        data: Form-data параметры.
        files: Файлы для multipart.
        timeout: Таймаут запроса.
        max_retries: Максимальное число попыток.

    Returns:
        HTTP-ответ.

    Raises:
        RequestException: Если все попытки исчерпаны.
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
                "Ошибка сети при запросе к Telegram API (попытка %s/%s): %s. Повтор через %s сек.",
                attempt,
                max_retries,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    assert last_exception is not None
    raise last_exception


def send_msg(user_id: int, text: str) -> None:
    """
    Отправить текстовое сообщение пользователю.

    Args:
        user_id: Telegram chat_id.
        text: Текст сообщения.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        post_with_retries(
            url,
            params={"chat_id": user_id, "text": text},
            timeout=TELEGRAM_SEND_MSG_TIMEOUT_SECONDS,
        )
    except RequestException as exc:
        logger.error("Не удалось отправить сообщение пользователю %s: %s", user_id, exc)


def send_photo(user_id: int, image_path: Path, caption: str | None = None) -> bool:
    """
    Отправить изображение пользователю как photo.

    Args:
        user_id: Telegram chat_id.
        image_path: Путь к файлу изображения.
        caption: Подпись к изображению.

    Returns:
        True при успехе, иначе False.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as image_file:
            data: dict[str, str | int] = {"chat_id": user_id}
            if caption:
                data["caption"] = caption
            response = post_with_retries(
                url,
                data=data,
                files={"photo": image_file},
                timeout=TELEGRAM_SEND_PHOTO_TIMEOUT_SECONDS,
            )
        payload = response.json()
        if not payload.get("ok"):
            logger.error("sendPhoto вернул ошибку: %s", payload)
            return False
        return True
    except RequestException as exc:
        logger.error("Не удалось отправить фото пользователю %s: %s", user_id, exc)
        return False
    except Exception as exc:
        logger.error("Не удалось отправить фото пользователю %s: %s", user_id, exc)
        return False


def mark_all_unfinished_jobs_as_completed() -> None:
    """
    Пометить все незавершённые задачи как завершённые при старте воркера.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(f"UPDATE {settings.SOOS_QUEUE_TABLE} SET status = 2 WHERE status <> 2")


def mark_job_as_finished(job_id: int, error_message: str | None = None) -> None:
    """
    Пометить задачу как завершённую.

    Args:
        job_id: ID задачи.
        error_message: Текст ошибки, если была.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                f"UPDATE {settings.SOOS_QUEUE_TABLE} SET status = 2, error_message = %s WHERE id = %s",
                (error_message, job_id),
            )


def get_next_pending_job() -> dict | None:
    """
    Атомарно взять следующую задачу и перевести в статус «в работе».

    Returns:
        Словарь задачи или None.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                f"""
                SELECT id, userid, file_name, ticket_text
                FROM {settings.SOOS_QUEUE_TABLE}
                WHERE status = 0
                ORDER BY timestamp ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                f"UPDATE {settings.SOOS_QUEUE_TABLE} SET status = 1 WHERE id = %s",
                (row["id"],),
            )
            return {
                "job_id": row["id"],
                "user_id": row["userid"],
                "file_name": row["file_name"],
                "ticket_text": row["ticket_text"],
            }


def generate_soos_images(
    ticket_text: str,
    payment_output_path: Path,
    cancel_output_path: Path,
    sverka_output_path: Path,
) -> tuple[bool, str | None]:
    """
    Сформировать PNG-изображение СООС на основании текста тикета.

    Args:
        ticket_text: Исходный текст тикета.
        payment_output_path: Путь для сохранения первого шаблона (чек оплаты).
        cancel_output_path: Путь для сохранения второго шаблона (чек отмены).
        sverka_output_path: Путь для сохранения третьего шаблона (сверка итогов).

    Returns:
        Кортеж (успех, ошибка).
    """
    fields = soos_parser.extract_ticket_fields(ticket_text)
    missing_fields = soos_parser.get_missing_required_fields(fields)
    if missing_fields:
        missing_text = ", ".join(missing_fields)
        return False, f"Отсутствуют обязательные поля: {missing_text}"

    payment_receipt_text = soos_template.build_soos_payment_receipt_text(fields)
    payment_image_bytes = soos_renderer.render_terminal_receipt_image(payment_receipt_text, image_format="PNG")
    payment_output_path.write_bytes(payment_image_bytes)

    cancel_receipt_text = soos_template.build_soos_cancel_receipt_text(fields)
    cancel_image_bytes = soos_renderer.render_terminal_receipt_image(cancel_receipt_text, image_format="PNG")
    cancel_output_path.write_bytes(cancel_image_bytes)

    sverka_receipt_text = soos_template.build_soos_receipt_text(fields)
    sverka_image_bytes = soos_renderer.render_terminal_receipt_image(sverka_receipt_text, image_format="PNG")
    sverka_output_path.write_bytes(sverka_image_bytes)

    return True, None


def main() -> None:
    """
    Главный цикл воркера очереди СООС.
    """
    mark_all_unfinished_jobs_as_completed()

    while True:
        job = get_next_pending_job()
        if not job:
            time.sleep(1)
            continue

        base_output_path = IMAGES_DIR / job["file_name"]
        payment_output_path = base_output_path.with_name(f"pay_{base_output_path.name}")
        cancel_output_path = base_output_path.with_name(f"cancel_{base_output_path.name}")
        sverka_output_path = base_output_path.with_name(f"sverka_{base_output_path.name}")
        try:
            success, error_message = generate_soos_images(
                job["ticket_text"],
                payment_output_path,
                cancel_output_path,
                sverka_output_path,
            )
            if not success:
                send_msg(job["user_id"], messages.MESSAGE_PROCESSING_FAILED)
                mark_job_as_finished(job["job_id"], error_message)
                continue

            payment_sent = send_photo(job["user_id"], payment_output_path)
            if not payment_sent:
                mark_job_as_finished(job["job_id"], "Ошибка отправки первого изображения в Telegram")
                continue

            cancel_sent = send_photo(job["user_id"], cancel_output_path)
            if not cancel_sent:
                mark_job_as_finished(job["job_id"], "Ошибка отправки второго изображения в Telegram")
                continue

            sverka_sent = send_photo(job["user_id"], sverka_output_path, messages.MESSAGE_PROCESSING_DONE)
            if not sverka_sent:
                mark_job_as_finished(job["job_id"], "Ошибка отправки третьего изображения в Telegram")
                continue

            mark_job_as_finished(job["job_id"], None)
        except Exception as exc:
            logger.exception("Ошибка обработки задачи СООС id=%s: %s", job["job_id"], exc)
            send_msg(job["user_id"], messages.MESSAGE_PROCESSING_FAILED)
            mark_job_as_finished(job["job_id"], str(exc))
        finally:
            payment_output_path.unlink(missing_ok=True)
            cancel_output_path.unlink(missing_ok=True)
            sverka_output_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
