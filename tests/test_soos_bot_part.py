"""
Тесты bot-part модуля СООС.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.soos.soos_bot_part import (
    add_to_soos_queue,
    process_soos_ticket_text,
)
from telegram.ext import ConversationHandler


class TestSoosQueueOps(unittest.TestCase):
    """Проверки SQL-операций очереди СООС."""

    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.database")
    def test_add_to_soos_queue_inserts_row(self, mock_database):
        """Добавляет задачу в таблицу очереди СООС."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        add_to_soos_queue(123456, "ticket text", "soos_1.png")

        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        values = mock_cursor.execute.call_args[0][1]
        self.assertIn("INSERT INTO soos_image_queue", query)
        self.assertEqual(values[0], 123456)
        self.assertEqual(values[1], "soos_1.png")


class TestSoosBotPartAsync(unittest.IsolatedAsyncioTestCase):
    """Асинхронные проверки сценариев обработки тикета."""

    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_legit", return_value=True)
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job", return_value=False)
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.get_number_of_jobs_in_the_queue", return_value=2)
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.add_to_soos_queue")
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.soos_parser.get_missing_required_fields", return_value=[])
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.soos_parser.extract_ticket_fields")
    async def test_process_ticket_success(
        self,
        mock_extract,
        _mock_missing,
        mock_add,
        _mock_queue_size,
        _mock_unprocessed,
        _mock_legit,
    ):
        """Ставит задачу в очередь при валидном тикете."""
        mock_extract.return_value = {
            "merchant_name": "MOCHI",
            "address": "Адрес",
            "phone": "79990000000",
            "tid": "12345678",
            "merchant_id": "123456789012",
        }

        update = MagicMock()
        update.effective_user.id = 100
        update.message.text = "ticket body"
        update.message.reply_text = AsyncMock()

        result = await process_soos_ticket_text(update, MagicMock())

        self.assertEqual(result, ConversationHandler.END)
        mock_add.assert_called_once()
        update.message.reply_text.assert_awaited()

    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_legit", return_value=True)
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job", return_value=False)
    @patch(
        "src.sbs_helper_telegram_bot.soos.soos_bot_part.soos_parser.get_missing_required_fields",
        return_value=["Адрес установки POS-терминала", "TID", "merchant/MID"],
    )
    @patch("src.sbs_helper_telegram_bot.soos.soos_bot_part.soos_parser.extract_ticket_fields", return_value={})
    async def test_process_ticket_missing_required_fields(
        self,
        _mock_extract,
        _mock_missing,
        _mock_unprocessed,
        _mock_legit,
    ):
        """Блокирует генерацию, если обязательные поля не извлечены."""
        update = MagicMock()
        update.effective_user.id = 101
        update.message.text = "ticket body"
        update.message.reply_text = AsyncMock()

        result = await process_soos_ticket_text(update, MagicMock())

        self.assertEqual(result, ConversationHandler.END)
        self.assertGreaterEqual(update.message.reply_text.await_count, 2)
        all_texts = [call.args[0] for call in update.message.reply_text.await_args_list]
        combined = "\n".join(all_texts)
        self.assertIn("POS\\-терминала", combined)
        self.assertIn("TID", combined)
        self.assertIn("merchant/MID", combined)


if __name__ == "__main__":
    unittest.main()
