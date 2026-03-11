"""
Модели данных для подсистемы Group Knowledge.

Содержит data-классы для сообщений, Q&A-пар и результатов анализа.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class GroupMessage:
    """Сообщение из Telegram-группы."""

    id: Optional[int] = None
    """ID записи в БД (auto-increment)."""

    telegram_message_id: int = 0
    """ID сообщения в Telegram."""

    group_id: int = 0
    """ID группы/супергруппы в Telegram."""

    group_title: str = ""
    """Название группы."""

    sender_id: int = 0
    """ID отправителя в Telegram."""

    sender_name: str = ""
    """Имя отправителя (first_name + last_name)."""

    message_text: str = ""
    """Текст сообщения."""

    caption: Optional[str] = None
    """Подпись к медиа (если есть)."""

    has_image: bool = False
    """Содержит ли сообщение изображение."""

    image_path: Optional[str] = None
    """Путь к сохранённому изображению на диске."""

    image_description: Optional[str] = None
    """Текстовое описание изображения (от GigaChat)."""

    reply_to_message_id: Optional[int] = None
    """ID сообщения, на которое это ответ (reply-to в Telegram)."""

    message_date: int = 0
    """Дата сообщения (UNIX timestamp)."""

    collected_at: int = 0
    """Время сбора записи (UNIX timestamp)."""

    processed: int = 0
    """Флаг обработки: 0 — не обработано, 1 — обработано."""

    is_question: Optional[bool] = None
    """Результат классификации сообщения как вопроса (True/False/None)."""

    question_confidence: Optional[float] = None
    """Уверенность классификатора вопроса (0.0–1.0)."""

    question_reason: Optional[str] = None
    """Краткое объяснение классификации вопроса."""

    question_model_used: Optional[str] = None
    """Модель, использованная для классификации вопроса."""

    question_detected_at: Optional[int] = None
    """Время классификации вопроса (UNIX timestamp)."""

    @property
    def full_text(self) -> str:
        """Полный текст сообщения (текст + подпись + описание изображения)."""
        parts: List[str] = []
        if self.message_text:
            parts.append(self.message_text)
        if self.caption:
            parts.append(self.caption)
        if self.image_description:
            parts.append(f"[Изображение: {self.image_description}]")
        return "\n".join(parts)


@dataclass
class QAPair:
    """Пара вопрос-ответ, извлечённая из переписки группы."""

    id: Optional[int] = None
    """ID записи в БД (auto-increment)."""

    question_text: str = ""
    """Текст вопроса."""

    answer_text: str = ""
    """Текст ответа."""

    question_message_id: Optional[int] = None
    """FK → gk_messages.id (сообщение с вопросом)."""

    answer_message_id: Optional[int] = None
    """FK → gk_messages.id (сообщение с ответом)."""

    group_id: int = 0
    """ID группы, из которой извлечена пара."""

    extraction_type: str = "thread_reply"
    """Тип извлечения: 'thread_reply' или 'llm_inferred'."""

    confidence: Optional[float] = None
    """Оценка уверенности LLM в качестве пары (0.0–1.0)."""

    confidence_reason: Optional[str] = None
    """Краткое объяснение, почему выставлен текущий confidence."""

    fullness: Optional[float] = None
    """Оценка полноты ответа (0.0–1.0)."""

    llm_model_used: str = ""
    """Модель LLM, использованная для извлечения/валидации."""

    llm_request_payload: Optional[str] = None
    """JSON-представление запроса, отправленного в LLM для отладки."""

    created_at: int = 0
    """Время создания записи (UNIX timestamp)."""

    approved: int = 1
    """Флаг одобрения: 1 — одобрено (по умолчанию), 0 — отклонено."""

    vector_indexed: int = 0
    """Флаг индексации в векторном хранилище: 0 — нет, 1 — да."""

    expert_status: Optional[str] = None
    """Сводный статус экспертной валидации: None, 'approved' или 'rejected'."""

    # --- Транзиентные поля (заполняются при поиске, не сохраняются в БД) ---

    search_bm25_score: Optional[float] = None
    """Нормализованная оценка BM25 [0, 1] для данного результата (транзиентное)."""

    search_vector_score: Optional[float] = None
    """Нормализованная оценка векторного поиска [0, 1] для данного результата (транзиентное)."""

    search_relevance_tier: Optional[str] = None
    """Уровень релевантности: 'высокая', 'средняя', 'низкая' (транзиентное)."""


@dataclass
class ImageDescription:
    """Результат описания изображения через GigaChat."""

    image_path: str = ""
    """Путь к исходному файлу."""

    description: str = ""
    """Текстовое описание содержимого."""

    model_used: str = ""
    """Модель, использованная для описания."""

    success: bool = True
    """Было ли описание получено успешно."""

    error: Optional[str] = None
    """Текст ошибки, если описание не удалось."""


@dataclass
class AnalysisResult:
    """Результат анализа сообщений за период."""

    date: str = ""
    """Дата анализа (YYYY-MM-DD)."""

    group_id: int = 0
    """ID анализируемой группы."""

    total_messages: int = 0
    """Общее число сообщений за период."""

    thread_pairs_found: int = 0
    """Число Q&A пар, найденных по thread reply."""

    llm_pairs_found: int = 0
    """Число Q&A пар, найденных через LLM-инференс."""

    pairs_indexed: int = 0
    """Число пар, проиндексированных в Qdrant."""

    errors: List[str] = field(default_factory=list)
    """Список ошибок, возникших при анализе."""


@dataclass
class ResponderResult:
    """Результат работы автоответчика на вопрос."""

    question_text: str = ""
    """Текст полученного вопроса."""

    answer_text: str = ""
    """Сгенерированный ответ."""

    confidence: float = 0.0
    """Уверенность в ответе (0.0–1.0)."""

    source_qa_pair_ids: List[int] = field(default_factory=list)
    """ID Q&A-пар, использованных для генерации ответа."""

    dry_run: bool = True
    """Был ли ответ отправлен (False) или только залогирован (True)."""

    responded: bool = False
    """Был ли ответ фактически отправлен пользователю."""

    score_diagnostics: Optional[List[Dict]] = None
    """Диагностика поисковых оценок по каждой использованной паре (опционально)."""
