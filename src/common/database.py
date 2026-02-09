import mysql.connector
from contextlib import contextmanager
from typing import Generator
from src.common.constants.database import MYSQL_DATABASE,MYSQL_HOST,MYSQL_PASSWORD,MYSQL_PORT,MYSQL_USER

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
    Автоматически выполняет connect/commit/rollback/close.
    """
    conn = None
    try:
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
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield cursor
    finally:
        cursor.close()