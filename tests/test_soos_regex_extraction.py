"""
Тесты парсера полей СООС.
"""

import unittest

from src.sbs_helper_telegram_bot.soos.soos_parser import (
    extract_ticket_fields,
    get_missing_required_fields,
)


class TestSoosRegexExtraction(unittest.TestCase):
    """Проверки извлечения полей из текста тикета."""

    def test_extract_ticket_fields_success(self):
        """Извлекает обязательные поля из типового тикета."""
        ticket_text = """
TID: 10371049
Наименование ТСТ: ИП МАРЕЕВ С.В.
Телефон обратной связи: +79253755053
Адрес установки POS-терминала: Московская область обл, г Лыткарино, кв-л 3А, дом 8
merchant: 123456789012
        """.strip()

        fields = extract_ticket_fields(ticket_text)

        self.assertEqual(fields["tid"], "10371049")
        self.assertEqual(fields["merchant_name"], "ИП МАРЕЕВ С.В.")
        self.assertEqual(fields["phone"], "79253755053")
        self.assertEqual(fields["merchant_id"], "123456789012")
        self.assertIn("г Лыткарино", fields["address"])

    def test_missing_required_fields(self):
        """Возвращает список отсутствующих обязательных полей."""
        ticket_text = """
Наименование ТСТ: MOCHI & BUBBLE TEA
Телефон обратной связи: +79629355081
        """.strip()

        fields = extract_ticket_fields(ticket_text)
        missing = get_missing_required_fields(fields)

        self.assertIn("Адрес установки POS-терминала", missing)
        self.assertIn("TID", missing)
        self.assertIn("merchant/MID", missing)

    def test_generate_mid_from_tid_when_mid_missing(self):
        """Генерирует MID по правилу 851000 + последние 6 цифр TID."""
        ticket_text = """
TID: 10371049
Наименование ТСТ: MOCHI & BUBBLE TEA
Телефон обратной связи: +79629355081
Адрес установки POS-терминала: Островцы, Раменское, ул. Баулинская, дом 3
        """.strip()

        fields = extract_ticket_fields(ticket_text)

        self.assertEqual(fields["tid"], "10371049")
        self.assertEqual(fields["merchant_id"], "851000371049")

    def test_extract_phone_from_inline_description_contact(self):
        """Извлекает телефон из inline-фрагмента описания с маркером `Тел.:`."""
        ticket_text = """
TID: 42297873
Наименование ТСТ: SP_Кофейня Мама Малина
Адрес установки POS-терминала: Москва г, г Москва, ул Лавриненко, дом 5
Телефон МПС: -
Описание: SMARTPOS; Контакт в ТСТ: АМЗАРАКОВА ЕКАТЕРИНА, Тел.: 79645552160; Контакт Банка: Захаренко Виктория Игорьевна 79800998227
        """.strip()

        fields = extract_ticket_fields(ticket_text)

        self.assertEqual(fields["phone"], "79645552160")

    def test_use_default_phone_when_missing(self):
        """Подставляет номер по умолчанию, если телефон не найден в тикете."""
        ticket_text = """
TID: 10371049
Наименование ТСТ: MOCHI & BUBBLE TEA
Адрес установки POS-терминала: Островцы, Раменское, ул. Баулинская, дом 3
        """.strip()

        fields = extract_ticket_fields(ticket_text)

        self.assertEqual(fields["phone"], "70000000000")


if __name__ == "__main__":
    unittest.main()
