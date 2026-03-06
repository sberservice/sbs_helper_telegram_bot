"""
Поиск по Q&A-парам для подсистемы Group Knowledge.

Выполняет гибридный поиск (vector + BM25) по извлечённым парам
и генерирует ответы с помощью LLM.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from config import ai_settings
from src.core.ai.llm_provider import get_provider
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import QAPair

logger = logging.getLogger(__name__)

# Промпт для генерации ответа на основе Q&A пар
ANSWER_GENERATION_PROMPT = """Ты — помощник технической поддержки для полевых инженеров.

На основе найденных пар вопрос-ответ из базы знаний технической поддержки ответь на вопрос пользователя.

Найденные пары:
{qa_context}

Правила:
1. Отвечай максимально точно и конкретно, опираясь на найденные пары.
2. Если несколько пар релевантны — объедини информацию.
3. Если ни одна пара не релевантна вопросу — честно скажи, что не нашёл информации.
4. Не придумывай информацию, которой нет в найденных парах.
5. Отвечай на русском языке.

Верни JSON:
{{
    "answer": "Текст ответа",
    "is_relevant": true/false,
    "confidence": 0.0-1.0,
    "used_pair_ids": [1, 2, ...]
}}"""


class QASearchService:
    """
    Сервис поиска по Q&A-парам.

    Выполняет гибридный поиск (vector + fulltext) и генерирует
    ответы на вопросы пользователей.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Инициализация сервиса.

        Args:
            model_name: Модель LLM для генерации (по умолчанию из настроек).
        """
        self._model_name = model_name or ai_settings.GK_RESPONDER_MODEL
        self._top_k = ai_settings.GK_RESPONDER_TOP_K

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[QAPair]:
        """
        Найти релевантные Q&A пары для запроса.

        Использует гибридный подход: векторный поиск + полнотекстовый.

        Args:
            query: Текст запроса.
            top_k: Число результатов (по умолчанию из настроек).

        Returns:
            Список релевантных QAPair, отсортированных по score.
        """
        k = top_k or self._top_k
        results: List[Tuple[QAPair, float]] = []

        # Векторный поиск
        vector_results = await self._vector_search(query, k * 2)
        for pair, score in vector_results:
            results.append((pair, score))

        # Полнотекстовый поиск (MySQL FULLTEXT)
        fulltext_results = self._fulltext_search(query, k * 2)
        for pair, score in fulltext_results:
            # Проверить дубли
            existing_ids = {r[0].id for r in results}
            if pair.id not in existing_ids:
                results.append((pair, score * 0.8))  # Слегка пониженный вес

        # Сортировать по score и взять top-k
        results.sort(key=lambda x: x[1], reverse=True)
        return [pair for pair, _ in results[:k]]

    async def answer_question(
        self,
        query: str,
    ) -> Optional[Dict]:
        """
        Ответить на вопрос, используя найденные Q&A пары.

        Args:
            query: Текст вопроса.

        Returns:
            Словарь с ключами: answer, confidence, source_pair_ids,
            is_relevant, primary_source_link, source_message_links.
            None если ответ не найден.
        """
        # Поиск релевантных пар
        relevant_pairs = await self.search(query)

        if not relevant_pairs:
            logger.info("Не найдены Q&A пары для вопроса: %s", query[:100])
            return None

        # Подготовить контекст из найденных пар
        qa_context_parts = []
        pair_id_map = {}
        for i, pair in enumerate(relevant_pairs, 1):
            qa_context_parts.append(
                f"Пара {i} (ID={pair.id}):\n"
                f"  В: {pair.question_text[:3500]}\n"
                f"  О: {pair.answer_text[:3500]}"
            )
            if pair.id:
                pair_id_map[i] = pair.id

        qa_context = "\n\n".join(qa_context_parts)

        # Сгенерировать ответ через LLM
        prompt = ANSWER_GENERATION_PROMPT.format(qa_context=qa_context)
        provider = get_provider("deepseek")

        try:
            raw = await provider.chat(
                messages=[{"role": "user", "content": f"Вопрос пользователя: {query}"}],
                system_prompt=prompt,
                purpose="gk_answer",
                model_override=self._model_name,
                response_format={"type": "json_object"},
            )

            parsed = self._parse_json_response(raw)
            if not parsed:
                return None

            answer = parsed.get("answer", "")
            is_relevant = parsed.get("is_relevant", False)
            confidence = float(parsed.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            used_ids = parsed.get("used_pair_ids", [])

            # Преобразовать индексы в реальные pair_id
            source_pair_ids = []
            for idx in used_ids:
                if isinstance(idx, int) and idx in pair_id_map:
                    source_pair_ids.append(pair_id_map[idx])

            if not source_pair_ids and relevant_pairs and relevant_pairs[0].id:
                source_pair_ids.append(relevant_pairs[0].id)

            if not is_relevant or not answer:
                logger.info(
                    "LLM решил, что пары нерелевантны для вопроса: %s",
                    query[:100],
                )
                return None

            source_message_links = self._resolve_source_message_links(source_pair_ids)

            return {
                "answer": answer,
                "confidence": confidence,
                "source_pair_ids": source_pair_ids,
                "is_relevant": is_relevant,
                "primary_source_link": source_message_links[0] if source_message_links else None,
                "source_message_links": source_message_links,
            }
        except Exception as exc:
            logger.error(
                "Ошибка генерации ответа: query=%s error=%s",
                query[:100], exc,
                exc_info=True,
            )
            return None

    async def _vector_search(
        self,
        query: str,
        top_k: int,
    ) -> List[Tuple[QAPair, float]]:
        """
        Выполнить векторный поиск по Q&A парам.

        Args:
            query: Текст запроса.
            top_k: Число результатов.

        Returns:
            Список кортежей (QAPair, score).
        """
        try:
            from src.core.ai.vector_search import LocalVectorIndex, LocalEmbeddingProvider

            embedding_provider = LocalEmbeddingProvider()
            collection_name = ai_settings.GK_QA_VECTOR_COLLECTION
            vector_index = LocalVectorIndex(chunk_collection_name=collection_name)

            # Генерировать эмбеддинг запроса
            query_embedding = embedding_provider.encode(query)
            if not query_embedding:
                logger.warning("Не удалось получить эмбеддинг для поискового запроса")
                return []

            # Поиск в Qdrant
            hits = vector_index.search(
                query_vector=query_embedding,
                limit=top_k,
            )

            results = []
            for hit in hits:
                pair_id = getattr(hit, "document_id", 0)
                if not pair_id:
                    continue

                pair = gk_db.get_qa_pair_by_id(int(pair_id))
                if not pair:
                    continue

                score = float(getattr(hit, "score", 0.0) or 0.0)
                results.append((pair, score))

            return results
        except ImportError:
            logger.debug("Vector search не доступен")
            return []
        except Exception as exc:
            logger.warning("Ошибка векторного поиска: %s", exc)
            return []

    def _fulltext_search(
        self,
        query: str,
        top_k: int,
    ) -> List[Tuple[QAPair, float]]:
        """
        Выполнить полнотекстовый поиск по MySQL FULLTEXT.

        Args:
            query: Текст запроса.
            top_k: Число результатов.

        Returns:
            Список кортежей (QAPair, score).
        """
        try:
            from src.common.database import get_db_connection, get_cursor

            # Подготовить поисковый запрос для FULLTEXT
            # Берём первые несколько слов из запроса
            words = query.split()[:10]
            search_query = " ".join(words)

            with get_db_connection() as conn:
                with get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        SELECT *,
                               MATCH(question_text, answer_text)
                               AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance
                        FROM gk_qa_pairs
                        WHERE approved = 1
                          AND MATCH(question_text, answer_text)
                              AGAINST(%s IN NATURAL LANGUAGE MODE)
                        ORDER BY relevance DESC
                        LIMIT %s
                        """,
                        (search_query, search_query, top_k),
                    )
                    rows = cursor.fetchall()

                    results = []
                    for row in rows:
                        pair = gk_db._row_to_qa_pair(row)
                        score = float(row.get("relevance", 0.0))
                        results.append((pair, score))

                    return results
        except Exception as exc:
            logger.warning("Ошибка полнотекстового поиska: %s", exc)
            return []

    def _resolve_source_message_links(self, pair_ids: List[int]) -> List[str]:
        """Построить ссылки на сообщения с похожими кейсами по найденным Q&A-парам."""
        links: List[str] = []
        seen_links = set()

        for pair_id in pair_ids:
            pair = gk_db.get_qa_pair_by_id(pair_id)
            if not pair:
                continue

            message = None
            if pair.answer_message_id:
                message = gk_db.get_message_by_id(pair.answer_message_id)
            if message is None and pair.question_message_id:
                message = gk_db.get_message_by_id(pair.question_message_id)
            if not message:
                continue

            link = self._build_group_message_link(
                group_id=message.group_id,
                telegram_message_id=message.telegram_message_id,
            )
            if link and link not in seen_links:
                links.append(link)
                seen_links.add(link)

        return links

    @staticmethod
    def _build_group_message_link(group_id: int, telegram_message_id: int) -> Optional[str]:
        """Построить Telegram-ссылку на сообщение внутри группы/супергруппы."""
        if not group_id or not telegram_message_id:
            return None

        normalized_group_id = str(abs(group_id))
        if normalized_group_id.startswith("100"):
            normalized_group_id = normalized_group_id[3:]
        if not normalized_group_id:
            return None

        return f"https://t.me/c/{normalized_group_id}/{telegram_message_id}"

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[Dict]:
        """Извлечь JSON из ответа LLM."""
        if not raw or not raw.strip():
            return None

        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])
            else:
                text = text.strip("`").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass

        logger.warning("Не удалось распарсить JSON из LLM: %s", raw[:200])
        return None
