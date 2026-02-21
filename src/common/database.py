import logging
import mysql.connector
import mysql.connector.pooling
from contextlib import contextmanager
from typing import Generator, Optional
from src.common.constants.database import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Пул соединений MySQL
# ─────────────────────────────────────────────────────────────
# Размер пула можно переопределить через переменную окружения DB_POOL_SIZE.
# По умолчанию 5 соединений — достаточно для основного бота и воркера очереди.

import os
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

_connection_pool: Optional[mysql.connector.pooling.MySQLConnectionPool] = None


def _get_pool() -> mysql.connector.pooling.MySQLConnectionPool:
    """
    Получить (или создать) глобальный пул соединений MySQL.

    Пул создаётся лениво при первом вызове. Это позволяет подхватить
    параметры из окружения, даже если модуль был импортирован до их загрузки.

    Returns:
        Пул соединений MySQLConnectionPool.
    """
    global _connection_pool
    if _connection_pool is None:
        logger.info(
            "Инициализация пула MySQL-соединений: pool_size=%d, host=%s, database=%s",
            _POOL_SIZE, MYSQL_HOST, MYSQL_DATABASE,
        )
        _connection_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="bot_pool",
            pool_size=_POOL_SIZE,
            pool_reset_session=True,
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            port=MYSQL_PORT,
        )
    return _connection_pool


def reset_pool() -> None:
    """
    Сбросить глобальный пул (для тестов и повторной инициализации).
    """
    global _connection_pool
    _connection_pool = None


@contextmanager
def get_db_connection(
    host: str = MYSQL_HOST,
    user: str = MYSQL_USER,
    password: str = MYSQL_PASSWORD,
    database: str = MYSQL_DATABASE,
    port: int = MYSQL_PORT,
    **kwargs
) -> Generator[mysql.connector.MySQLConnection, None, None]:
    """
    Контекстный менеджер для подключения к MySQL.

    Если вызывается с параметрами по умолчанию — берёт соединение из пула.
    Если переданы нестандартные параметры — создаёт одноразовое соединение
    (обратная совместимость для тестов и миграций).

    Автоматически выполняет commit/rollback/close (или возврат в пул).
    """
    # Определяем, можно ли использовать пул (параметры совпадают с дефолтными)
    use_pool = (
        host == MYSQL_HOST
        and user == MYSQL_USER
        and password == MYSQL_PASSWORD
        and database == MYSQL_DATABASE
        and port == MYSQL_PORT
        and not kwargs
    )

    conn = None
    try:
        if use_pool:
            conn = _get_pool().get_connection()
        else:
            conn = mysql.connector.connect(
                host=host,
                user=user,
                password=password,
                database=database,
                port=port,
                **kwargs
            )
        yield conn
        conn.commit()  # фиксируем транзакцию, если нет исключения
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


@contextmanager
def get_cursor(conn, dictionary=True):
    """Контекстный менеджер для курсора MySQL."""
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield cursor
    finally:
        cursor.close()