"""
Демон проверки доступности сервиса налоговой.

Работает в постоянном цикле и сохраняет статус в bot_settings.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import requests

from config.settings import DEBUG
from src.common.health_check import record_health_status

HEALTHCHECK_URL = (
    "https://kkt-online.nalog.ru/lkip.html?query=/kkt/model/check"
    "&factory_number=00307901234231&model_code=0080"
)
CHECK_INTERVAL_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 10

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _is_healthy(payload: Dict[str, Any]) -> bool:
    """Проверить, соответствует ли ответ здоровому статусу."""
    try:
        status = int(payload.get("status"))
        check_status = int(payload.get("check_status"))
    except (TypeError, ValueError):
        return False
    return status == 1 and check_status == 0


def _check_once() -> None:
    checked_at = int(time.time())
    try:
        response = requests.get(
            HEALTHCHECK_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        healthy = _is_healthy(payload)
        record_health_status(healthy, checked_at)
        logger.info(
            "Tax health check: %s (status=%s, check_status=%s)",
            "healthy" if healthy else "broken",
            payload.get("status"),
            payload.get("check_status"),
        )
    except Exception as exc:  # noqa: BLE001
        record_health_status(False, checked_at)
        logger.exception("Tax health check failed: %s", exc)


def run_loop() -> None:
    """Запуск периодических проверок доступности."""
    logger.info(
        "Starting tax health check daemon (interval=%ss)",
        CHECK_INTERVAL_SECONDS,
    )
    while True:
        _check_once()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_loop()
