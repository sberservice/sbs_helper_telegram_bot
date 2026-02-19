#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from datetime import date

from src.common.health_check import OUTAGE_TYPE_RED, _format_outage_window, _get_outage_window


class TestHealthCheckFormatting(unittest.TestCase):
    """Тесты форматирования сообщений о плановых работах."""

    def test_red_outage_window_shows_start_and_end_dates(self):
        """Для красного окна должны показываться дата начала и дата конца."""
        start_dt, end_dt = _get_outage_window(date(2026, 2, 20), OUTAGE_TYPE_RED)

        text = _format_outage_window(int(start_dt.timestamp()), int(end_dt.timestamp()), OUTAGE_TYPE_RED)

        self.assertIn("20:00 20.02.2026 - 20:00 21.02.2026", text)
        self.assertNotIn("МСК", text)
        self.assertNotIn("до ", text)


if __name__ == "__main__":
    unittest.main()
