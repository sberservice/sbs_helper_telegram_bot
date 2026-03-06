"""
Настройки модуля Group Knowledge.

Содержит метаданные модуля и вспомогательные константы.
"""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()

MODULE_NAME: Final[str] = "group_knowledge"
MODULE_VERSION: Final[str] = "0.1.0"
MODULE_AUTHOR: Final[str] = "SBS Archie"
MODULE_DESCRIPTION: Final[str] = "Майнинг знаний из Telegram-групп технической поддержки"

# Максимальный возраст сообщения (секунды) — старые пропускаются при реконнекте
MAX_MESSAGE_AGE_SECONDS: Final[int] = 120

# Максимальная длина текста сообщения для обработки
MAX_MESSAGE_TEXT_LENGTH: Final[int] = 8000

# Максимальная длина одного сообщения для LLM-анализа
MAX_ANALYSIS_TEXT_LENGTH: Final[int] = 50000

# Расширения файлов изображений, которые следует скачивать
SUPPORTED_IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif",
)

# Поддерживаемые MIME-типы изображений
SUPPORTED_IMAGE_MIME_TYPES: Final[tuple[str, ...]] = (
    "image/jpeg", "image/png", "image/bmp", "image/webp", "image/gif",
)

# Минимальная длина вопроса для обработки автоответчиком
MIN_QUESTION_LENGTH: Final[int] = 10

# Русские вопросительные слова для эвристики определения вопроса
QUESTION_KEYWORDS_RU: Final[tuple[str, ...]] = (
    "как", "что", "почему", "зачем", "где", "когда", "кто",
    "каким", "какой", "какая", "какие", "какое",
    "сколько", "можно", "нужно", "подскажите", "помогите",
    "расскажите", "объясните", "скажите",
)

# Telegram user IDs, которые нужно игнорировать в анализе и автоответах
GK_IGNORED_SENDER_IDS: Final[tuple[int, ...]] = tuple(
    int(value.strip())
    for value in os.getenv("GK_IGNORED_SENDER_IDS", "11111").split(",")
    if value.strip()
)

# Окно склейки соседних сообщений одного пользователя в один вопрос
GK_MESSAGE_GROUPING_WINDOW_SECONDS: Final[int] = int(
    os.getenv("GK_MESSAGE_GROUPING_WINDOW_SECONDS", "20")
)
