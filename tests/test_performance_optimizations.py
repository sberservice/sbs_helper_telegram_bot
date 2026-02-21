"""
Тесты оптимизаций производительности.

Покрывает:
- Пул соединений MySQL (database.py)
- TTL-кеш настроек (bot_settings.py)
- Пакетная загрузка настроек модулей (bot_settings.py)
- Консолидированная проверка авторизации (telegram_user.py)
- Кеш статуса здоровья (health_check.py)
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from src.common import database
from src.common import bot_settings
from src.common.telegram_user import get_user_auth_status, UserAuthStatus


class TestConnectionPool(unittest.TestCase):
    """Тесты пула соединений MySQL."""

    def setUp(self):
        """Сбрасываем пул перед каждым тестом."""
        database.reset_pool()

    def tearDown(self):
        database.reset_pool()

    @patch("src.common.database._get_pool")
    def test_pool_connection_commit_and_close(self, mock_get_pool):
        """Соединение из пула коммитится и закрывается при успешном завершении."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        with database.get_db_connection() as conn:
            pass

        mock_pool.get_connection.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("src.common.database._get_pool")
    def test_pool_connection_rollback_on_error(self, mock_get_pool):
        """Соединение из пула откатывается при ошибке."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        with self.assertRaises(RuntimeError):
            with database.get_db_connection():
                raise RuntimeError("test error")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("src.common.database.mysql.connector.connect")
    def test_custom_params_bypass_pool(self, mock_connect):
        """Нестандартные параметры подключения не используют пул."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_connect.return_value = mock_conn

        with database.get_db_connection(host="custom_host") as conn:
            self.assertIs(conn, mock_conn)

        mock_connect.assert_called_once()

    def test_reset_pool_clears_global(self):
        """reset_pool() сбрасывает глобальный пул."""
        database._connection_pool = "something"
        database.reset_pool()
        self.assertIsNone(database._connection_pool)


class TestSettingsCache(unittest.TestCase):
    """Тесты TTL-кеша настроек."""

    def setUp(self):
        bot_settings.clear_settings_cache()

    def tearDown(self):
        bot_settings.clear_settings_cache()

    @patch('src.common.bot_settings.database')
    def test_get_setting_caches_result(self, mock_database):
        """Повторный вызов get_setting() берёт значение из кеша, а не из БД."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'setting_value': 'cached_value'}

        # Первый вызов — обращение к БД
        result1 = bot_settings.get_setting('test_key')
        self.assertEqual(result1, 'cached_value')
        self.assertEqual(mock_cursor.execute.call_count, 1)

        # Второй вызов — из кеша, execute не вызывается повторно
        result2 = bot_settings.get_setting('test_key')
        self.assertEqual(result2, 'cached_value')
        self.assertEqual(mock_cursor.execute.call_count, 1)  # Не увеличилось

    @patch('src.common.bot_settings.database')
    def test_get_setting_caches_none(self, mock_database):
        """None-результат (настройка не найдена) тоже кешируется."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result1 = bot_settings.get_setting('missing_key')
        self.assertIsNone(result1)

        result2 = bot_settings.get_setting('missing_key')
        self.assertIsNone(result2)
        self.assertEqual(mock_cursor.execute.call_count, 1)

    @patch('src.common.bot_settings.database')
    def test_set_setting_clears_cache(self, mock_database):
        """set_setting() сбрасывает кеш, чтобы новое значение стало доступным."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'setting_value': 'old'}

        # Кешируем
        bot_settings.get_setting('key1')
        self.assertEqual(mock_cursor.execute.call_count, 1)

        # Обновляем — кеш должен сброситься
        bot_settings.set_setting('key1', 'new', 123)

        # Следующий get_setting должен снова обратиться к БД
        mock_cursor.fetchone.return_value = {'setting_value': 'new'}
        result = bot_settings.get_setting('key1')
        self.assertEqual(result, 'new')
        # execute вызван: 1 (get) + 1 (set) + 1 (get after clear) = 3
        self.assertEqual(mock_cursor.execute.call_count, 3)

    def test_cache_ttl_expiry(self):
        """Кеш истекает после _SETTINGS_CACHE_TTL секунд."""
        # Вручную помещаем в кеш запись с истёкшим TTL
        bot_settings._settings_cache['expired_key'] = ('value', time.monotonic() - 120)

        result = bot_settings._cache_get('expired_key')
        self.assertIs(result, bot_settings._CACHE_MISS)

    def test_clear_settings_cache(self):
        """clear_settings_cache() полностью очищает кеш."""
        bot_settings._cache_put('key1', 'val1')
        bot_settings._cache_put('key2', 'val2')

        bot_settings.clear_settings_cache()

        self.assertEqual(len(bot_settings._settings_cache), 0)


class TestBatchModuleSettings(unittest.TestCase):
    """Тесты пакетной загрузки настроек модулей."""

    def setUp(self):
        bot_settings.clear_settings_cache()

    def tearDown(self):
        bot_settings.clear_settings_cache()

    @patch('src.common.bot_settings.database')
    def test_get_all_module_states_one_query(self, mock_database):
        """get_all_module_states() делает один запрос к БД вместо N."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        # Возвращаем все настройки модулей за один запрос
        mock_cursor.fetchall.return_value = [
            {'setting_key': 'module_certification_enabled', 'setting_value': '1'},
            {'setting_key': 'module_screenshot_enabled', 'setting_value': '0'},
        ]

        states = bot_settings.get_all_module_states()

        # Один вызов execute (один запрос), а не 8 отдельных
        self.assertEqual(mock_cursor.execute.call_count, 1)

        # Проверяем что модули с настройками распарсены корректно
        self.assertTrue(states['certification'])
        self.assertFalse(states['screenshot'])
        # Модули без настройки в БД считаются включёнными
        self.assertTrue(states['upos_errors'])

    @patch('src.common.bot_settings.database')
    def test_get_modules_config_uses_batch(self, mock_database):
        """get_modules_config() загружает настройки пакетно и кеширует."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {'setting_key': 'module_certification_enabled', 'setting_value': '1'},
        ]

        modules = bot_settings.get_modules_config(enabled_only=True)

        # Все модули включены (кроме тех, кто явно '0')
        self.assertTrue(len(modules) > 0)
        # Один запрос к БД
        self.assertEqual(mock_cursor.execute.call_count, 1)

        # Повторный вызов использует кеш — execute не увеличивается
        modules2 = bot_settings.get_modules_config(enabled_only=True)
        self.assertEqual(mock_cursor.execute.call_count, 1)


class TestConsolidatedAuth(unittest.TestCase):
    """Тесты консолидированной проверки авторизации."""

    @patch('src.common.bot_settings.get_setting')
    @patch('src.common.telegram_user.database')
    def test_pre_invited_user_is_legit(self, mock_database, mock_get_setting):
        """Пред-добавленный пользователь считается легитимным."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        # chat_members: есть, активирован
        # manual_users: нет
        # invites: нет
        # users: не админ
        mock_cursor.fetchone.side_effect = [
            {'telegram_id': 123, 'activated_timestamp': 1000},  # chat_members
            {'count': 0},  # manual_users
            {'invite_consumed': 0},  # invites
            None,  # users (не найден)
        ]
        mock_get_setting.return_value = '1'

        auth = get_user_auth_status(123)

        self.assertTrue(auth.is_pre_invited)
        self.assertTrue(auth.is_pre_invited_activated)
        self.assertTrue(auth.is_legit)
        self.assertFalse(auth.is_invite_blocked)
        self.assertFalse(auth.is_admin)

    @patch('src.common.bot_settings.get_setting')
    @patch('src.common.telegram_user.database')
    def test_invite_user_blocked_when_system_disabled(self, mock_database, mock_get_setting):
        """Инвайт-пользователь блокируется при выключенной инвайт-системе."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            None,  # chat_members: нет
            {'count': 0},  # manual_users: нет
            {'invite_consumed': 1},  # invites: есть
            None,  # users: нет
        ]
        mock_get_setting.return_value = '0'  # Инвайт-система выключена

        auth = get_user_auth_status(456)

        self.assertFalse(auth.is_legit)
        self.assertTrue(auth.is_invite_blocked)

    @patch('src.common.bot_settings.get_setting')
    @patch('src.common.telegram_user.database')
    def test_admin_flag_detected(self, mock_database, mock_get_setting):
        """Флаг is_admin корректно определяется."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {'telegram_id': 789, 'activated_timestamp': 1000},  # chat_members
            {'count': 0},  # manual_users
            {'invite_consumed': 0},  # invites
            {'is_admin': 1},  # users — админ
        ]
        mock_get_setting.return_value = '1'

        auth = get_user_auth_status(789)

        self.assertTrue(auth.is_admin)
        self.assertTrue(auth.is_legit)

    @patch('src.common.bot_settings.get_setting')
    @patch('src.common.telegram_user.database')
    def test_single_db_connection_used(self, mock_database, mock_get_setting):
        """Все проверки выполняются через одно подключение к БД."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            None,  # chat_members
            {'count': 0},  # manual_users
            {'invite_consumed': 0},  # invites
            None,  # users
        ]
        mock_get_setting.return_value = '1'

        get_user_auth_status(100)

        # Одно подключение к БД
        mock_database.get_db_connection.assert_called_once()
        # 4 запроса через один курсор
        self.assertEqual(mock_cursor.execute.call_count, 4)

    @patch('src.common.bot_settings.get_setting')
    @patch('src.common.telegram_user.database')
    def test_manual_user_is_legit(self, mock_database, mock_get_setting):
        """Вручную добавленный пользователь считается легитимным."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            None,  # chat_members: нет
            {'count': 1},  # manual_users: есть
            {'invite_consumed': 0},  # invites
            None,  # users
        ]
        mock_get_setting.return_value = '0'  # Инвайт-система выключена

        auth = get_user_auth_status(200)

        self.assertTrue(auth.is_manual_user)
        self.assertTrue(auth.is_legit)
        self.assertFalse(auth.is_invite_blocked)


class TestHealthCache(unittest.TestCase):
    """Тесты кеша статуса здоровья."""

    def setUp(self):
        from src.common import health_check
        health_check.clear_health_cache()

    def tearDown(self):
        from src.common import health_check
        health_check.clear_health_cache()

    def test_health_cache_stores_and_returns(self):
        """Кеш хранит и возвращает строки статуса."""
        from src.common.health_check import (
            _set_cached_health_lines,
            _get_cached_health_lines,
        )

        lines = ["*Статус:* 🟢 работает"]
        _set_cached_health_lines(lines)

        cached = _get_cached_health_lines()
        self.assertEqual(cached, lines)

    def test_health_cache_expires(self):
        """Кеш статуса здоровья протухает после TTL."""
        from src.common import health_check

        # Вручную помещаем запись с истёкшим TTL
        health_check._health_lines_cache = (["old"], time.monotonic() - 120)

        cached = health_check._get_cached_health_lines()
        self.assertIsNone(cached)

    def test_clear_health_cache(self):
        """clear_health_cache() очищает кеш."""
        from src.common.health_check import (
            _set_cached_health_lines,
            _get_cached_health_lines,
            clear_health_cache,
        )

        _set_cached_health_lines(["test"])
        clear_health_cache()

        cached = _get_cached_health_lines()
        self.assertIsNone(cached)

    @patch('src.common.health_check.get_planned_outage_status_lines', return_value=[])
    @patch('src.common.health_check.get_health_status_snapshot')
    def test_get_tax_health_status_lines_caches_result(self, mock_snapshot, mock_outages):
        """get_tax_health_status_lines() кеширует результат при повторных вызовах."""
        from src.common.health_check import (
            get_tax_health_status_lines,
            HealthStatusSnapshot,
        )

        mock_snapshot.return_value = HealthStatusSnapshot(
            status="healthy",
            last_checked_at=1000,
            last_healthy_at=1000,
            last_broken_at=900,
            last_broken_started_at=800,
        )

        # Первый вызов — обращение к get_health_status_snapshot
        lines1 = get_tax_health_status_lines()
        self.assertEqual(mock_snapshot.call_count, 1)
        self.assertTrue(len(lines1) > 0)

        # Второй вызов — из кеша, snapshot не вызывается повторно
        lines2 = get_tax_health_status_lines()
        self.assertEqual(mock_snapshot.call_count, 1)
        self.assertEqual(lines1, lines2)


if __name__ == '__main__':
    unittest.main()
